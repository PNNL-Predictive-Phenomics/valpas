"""
Module containing helper functions to deal with data handling (i.e. 
input & output).
"""


import sys

from io import TextIOWrapper
from pathlib import Path
from typing import Literal
from typing import TextIO
from typing import BinaryIO
from os import PathLike

import pandas as pd
import numpy as np

from pandas import ExcelWriter

from valpas.utils.post_processing import beautify_series
from valpas.utils.post_processing import sort_associations


def reduce_to_shared_conditions(
        df_1: pd.DataFrame, df_2: pd.DataFrame
        ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    (!DEPRECATED!)
        
    This function operates on already inmported and transposed 
    pd.DataFrame objects. This means that the individual conditions in 
    the raw data (columns) are represented as rows (index).  
    """
    intersect = df_1.columns.intersection(df_2.columns)
    df_1_ret = df_1.filter(items=intersect, axis="columns")
    df_2_ret = df_2.filter(items=intersect, axis="columns")

    df_1_ret.replace(0, np.nan, inplace=True)
    df_1_ret.dropna(axis="columns", how="all", inplace=True)
    df_1_ret.replace(np.nan, 0, inplace=True)

    df_2_ret.replace(0, np.nan, inplace=True)
    df_2_ret.dropna(axis="columns", how="all", inplace=True)
    df_2_ret.replace(np.nan, 0, inplace=True)
   
    return (df_1_ret, df_2_ret)


def export_xlsx(filepath_or_buffer: str | PathLike | Path,
        dfs: pd.DataFrame | list[pd.DataFrame],
        sheets: str | list[str]) -> None:
    
    filepath_or_buffer_ = filepath_or_buffer
    if not isinstance(filepath_or_buffer_, (str, PathLike, Path)):
        raise TypeError(
            f"filepath_or_buffer must be of type str, PathLike or Path. "
            f"Supplied argument is of type {type(filepath_or_buffer_)}."
        )
    if isinstance(dfs, str) and isinstance(sheets, str):
        try:
            with ExcelWriter(filepath_or_buffer_, mode='a') as writer:
                dfs.to_excel(writer, sheet_name=sheets)
        except FileNotFoundError:
            with ExcelWriter(filepath_or_buffer_, mode='w') as writer:
                dfs.to_excel(writer, sheet_name=sheets)
    elif isinstance(dfs, list) and isinstance(sheets, list):
        if len(dfs) != len(sheets):
            raise ValueError(
                f"Number of DataFrames to write to {filepath_or_buffer_} does "
                "not match number of supplied Sheet names."
            )
        try:
            with ExcelWriter(filepath_or_buffer_, mode='a', if_sheet_exists='new') as writer:
                for i in range(0, len(dfs)):
                    dfs[i].to_excel(writer, sheet_name=sheets[i])
        except FileNotFoundError:
            with ExcelWriter(filepath_or_buffer_, mode='w') as writer:
                for i in range(0, len(dfs)):
                    dfs[i].to_excel(writer, sheet_name=sheets[i])
    elif not (isinstance(dfs, list) or isinstance(dfs, str)):
        raise TypeError(
            f"dfs must be either of type str or list. "
            f"Suppied dfs is of type {type(dfs)}."
        )
    elif not (isinstance(sheets, list) or isinstance(sheets, str)):
        raise TypeError(
            f"sheets must be either of type str or list. "
            f"Suppied sheets is of type {type(sheets)}."
        )
    else:
        raise TypeError(
            "dfs and sheets must type match."
        )
        

def import_csv(filepath_or_buffer: str | PathLike | TextIO) -> pd.DataFrame:
    """
    Imports a csv file. Returns a pandas DataFrame object containing 
    the data.

    Input can be either:
      - a string that is the path to the infile 
      - a path like object (e.g. generated via `os.path`) to the infile
      - a file handle (e.g. opened via `argparse.FileType`)
    """
    filepath_or_buffer_ = filepath_or_buffer
    if isinstance(filepath_or_buffer_, (str, PathLike, TextIOWrapper)):
        try:
            df = pd.read_csv(
                filepath_or_buffer=filepath_or_buffer_,
                index_col=0,
            )
        except FileNotFoundError as err:
            raise FileNotFoundError(err)
    else:
        error = (
            f"filepath_or_buffer must be of type str, PathLike or TextIO. "
            f"Supplied argument is of type {type(filepath_or_buffer_)}."
            )
        raise TypeError(error)
    
    return df


def import_xls(
        filepath_or_buffer: str | PathLike | BinaryIO,
        sheet: str
        ) -> pd.DataFrame:
    """
    Imports a sheet within a xlsx file into a pandas DataFrame.

    Input for filepath_or_buffer can be either:
      - a string that is the path to the infile 
      - a path like object (e.g. generated via `os.path`) to the infile
      - a file handle (e.g. opened via `argparse.FileType`)
    
    Requires the name of the sheet to be imported (`sheet`).
      
    Raises:
        - FileNotFoundError: If supplied path to file does not resolve
        to a file
        - TypeError: If the supplied filepath_or_buffer is not an
        instance of `str`, `PathLike` or `BinaryIO`

    Returns:
        - `pandas.DataFrame` containing the contents of the defined
        sheet
    """
    filepath_or_buffer_ = filepath_or_buffer
    if isinstance(filepath_or_buffer_, (str, PathLike, BinaryIO)):
        try:
            df = pd.read_excel(
                io=filepath_or_buffer_,
                sheet_name=sheet,
                index_col=0,
            )
        except FileNotFoundError as err:
            raise FileNotFoundError(err)
    else:
        error = (
            f"filepath_or_buffer must be of type str, PathLike or TextIO. "
            f"Supplied argument is of type {type(filepath_or_buffer_)}."
            )
        raise TypeError(error)
    
    return df


def prep_data(
        filepath_or_buffer: str | PathLike | Path,
        filepath_or_buffer_2: (str | PathLike | Path )=None,
        sheet1: str=None,
        sheet2: str=None,
        filter_cutoff: float=0.9,
        cut: bool=False, threshold: float=None
        ) -> tuple[pd.DataFrame, pd.Index, pd.Index]:
    """
    Imports data file(s) from file_path_or_buffer into pandas DataFrame
    object(s). If two data files are provided, the two imported 
    DataFrames are concatenated over their shared columns (conditions). 
    Finally, (depending on the arguments passed to the function call) 
    the resulting DataFrame is:

    - cleaned of low confidence items (rows) that contain to many 0 
      values.
    - binned (necessary for mutual information)
    - thresholded (necessary for Jaccard Index/Similarity)

    Returns a tuple containing:
    
    1. a pandas DataFrame object containing transposed data
    2. a pandas Index object containing the index of the DataFrame
    resulting from importing `filepath_or_buffer`
    3. a pandas Index object containing the index of the DataFrame
    resulting from importing `filepath_or_buffer_2` or if 
    `filepath_or_buffer_2` was not passed to the function (i.e. `None`) 
    then `None` is returned as the 3rd position of the tuple
    """

    if not isinstance(filepath_or_buffer, Path):
        filepath_or_buffer = Path(filepath_or_buffer).absolute()

    f_suffix = filepath_or_buffer.suffix
    if f_suffix == '.xlsx':
        if sheet1 is None:
            raise ValueError(
                f"No Sheet name provided for file {filepath_or_buffer}"
            )
        df = import_xls(filepath_or_buffer=filepath_or_buffer, sheet=sheet1)
    elif f_suffix == '.csv':
        df = import_csv(filepath_or_buffer)
    else: 
        raise ValueError(
            f"Supplied file is of type '{f_suffix}'. "
            "Expected '.csv' or '.xlsx'."
         )
    
    idx1 = df.index
    idx2 = None

    if filepath_or_buffer_2 is not None:
        if not isinstance(filepath_or_buffer_2, Path):
            filepath_or_buffer_2 = Path(filepath_or_buffer_2).absolute()

        f_suffix = filepath_or_buffer_2.suffix
        if f_suffix == '.xlsx':    
            if sheet2 is None:
                raise ValueError(
                    f"No Sheet name provided for file {filepath_or_buffer_2}"
                )
            df_2 = import_xls(
                filepath_or_buffer=filepath_or_buffer_2, sheet=sheet2
                )
        elif f_suffix == '.csv':
            df_2 = import_csv(filepath_or_buffer_2)
        else:
            raise ValueError(
                f"Supplied file is of type '{f_suffix}'. "
                "Expected '.csv' or '.xlsx'."
            )
        idx2 = df_2.index
        df = pd.concat([df, df_2], join='inner')


    # removing low confidence items
    df, index = remove_low_confidence_items(df=df, cutoff=filter_cutoff)
    if len(index.values) > 0:
        print("Removed items: ", end="", file=sys.stderr)
        print(*index.values, sep=", ", file=sys.stderr)
        idx1_ret = idx1.difference(index)
        idx1_ret.name = idx1.name
        if idx2 is not None:
            idx2_ret = idx2.difference(index)
            idx2_ret.name = idx2.name
        else:
            idx2_ret = idx2
    # this is done if binning is necessary (e.g. for mutual information)
    if cut:
        df = bin(df=df)

    # this is done if thersholding is necessary (e.g. for jaccard dist)
    if threshold:
        df = threshold_df(df=df, threshold_rel=threshold)

    if idx2 is None:
        return (df.transpose(), idx1_ret, None)
    else:
        return (df.transpose(), idx1_ret, idx2_ret)

def bin(df: pd.DataFrame, num_bins: int=2) -> pd.DataFrame:
    df = df.apply(lambda x: pd.cut(x, bins=num_bins, labels=range(0,num_bins)), axis=0)
    return df


def threshold_df(df: pd.DataFrame, threshold_rel: float=0.5) -> pd.DataFrame:
    """
    function to threshold a pd.DataFrame containing aboslute or relative 
    abunances for items (rows, e.g. metabolites) across different 
    conditions (columns).

    Returns a truth table encoded with 0s and 1s denoting if the value 
    falls above the determined threshold. Note that NA values in the DF 
    passed to the function will automatically be cast to 'False' / 0
    """

    # it is assumed that the DF that is passed to the function will not
    # contain NaNs/NAs in place of 0s. If this is not the case the if 
    # statement below is triggered and 0s are replaced with NaN such 
    # that they don't interfere with calulating the threshold
    if df.eq(0).any(axis=None):
        df.replace(0, np.nan, inplace=True)
    
    # creating a Series containing thresholds for individual items
    # currently the threshold is calculated per item across different
    # conditions (axis = 1).
    s_thresh = (
        df.min(axis=1)
        + (df.max(axis=1) - df.min(axis=1)) * threshold_rel
    )
    
    # generating the return DataFrame
    # ATTN: DataFrame.ge() will return 'False' for NaNs
    # An additional step (see mask) is needed to cast NaNs back into 
    # the return DF.
    df_ret = (
        df
        .ge(s_thresh, axis='index') # check if cell satisfies the threshold
        .astype(int) # casts the boolean returned by `.gt()` to int(0,1)
        )
    df_ret.mask(df.isna(), df, inplace=True)
    
    return df_ret


def remove_low_confidence_items(df: pd.DataFrame, cutoff: float=0.9,
        drop_na_cols: bool=True) -> tuple[pd.DataFrame, pd.Index]:
    """
    Takes a pd.DataFrame and removes low confidence (to many NAs) 
    items (rows) from the DataFrame. The `cutoff` argument passed to 
    the function determines how complete (i.e. the fraction of non-NA 
    values) an item (row) needs to be to retained in the DataFrame.
    Additionally, the function can be told to keep any columns that 
    are completely populated with NAs/0s as a result of removing items 
    from the DataFrame. By default those columns are dropped.
    """
    
    # treating '0' as NaNs for easier counting of missing values
    df.replace(0, np.nan, inplace=True)

    # creating an index of rows (items) to filter i.e. finding the rows
    # that where the fraction of NAs is larger than 1-cutoff
    s = (
        (df.isna() # create truth table whether values is NaN
         .sum(axis=1) # sum "True" iterating over columns for each row
         /df.shape[1]) # divide by the number of columns
         .gt(1-cutoff) # check if fraction of NAs (in row) is > cutoff
        )
    index = s[s].index # creating the actual index (i.e. which rows to drop)

    # filter the DataFrame
    df_filtered = df.drop(
        labels=index, # using the defined index from above
        axis='index', # drop based on rows
        )
    
    # if the above procedure generated columns (conditions) that contain
    # only NAs as values, those will be removed. The behaviour can be 
    # toggled with a function argument (default = True)
    if drop_na_cols:
        df_filtered.dropna(axis="columns", how="all", inplace=True)
    
    # return both the filtered df and the index of dropped items
    return (df_filtered, index)


def write_outfile(df: pd.DataFrame, file_handle: str, reduced_output: bool=False,
                  output_type: Literal[
                      'sorted_list', 'correlation_matrix'
                      ]='sorted_list') -> None:
    """
    Takes a `pd.DataFrame` object and writes it to a file handle. This 
    can be either a file or sys.stdout.
    """
    if output_type == 'sorted_list':
        df = beautify_series(df=df)
        df.to_csv(file_handle, encoding='utf-8', index=False)
    elif output_type == 'correlation_matrix':
        df.to_csv(file_handle, encoding='utf-8')


def import_asssociation_matrix(file_handle: str) -> pd.DataFrame:
    """
    Imports a saved correlation / association matrix saved by 
    `valpas.utils.write_outfile()` into a `pd.DataFrame` object and 
    returns it.

    Can for example be used to read in data necessary to plot a heatmap 
    via the `valpas.visualize.heatmap` module. 
    """
    df = pd.read_csv(
        filepath_or_buffer=file_handle,
        index_col=0,
        header=0,
        )
    return df
