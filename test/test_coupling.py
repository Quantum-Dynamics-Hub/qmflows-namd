from nac.common import (is_data_in_hdf5, retrieve_hdf5_data)
from nac.workflows.input_validation import process_input
from nac.workflows.workflow_coupling import workflow_derivative_couplings
from os.path import join

import numpy as np
import pkg_resources as pkg
import os
import shutil
import sys


# Environment data
file_path = pkg.resource_filename('nac', '')
root = os.path.split(file_path)[0]


def test_fast_couplings(tmp_path):
    """
    Check that the couplings run
    """
    file_path = join(
        root, 'test/test_files/input_fast_test_derivative_couplings.yml')
    config = process_input(file_path, 'derivative_couplings')
    config["scratch_path"] = tmp_path
    tmp_hdf5 = os.path.join(tmp_path, 'fast_couplings.hdf5')
    shutil.copy(config.path_hdf5, tmp_hdf5)
    config['path_hdf5'] = tmp_hdf5
    try:
        hamiltonians, _ = workflow_derivative_couplings(config)
        os.remove('cache.db')
        check_couplings(config, tmp_hdf5)
        check_hamiltonians(hamiltonians)
    except:
        print("scratch_path: ", tmp_path)
        print("Unexpected error:", sys.exc_info()[0])
        raise


def check_couplings(config: dict, tmp_hdf5: str) -> None:
    """
    Check that the couplings have meaningful values
    """
    def create_paths(keyword: str) -> list:
        return [f'{config.project_name}/{keyword}_{x}'
                for x in range(len(config.geometries) - 1)]
    overlaps = create_paths('overlaps')
    couplings = create_paths('coupling')

    # Check that couplings and overlaps exists
    assert is_data_in_hdf5(tmp_hdf5, overlaps)
    assert is_data_in_hdf5(tmp_hdf5, couplings)

    # All the elements are different of inifinity or nan
    tensor_couplings = np.stack(retrieve_hdf5_data(tmp_hdf5, couplings))
    assert np.isfinite(tensor_couplings).all()

    # Check that the couplings are anti-symetric
    for mtx in tensor_couplings[:]:
        assert np.allclose(mtx, -mtx.T)

    # Check that there are not NaN
    assert (not np.all(np.isnan(tensor_couplings)))


def check_hamiltonians(hamiltonians: str) -> None:
    """
    Check that the hamiltonians were written correctly
    """
    energies = np.stack([np.diag(np.loadtxt(ts[1])) for ts in hamiltonians])
    couplings = np.stack([np.loadtxt(ts[0]) for ts in hamiltonians])

    # check that energies and couplings are finite values
    assert np.isfinite(energies).all()
    assert np.isfinite(couplings).all()

    # Check that the couplings diagonal is zero
    assert abs(np.einsum('jii->', couplings)) < 1e-16
