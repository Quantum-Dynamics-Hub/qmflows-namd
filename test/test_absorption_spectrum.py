from nac.common import retrieve_hdf5_data
from nac.workflows.input_validation import process_input
from nac.workflows import workflow_stddft
from os.path import join
from .utilsTest import remove_files, copy_basis_and_orbitals

import numpy as np
import pkg_resources as pkg
import os
import tempfile


# Environment data
file_path = pkg.resource_filename('nac', '')
root = os.path.split(file_path)[0]

path_traj_xyz = join(root, 'test/test_files/Cd.xyz')
path_original_hdf5 = join(root, 'test/test_files/Cd.hdf5')
project_name = 'Cd'
input_file = join(root, 'test/test_files/input_test_absorption_spectrum.yml')


def test_compute_oscillators(tmp_path):
    """
    Compute the oscillator strenght and check the results.
    """
    scratch_path = join(tempfile.gettempdir(), 'namd')
    path_test_hdf5 = tempfile.mktemp(
        prefix='absorption_spectrum_', suffix='.hdf5', dir=scratch_path)
    if not os.path.exists(scratch_path):
        os.makedirs(scratch_path, exist_ok=True)
    try:
        # Run the actual test
        copy_basis_and_orbitals(path_original_hdf5, path_test_hdf5,
                                project_name)
        calculate_oscillators(path_test_hdf5, scratch_path)
        check_properties(path_test_hdf5)

    finally:
        remove_files()


def calculate_oscillators(path_test_hdf5, scratch_path):
    """
    Compute a couple of couplings with the Levine algorithm
    using precalculated MOs.
    """
    config = process_input(input_file, 'absorption_spectrum')
    config['path_hdf5'] = path_test_hdf5
    config['workdir'] = scratch_path
    config['path_traj_xyz'] = join(
        root, config.path_traj_xyz)

    workflow_stddft(config)


def check_properties(path_test_hdf5):
    """
    Check that the tensor stored in the HDF5 are correct.
    """
    dipole_matrices = retrieve_hdf5_data(
        path_test_hdf5, 'Cd/multipole/point_0/dipole')

    # The diagonals of each component of the matrix must be zero
    # for a single atom
    diagonals = np.sum([np.diag(dipole_matrices[n + 1]) for n in range(3)])
    assert abs(diagonals) < 1e-16
