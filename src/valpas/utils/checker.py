"""
collection of type checker / validater functions
"""

import argparse
from os import PathLike
from pathlib import Path

def check_infile(path: str | PathLike | Path) -> str:
    """
    Checks whether a give infile exsits. Returns the absolute path to 
    the file if the file exsits. Can be used in conjuction with the 
    ``type`` paramater in ``argparse.ArgumentParser.add_argument``.

    Parameters
    ----------
    path : str | PathLike | Path
        A path like object that contains the file path that should be 
        checked for existence.

    Returns
    -------
    str
        Returns the absolute Path to the file if the file exists.

    Raises
    ------
    TypeError
        If the passed ``path`` argument is not in a path like format
    FileNotFoundError
        If the file is not found / does not exist
    ValueError
        If the supplied file is not a defined type (in this case .csv
        or .xlsx).
    """

    if not isinstance(path, (str, PathLike, Path)):
        error = (
            f"filepath_or_buffer must be of type str, PathLike or TextIO. "
            f"Supplied argument is of type {type(filepath_or_buffer_)}."
            )
        raise TypeError(error)
    
    if not isinstance(path, Path):
        abs_path = Path(path).absolute()
    else:
        abs_path = path.absolute()

    if not abs_path.is_file():
        raise FileNotFoundError(
            f"Supplied file '{abs_path}' does not exist."
            )
    else:
        suffix = abs_path.suffix
        if suffix in ['.csv', '.xlsx']:
            return abs_path
        else:
            raise ValueError(
                f"Supplied file is of type '{suffix}'. "
                f"Expected '.csv' or '.xlsx'."
                )

def check_outfile(path: str | PathLike | Path) -> str:
    """
    Checks whether the outfile passed to the function satisfies certain
    criteria. Returns the absolute path to the file. Can be used in
    conjuction with the ``type`` paramater in 
    ``argparse.ArgumentParser.add_argument``.

    Parameters
    ----------
    path : str | PathLike | Path
        A path like object that contains the file path that should be 
        checked for compliance.

    Returns
    -------
    str
        Returns the absolute Path to the file if the file is compliant.

    Raises
    ------
    TypeError
        If the passed ``path`` argument is not in a path like format
    ValueError
        If the supplied file is not a defined type (in this case .csv
        or .xlsx).
    """

    if not isinstance(path, (str, PathLike, Path)):
        error = (
            f"filepath_or_buffer must be of type str, PathLike or TextIO. "
            f"Supplied argument is of type {type(filepath_or_buffer_)}."
            )
        raise TypeError(error)
    
    if not isinstance(path, Path):
        abs_path = Path(path).absolute()
    else:
        abs_path = path.absolute()

    suffix = abs_path.suffix
    if suffix in ['.csv', '.xlsx']:
        return abs_path
    else:
        raise ValueError(
            f"Supplied file is of type '{suffix}'. "
            f"Expected '.csv' or '.xlsx'."
            )


def check_cutoff_range(x: any) -> float:
    """
    Checks if the supplied value is in a certain float range.

    Parameters
    ----------
    x : Any
        The supplied value that should be checked whether it falls in 
        a predefined float range.

    Returns
    -------
    float
        Returns the value cast to float.

    Raises
    ------
    argparse.ArgumentTypeError
        If ``x`` can not be cast to float or is not with in the defined
        float range.
    """
    try:
        x = float(x)
    except ValueError:
        raise argparse.ArgumentTypeError(f'{x} not a float')
    if x < 0.0 or x > 1.0:
        raise argparse.ArgumentTypeError(f'{x} not in range [0.0, 1.0]')
    return x