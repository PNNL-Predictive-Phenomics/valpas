"""
Module containing helper functions to deal with data handling (i.e. 
input & output).
"""

import pandas as pd
import numpy as np
import sys

from typing import Literal

from valpas.utils.post_processing import beautify_series
from valpas.utils.post_processing import sort_associations

def prep_data(file_handle: str, cut: bool=False, threshold: bool=False,
              filter_cutoff: float=None) -> pd.DataFrame:
    """
    Imports csv file from file_handle into pandas DataFrame object and 
    transposes the DataFrame such that row are experiment conditions 
    and columns are identifier (e.g. protein identifier or metabolite).

    Returns pandas DataFrame object containing transposed data.
    """

    # TODO: more robust file path / file object handling

    df = pd.read_csv(
        filepath_or_buffer=file_handle,
        index_col=0
    )

    # if a filtering cut if is selected the filtering logic is executed
    if filter_cutoff is not None:
        df, index = filter_for_missing_values(df=df, cutoff=filter_cutoff)
        if len(index.values) > 0:
            print("Removed items: ", end="", file=sys.stderr)
            print(*index.values, sep=", ", file=sys.stderr)
    
    # this is done if binning is necessary (e.g. for mutual information)
    if cut:
        df = bin(df=df)

    # this is done if thersholding is necessary (e.g. for jaccard dist)
    if threshold:
        df = threshold_df(df=df)

    return df.transpose()

def bin(df: pd.DataFrame, num_bins: int=2) -> pd.DataFrame:
    df = df.apply(lambda x: pd.cut(x, bins=num_bins), axis=0)
    return df

def threshold_df(df: pd.DataFrame) -> pd.DataFrame:

    df = df.transpose()

    # replacing 0s with NaN such that they don't interfere with
    # calulating the threshold
    df.replace(0, np.nan, inplace=True)

    # creating a Series containing thersholds for individual instances
    # currently the threshold is calculated per instance & across
    # different conditions (axis = 0)
    s_thresh = (df.min(axis=0)) + (((df.max(axis=0)) - (df.min(axis=0))) / 2)
    
    # generating the return DataFrame
    df_ret = (
        df
        .gt(s_thresh) # checks if the cell satisfies the thershold
        .astype(int) # casts the boolean returned by `.gt()` to int(0,1)
        ).transpose() # transpose to return df in original orientation
    
    return df_ret

def filter_for_missing_values(df: pd.DataFrame, cutoff: float) -> tuple[
        pd.DataFrame, pd.Index]:
    
    # treating '0' as NaNs for easier counting of missing values
    df.replace(0, np.nan, inplace=True)

    df = df.transpose()

    # creating an index of rows to filter
    s = (((
        df[df.columns] # per column
        .notna().sum()) # count all NaNs
        /df.shape[0]) # divide by the total number of rows
        .le(cutoff) # check if fraction is less or equal than cutoff
    )
    index = s[s].index # creating the actual index

    # filter the DataFrame
    df_filtered = df.drop(
        labels=index, # using the defined index from above
        axis='columns', # drop based on columns
        ).transpose()
    
    df_filtered.replace(np.nan, 0, inplace=True) # necessary for nan rows
    
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
        s_sorted = sort_associations(df=df, reduced_output=reduced_output)
        df = beautify_series(s_sorted)
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
