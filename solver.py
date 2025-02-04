"""Main file."""

import calendar
import csv
import gc
import glob
import os
import pathlib
import platform
import sys
import time
from collections import defaultdict
from typing import Dict, Union

import numpy as np
import psutil
import scipy as sp
import scipy.io as sio
import scipy.sparse.linalg

try:
    import pypardiso
except ImportError as e:
    print("Module PyPardiso not available, cannot use Intel MKL.")


class InvalidMatrixFormat(Exception):
    """Exception raised if a matrix is in an invalid format."""
    pass


def load_matrix(path: str, matrix_format: str):
    """Load a matrix in Matrix Market format from the data folder.

    Parameters
    ----------
    path: str
        path of the matrix file
    
    matrix_format: str
        {'csc', 'csr'} should be 'csc' if using UMFPACK of SuperLU,
        or 'csr' if using Intel MKL
    
    Returns
    -------
    m: scipy.sparse matrix
        the loaded matrix in 'csr' or 'csc' format
    """
    if matrix_format == 'csr':
        return sio.mmread(path).tocsr()
    elif matrix_format == 'csc':
        return sio.mmread(path).tocsc()
    else:
        raise ValueError(
            "Invalid argument matrix_format. Should be one of 'csr', 'csc', got {} instead.".
            format(matrix_format))


def create_b(matrix):
    """Create the rhs vector for the system A*xe = b where
    xe is a vector of only ones, with shape (A.shape[1], 1).
    """
    xe = np.ones((matrix.shape[1], 1))
    b = matrix @ xe  # use @ because np.dot fails with sparse matrices
    return b


def get_relative_error(xe, x):
    """Get the relative error between two solutions, the exact xe
    and the computed x."""
    relative_error = np.linalg.norm(xe - x, ord=2) / np.linalg.norm(xe, ord=2)
    return float(relative_error)


def solve_with_profiling(A,
                         b,
                         matrix_name,
                         matrix_type,
                         solver_library='umfpack'):
    """Perform a benchmark on the given matrix-rhs for solving A*xe = b,
    where xe is assumed to be a vector of ones [1, 1,..., 1].T

    Parameters
    ----------
    A: scipy.sparse matrix
        the coefficient matrix
    
    b: numpy.array
        right-hand side of A*xe = b, where xe is a vector of ones
        [1, 1, 1,..., 1].T
    
    Returns
    -------
    result: Dict
        dictionary with these key-value pairs:
            'matrix_name': name of the matrix
            'start_time': int, start time in UNIX format
            'end_time': int, end time in UNIX format
            'relative_error': float, relative error computed as norm2(xe - x)/norm2(xe)
            'solver_library': str, value of the solver library
            'matrix_dimensions': str, value of NxM
            'umfpack_error': 1 if UMFPACK raised MemoryError, else 0
    """
    umfpack_mem_error = False

    if solver_library == 'mkl':
        start_time = time.time()

        x = pypardiso.spsolve(A, b)

        end_time = time.time()
    elif solver_library == 'superlu':
        start_time = time.time()

        x = scipy.sparse.linalg.spsolve(A, b, use_umfpack=False)

        end_time = time.time()
    elif solver_library == 'umfpack':
        start_time = time.time()

        try:
            x = scipy.sparse.linalg.spsolve(A, b, use_umfpack=True)
        except MemoryError:
            print("Got MemoryError for UMFPACK!")
            umfpack_mem_error = True

        end_time = time.time()
    else:
        raise ValueError(
            "Wrong value for parameter 'solver_library', shoud be in {'mkl', 'umfpack', 'superlu'}, got {} instead.".
            format(solver_library))

    xe = np.ones((A.shape[1], ))
    relative_error = get_relative_error(xe, x) if not umfpack_mem_error else -1

    del xe
    gc.collect()

    return {
        'matrix_name': matrix_name,
        'matrix_type': matrix_type,
        'matrix_dimensions': "{}x{}".format(A.shape[0], A.shape[1]),
        'start_time': start_time,
        'end_time': end_time,
        'relative_error': relative_error,
        'solver_library': solver_library,
        'umfpack_error': 1 if umfpack_mem_error else 0,
    }


