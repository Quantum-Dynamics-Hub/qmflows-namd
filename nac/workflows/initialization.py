__all__ = ['initialize', 'read_swaps', 'split_trajectory']

from nac.common import (
    InputKey, Matrix, change_mol_units, retrieve_hdf5_data, is_data_in_hdf5)
from nac.schedule.components import (
    create_point_folder, split_file_geometries)
from os.path import join
from qmflows.hdf5.quantumHDF5 import cp2k2hdf5
from qmflows.parsers import parse_string_xyz
from subprocess import (PIPE, Popen)

import fnmatch
import getpass
import h5py
import logging
import nac
import numpy as np
import os
import pkg_resources
import subprocess
import tempfile

# Starting logger
logger = logging.getLogger(__name__)


def initialize(config: dict) -> dict:
    """
    Initialize all the data required to schedule the workflows associated with
    the nonadaibatic coupling
    """
    log_config(config)

    # Scratch folder
    scratch_path = config["scratch_path"]
    if scratch_path is None:
        scratch_path = join(tempfile.gettempdir(),
                            getpass.getuser(), config.project_name)
        logger.warning(
            f"path to scratch was not defined, using: {scratch_path}")
    config['workdir'] = scratch_path

    # If the directory does not exist create it
    if not os.path.exists(scratch_path):
        os.makedirs(scratch_path)

    # HDF5 path
    path_hdf5 = config["path_hdf5"]
    if path_hdf5 is None:
        path_hdf5 = join(scratch_path, 'quantum.hdf5')
        logger.warning(
            f"path to the HDF5 was not defined, using: {path_hdf5}")

    # all_geometries type :: [String]
    geometries = split_file_geometries(config["path_traj_xyz"])
    config['geometries'] = geometries

    # Create a folder for each point the the dynamics
    enumerate_from = config["enumerate_from"]
    len_geometries = len(geometries)
    config["folders"] = create_point_folder(
        scratch_path, len_geometries, enumerate_from)

    config['calc_new_wf_guess_on_points'] = guesses_to_compute(
        config['calculate_guesses'], enumerate_from, len_geometries)

    # Generate a list of tuples containing the atomic label
    # and the coordinates to generate
    # the primitive CGFs
    atoms = parse_string_xyz(geometries[0])
    if 'angstrom' in config["geometry_units"].lower():
        atoms = change_mol_units(atoms)

    # Save Basis to HDF5
    save_basis_to_hdf5(config)

    return config


def save_basis_to_hdf5(config: dict, package_name: str = "cp2k") -> None:
    """
    Store the specification of the basis set in the HDF5 to compute the integrals
    """
    basis_location = join(package_name, 'basis')
    with h5py.File(config["path_hdf5"]) as f5:
        if basis_location not in f5:
            # Search Path to the file containing the basis set
            path_basis = pkg_resources.resource_filename(
                "nac", "basis/BASIS_MOLOPT")
            keyBasis = InputKey("basis", [path_basis])
            cp2k2hdf5(f5, [keyBasis])


def guesses_to_compute(calculate_guesses: str, enumerate_from: int, len_geometries) -> list:
    """Guess for the wave function"""
    if calculate_guesses is None:
        points_guess = []
    elif calculate_guesses.lower() in 'first':
        # Calculate new Guess in the first geometry
        points_guess = [enumerate_from]
        msg = "An initial Calculation will be computed as guess for the wave function"
        logger.info(msg)
    elif calculate_guesses.lower() in 'all':
        # Calculate new Guess in each geometry
        points_guess = [enumerate_from + i for i in range(len_geometries)]
        msg = "A guess calculation will be done for each geometry"
        logger.info(msg)

    return points_guess


def read_swaps(path_hdf5: str, project_name: str) -> Matrix:
    """
    Read the crossing tracking for the Molecular orbital
    """
    path_swaps = join(project_name, 'swaps')
    if is_data_in_hdf5(path_hdf5, path_swaps):
        return retrieve_hdf5_data(path_hdf5, path_swaps)
    else:
        msg = f"""There is not a tracking file called: {path_swaps}
        This file is automatically created when running the worflow_coupling
        simulations"""
        raise RuntimeError(msg)


def split_trajectory(path: str, nBlocks: int, pathOut: str) -> list:
    """
    Split an XYZ trajectory in n Block and write
    them in a given path.
    :Param path: Path to the XYZ file.
    :param nBlocks: number of Block into which the xyz file is split.
    :param pathOut: Path were the block are written.
    :returns: path to block list
    """
    with open(path, 'r') as f:
        # Read First line
        ls = f.readline()
        numat = int(ls.split()[0])

    # Number of lines in the file
    cmd = f"wc -l {path}"
    ls = subprocess.check_output(cmd.split()).decode()
    lines = int(ls.split()[0])
    if (lines % (numat + 2)) != 0:
        lines += 1

    # Number of points in the xyz file
    nPoints = lines // (numat + 2)
    # Number of points for each chunk
    nChunks = int(np.ceil(nPoints / nBlocks))
    # Number of lines per block
    lines_per_block = nChunks * (numat + 2)
    # Path where the splitted xyz files are written
    prefix = join(pathOut, 'chunk_xyz_')
    cmd = f'split -a 1 -l {lines_per_block} {path} {prefix}'
    p = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE, shell=True)
    rs = p.communicate()
    err = rs[1]
    if err:
        raise RuntimeError(f"Submission Errors: {err}")
    else:
        return fnmatch.filter(os.listdir(), "chunk_xyz_?")


def log_config(config):
    """
    Print initial configuration
    """
    workdir = os.path.abspath('.')
    file_log = f'{config.project_name}.log'
    logging.basicConfig(filename=file_log, level=logging.DEBUG,
                        format='%(asctime)s---%(levelname)s\n%(message)s\n',
                        datefmt='[%I:%M:%S]')
    logging.getLogger("noodles").setLevel(logging.WARNING)
    handler = logging.StreamHandler()
    handler.terminator = ""

    version = pkg_resources.get_distribution('qmflows-namd').version
    path = nac.__path__

    logger.info(f"Using qmflows-namd version: {version} ")
    logger.info(f"qmflows-namd path is: {path}")
    logger.info(f"Working directory is: {workdir}")
    logger.info(f"Data will be stored in HDF5 file: {config.path_hdf5}")
