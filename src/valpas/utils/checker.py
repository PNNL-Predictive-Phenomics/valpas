"""
collection of type checker / validater functions
"""


import argparse
from os import PathLike
from pathlib import Path
import sys

def check_file(path: str | PathLike | Path) -> str:
    

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


def check_cutoff_range(x):
    try:
        x = float(x)
    except ValueError:
        raise argparse.ArgumentTypeError(f'{x} not a float')
    if x < 0.0 or x > 1.0:
        raise argparse.ArgumentTypeError(f'{x} not in range [0.0, 1.0]')
    return x