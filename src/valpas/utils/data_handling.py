"""
Module containing helper functions to deal with data handling (i.e. 
input & output).
"""

import pandas as pd
import numpy as np
import sys

from valpas.utils.post_processing import beautify_series
from valpas.utils.post_processing import sort_associations

def prep_data(file_handle: str, cut=False, filter_cutoff=None) -> pd.DataFrame:
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
        df.apply(lambda x: pd.cut(x, bins=100), axis=0)

    df_t = df.transpose()

    return df_t

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

def write_outfile(df: pd.DataFrame, file_handle: str,
                  output_type: str) -> None:
    """
    Takes a `pd.DataFrame` object and writes it to a file handle. This 
    can be either a file or sys.stdout.
    """
    if output_type == 'sorted_list':
        s_sorted = sort_associations(df)
        df = beautify_series(s_sorted)
        df.to_csv(file_handle, encoding='utf-8', index=False)
    elif output_type == 'correlation_matrix':
        df.to_csv(file_handle, encoding='utf-8')
