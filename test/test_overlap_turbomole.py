

from qmworks.hdf5.quantumHDF5 import turbomole2hdf5
from qmworks.parsers.xyzParser import readXYZ

from os.path import join
import h5py
import numpy as np
import os

# ===============================<>============================================
from nac.basisSet.basisNormalization import createNormalizedCGFs
from nac.common import InputKey
from nac.integrals.overlapIntegral import calcMtxOverlapP

from utilsTest import offdiagonalTolerance, triang2mtx, try_to_remove

# ===============================<>============================================
path_hdf5 = 'test_files/test.hdf5'
path_MO = 'test_files/aomix_ethylene.in'


def create_dict_CGFs(f5, pathBasis, basisname, packageName, xyz):
    """
    Store the basis set in HDF5 format
    """
    keyBasis = InputKey("basis", [pathBasis])
    turbomole2hdf5(f5, [keyBasis])   # Store the basis sets

    return  createNormalizedCGFs(f5, basisname, packageName, xyz)


def dump_MOs_coeff(handle_hdf5, pathEs, pathCs, nOrbitals, nOrbFuns):
    """
    MO coefficients are stored in row-major order, they must be transposed
    to get the standard MO matrix.
    :param files: Files to calculate the MO coefficients
    :type  files: Namedtuple (fileXYZ,fileInput,fileOutput)
    :param job: Output File
    :type  job: String
    """
    key = InputKey('orbitals', [path_MO, nOrbitals, nOrbFuns, pathEs, pathCs])

    turbomole2hdf5(handle_hdf5, [key])

    return pathEs, pathCs


def test_store_basisSet():
    """
    Check if the turbomole basis set are read
    and store in HDF5 format.
    """
    pathBasis = 'test_files/basis_turbomole'
    keyBasis = InputKey("basis", [pathBasis])
    try_to_remove(path_hdf5)
    with h5py.File(path_hdf5, chunks=True) as f5:
        try:
            # Store the basis sets
            turbomole2hdf5(f5, [keyBasis])
            os.remove(path_hdf5)
            if not f5["turbomole/basis"]:
                assert False
        except RuntimeError:
            try_to_remove(path_hdf5)
            assert False


def test_store_MO_h5():
    """
    test if the MO are stored in the HDF5 format
    """
    path = join('/turbomole', 'test', 'ethylene')
    pathEs = join(path, 'eigenvalues')
    pathCs = join(path, 'coefficients')
    nOrbitals = 36
    nOrbFuns = 38

    try_to_remove(path_hdf5)
    with h5py.File(path_hdf5, chunks=True) as f5:
        pathEs, pathCs = dump_MOs_coeff(f5, pathEs, pathCs, nOrbitals, nOrbFuns)
        if f5[pathEs] and f5[pathCs]:
            try_to_remove(path_hdf5)
            assert True
        else:
            try_to_remove(path_hdf5)
            assert False


def test_overlap2():
    """
    The overlap matrix must fulfill the following equation C^(+) S C = I
    where S is the overlap matrix, C is the MO matrix and
    C^(+) conjugated complex.
    """
    basis = 'def2-SV(P)'
    mol = readXYZ('test_files/ethylene_au.xyz')
    labels = [at.symbol for at in mol]

    path = join('/turbomole', 'test', 'ethylene')
    pathEs = join(path, 'eigenvalues')
    pathCs = join(path, 'coefficients')
    pathBasis = 'test_files/basis_turbomole'

    nOrbitals = 36
    nOrbFuns = 38

    with h5py.File(path_hdf5, chunks=True) as f5:
        dictCGFs = create_dict_CGFs(f5, pathBasis, basis, 'turbomole', mol)
        pathEs, pathCs = dump_MOs_coeff(f5, pathEs, pathCs, nOrbitals, nOrbFuns)
        trr = f5[pathCs].value
        try_to_remove(path_hdf5)

    cgfsN = [dictCGFs[l] for l in labels]
    dim = sum(len(xs) for xs in cgfsN)
    css = np.transpose(trr)
    mtx_overlap = triang2mtx(calcMtxOverlapP(mol, cgfsN), dim)
    rs = np.dot(trr, np.dot(mtx_overlap, css))

    assert offdiagonalTolerance(rs)
