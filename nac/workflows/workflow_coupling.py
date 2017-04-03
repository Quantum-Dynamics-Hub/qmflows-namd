__author__ = "Felipe Zapata"

__all__ = ['generate_pyxaid_hamiltonians']

# ================> Python Standard  and third-party <==========
from noodles import (gather, schedule)

from nac.common import (change_mol_units, search_data_in_hdf5)
from nac.schedule.components import calculate_mos
from nac.schedule.scheduleCoupling import (
    lazy_overlaps, lazy_couplings, write_hamiltonians)
from os.path import join
from qmworks import run
from qmworks.parsers import parse_string_xyz

import logging
import os
import shutil

# Type Hints
from typing import (Dict, List, Tuple)

logger = logging.getLogger(__name__)
# ==============================> Main <==================================


def generate_pyxaid_hamiltonians(
        package_name: str, project_name: str,
        package_args: Dict, guess_args: Dict=None,
        geometries: List=None, dictCGFs: Dict=None,
        calc_new_wf_guess_on_points: str=None,
        path_hdf5: str=None, enumerate_from: int=0,
        package_config: Dict=None, dt: float=1,
        traj_folders: List=None, work_dir: str=None,
        basisname: str=None, hdf5_trans_mtx: str=None,
        nHOMO: int=None,
        couplings_range: Tuple=None) -> None:
    """
    Use a md trajectory to generate the hamiltonian components to run PYXAID
    nonadiabatic molecular dynamics.

    :param package_name: Name of the package to run the QM simulations.
    :param project_name: Folder name where the computations
    are going to be stored.
    :param package_args: Specific Settings for the package that will compute
    the MOs.
    :param geometries: List of string cotaining the molecular geometries
    numerical results.
    :paramter dictCGFS: Dictionary from Atomic Label to basis set
    :param calc_new_wf_guess_on_points: Calculate a guess wave function either
    in the first point or on each point of the trajectory.
    :param path_hdf5: path to the HDF5 file were the data is going to be stored.
    :param enumerate_from: Number from where to start enumerating the folders
    create for each point in the MD.
    :param hdf5_trans_mtx: Path into the HDF5 file where the transformation
    matrix (from Cartesian to sphericals) is stored.
    :param dt: Time used in the dynamics (femtoseconds)
    :param package_config: Parameters required by the Package.
    :type package_config: Dict
    :param nHOMO: index of the HOMO orbital.
    :param couplings_range: Range of MO use to compute the nonadiabatic
    coupling matrix.

    :returns: None
    """
    # Start logging event
    file_log = '{}.log'.format(project_name)
    logging.basicConfig(filename=file_log, level=logging.DEBUG,
                        format='%(levelname)s:%(message)s  %(asctime)s\n',
                        datefmt='%m/%d/%Y %I:%M:%S %p')

    # prepare Cp2k Jobs
    # Point calculations Using CP2K
    mo_paths_hdf5 = calculate_mos(
        package_name, geometries, project_name, path_hdf5, traj_folders,
        package_args, guess_args, calc_new_wf_guess_on_points,
        enumerate_from, package_config=package_config)

    # Calculate Non-Adiabatic Coupling
    # Number of Coupling points calculated with the MD trajectory
    promised_overlaps = calculate_overlap(
        project_name, path_hdf5, dictCGFs, geometries, mo_paths_hdf5,
        hdf5_trans_mtx, enumerate_from, nHOMO=nHOMO,
        couplings_range=couplings_range)

    # Compute the Couplings
    # Inplace scheduling of lazy_couplings function
    # Equivalent to add @schedule on top of the function
    schedule_couplings = schedule(lazy_couplings)
    promised_crossing_and_couplings = schedule_couplings(
        promised_overlaps, path_hdf5, project_name, enumerate_from, dt)

    # Write the results in PYXAID format
    path_hamiltonians = join(work_dir, 'hamiltonians')
    if not os.path.exists(path_hamiltonians):
        os.makedirs(path_hamiltonians)

    # Inplace scheduling of write_hamiltonians function.
    # Equivalent to add @schedule on top of the function
    schedule_write_ham = schedule(write_hamiltonians)

    # Number of matrix computed
    nPoints = len(geometries) - 2

    # Write Hamilotians in PYXAID format
    promise_files = schedule_write_ham(
        path_hdf5, mo_paths_hdf5, promised_crossing_and_couplings,
        nPoints, path_dir_results=path_hamiltonians,
        enumerate_from=enumerate_from, nHOMO=nHOMO,
        couplings_range=couplings_range)

    run(promise_files, folder=work_dir)

    remove_folders(traj_folders)

# ==============================> Tasks <=====================================


def calculate_overlap(project_name: str, path_hdf5: str, dictCGFs: Dict,
                      geometries: List, mo_paths_hdf5: List, hdf5_trans_mtx: str,
                      enumerate_from: int, nHOMO: int=None,
                      couplings_range: Tuple=None,
                      units: str='angstrom') -> List:
    """
    Calculate the Overlap matrices before computing the non-adiabatic
    coupling using 3 consecutive set of MOs in a molecular dynamic.

    :param path_hdf5: Path to the HDF5 file that contains the
    numerical results.
    :type path_hdf5: String
    :paramter dictCGFS: Dictionary from Atomic Label to basis set
    :type     dictCGFS: Dict String [CGF],
              CGF = ([Primitives], AngularMomentum),
              Primitive = (Coefficient, Exponent)
    :param geometries: list of molecular geometries
    :type geometries: [String]
    :param mo_paths: Path to the MO coefficients and energies in the
    HDF5 file.
    :type mo_paths: [String]
    :param hdf5_trans_mtx: path to the transformation matrix in the HDF5 file.
    :type hdf5_trans_mtx: String
    :param enumerate_from: Number from where to start enumerating the folders
    create for each point in the MD
    :type enumerate_from: Int
    :param nHOMO: index of the HOMO orbital in the HDF5
    :param couplings_range: range of Molecular orbitals used to compute the
    coupling.
    :returns: paths to the Overlap matrices inside the HDF5.
    """
    nPoints = len(geometries) - 1

    # Compute the Overlaps
    paths_overlaps = []
    for i in range(nPoints):
        # extract 3 molecular geometries to compute the overlaps
        molecules = tuple(map(lambda idx: parse_string_xyz(geometries[idx]),
                              [i, i + 1]))

        # If units are Angtrom convert then to a.u.
        if 'angstrom' in units.lower():
            molecules = tuple(map(change_mol_units, molecules))

        # Path inside the HDF5 where the overlaps are stored
        root = join(project_name, 'overlaps_{}'.format(i + enumerate_from))
        names_matrices = ['mtx_sji_t0', 'mtx_sij_t0']
        overlaps_paths_hdf5 = [join(root, name) for name in names_matrices]

        # If the Overlaps are not in the HDF5 file compute them
        if search_data_in_hdf5(path_hdf5, overlaps_paths_hdf5):
            paths_overlaps.append(overlaps_paths_hdf5)
            logger.info("{} Overlaps are already in the HDF5".format(root))
        else:
            # Compute the coupling
            overlaps = lazy_overlaps(
                i, project_name, path_hdf5, dictCGFs, molecules, mo_paths_hdf5,
                hdf5_trans_mtx=hdf5_trans_mtx, enumerate_from=enumerate_from,
                nHOMO=nHOMO, couplings_range=couplings_range)
            paths_overlaps.append(overlaps)

    # Gather all the promised paths
    return gather(*paths_overlaps)


def remove_folders(folders):
    """
    Remove unused folders
    """
    for f in folders:
        if os.path.exists(f):
            shutil.rmtree(f)