def main(matrices, matrices_type: str, library='umfpack', num_runs=30):
    """Launch analysis for every matrix.
    Makes num_runs different runs loading each matrix every time to prevent
    smart caching from the solver libraries.

    Parameters
    ----------
    matrices: List[str]
        list of relative paths of matrix files
    
    library: str
        one of {'mkl', 'umfpack', 'superlu'}, defines the solver library
        to be used
    
    num_runs: int
        number of runs
    
    Returns
    -------
    results: Dics[str, List]
        dictionary with matrix names as keys, and list of result for each run
        as values
    """
    print("Discovered these matrices:")
    for m in matrices:
        print("{}".format(m))

    results = []

    for i in range(num_runs):
        print("\n## ------------------------ ##")
        print("Run {}/{} with all matrices".format(i + 1, num_runs))

        for index, path in enumerate(matrices):
            matrix_name = path.split('/')[-1]
            if library == 'mkl':
                A = load_matrix(path, 'csr')
            elif library == 'umfpack' or library == 'superlu':
                A = load_matrix(path, 'csc')

            print("Iter {}, matrix '{}' {}/{}, shape {}".format(
                i + 1, matrix_name, index + 1, len(matrices), A.shape))
            b = create_b(A)

            result = solve_with_profiling(
                A, b, matrix_name, matrices_type, solver_library=library)
            results.append(result)

            del A, b
            gc.collect()
            print("GC collection finished, next run...")

    print("\nDone!")
    return results


def log_results(results: Dict[str, Union[str, int]],
                filename: str = 'python-result-log'):
    """Write the results on a file."""
    if not results:
        return None

    csv_fields = [
        'matrix',
        'dimensions',
        'type',
        'start_time',
        'end_time',
        'rel_error',
        'system',
        'library',
        'umfpack_error',
    ]

    system_type = 'ubuntu' if platform.system == 'Linux' else 'windows'

    # se non esiste il file, crealo con le colonne giuste
    filepath = './{}-{}.csv'.format(system_type, filename)
    myfile = pathlib.Path(filepath)
    if not myfile.is_file():
        with open(filepath, 'w') as outfile:
            outfile.write(",".join(csv_fields) + "\n")

    csv_rows = []
    for result in results:
        row = {
            'matrix': result['matrix_name'],
            'dimensions': result['matrix_dimensions'],
            'type': result['matrix_type'],
            'start_time': result['start_time'],
            'end_time': result['end_time'],
            'rel_error': result['relative_error'],
            'system': system_type,
            'library': result['solver_library'],
            'umfpack_error': result['umfpack_error'],
        }
        csv_rows.append(row)

    with open(filepath, 'a') as outfile:
        print("Saving to {}".format(filepath))
        w = csv.DictWriter(outfile, delimiter=',', fieldnames=csv_fields)
        for row in csv_rows:
            w.writerow(row)
    print("Saved!")


if __name__ == '__main__':
    if len(sys.argv) == 3:
        library = sys.argv[1]

        if library not in {'umfpack', 'superlu', 'mkl'}:
            raise ValueError(
                "Accepted values for library are: 'mkl', 'superlu', 'umfpack', got {} instead.".
                format(library))

        n_runs = int(sys.argv[2])

        if not (n_runs >= 1):
            raise ValueError(
                "Number of runs must be >= 1, got {} instead".format(n_runs))
    else:
        raise ValueError(
            "Please, provide a choice for the solver library an run number:" +
            "you should call this script as 'python scratch.py solver runs' where solver is {'mkl', 'superlu', 'umfpack'} and runs an integer > 0."
        )

    print("\n------------------------------")
    print("Current process PID is: {}".format(os.getpid()))
    print("------------------------------\n")

    ready = False
    while not ready:
        user_is_ready = input("Are you ready? (y/n)")
        if user_is_ready == 'y':
            ready = True

    symmetric_matrices = sorted(glob.glob('./data/matrici_def_pos/*.mtx'))
    results_sdf = main(
        symmetric_matrices, 'def_pos', library=library, num_runs=n_runs)

    unsym_matrices = sorted(glob.glob('./data/matrici_non_def_pos/*.mtx'))
    results_unsym = main(
        unsym_matrices, 'non_def_pos', library=library, num_runs=n_runs)

    log_results(results_sdf, filename='python-result-log')
    log_results(results_unsym, filename='python-result-log')
