"""
_summary_
"""

from copy import deepcopy
from typing import Literal
import sys

import numpy as np
import pandas as pd


def _bin(df: pd.DataFrame, num_bins: int=2) -> pd.DataFrame:
    """
    Helper function for binning the values of rows in a DataFrame

    Parameters
    ----------
    df : pandas.DataFrame
        DataFrame with values to be binned
    num_bins: int, default = 2
        Defines the number of bins.

    Returns
    -------
    pandas.DataFrame
        Return DataFrame with binned rows.
    """
    df = df.apply(
        lambda x: pd.cut(
            x, bins=num_bins,
            labels=range(0,num_bins)
            ),
        axis=0
        )
    return df


def _threshold_df(df: pd.DataFrame, threshold_rel: float=0.5) -> pd.DataFrame:
    """
    Thresholds rows in a pd.DataFrame containing aboslute or relative 
    abunances for items (rows, e.g. metabolites) across different 
    conditions (columns).

    Parameters
    ----------
    df : pandas.DataFrame
        DataFrame that contains values that should be thresholded
    threshold_rel : float, default=0.5
        Relative threshold, that is to be used for the internal
        thresholding function. 

    Returns
    -------
    pandas.DataFrame
        A truth table encoded with 0s and 1s denoting if the value 
        falls above the determined threshold.

    Notes
    -----
    NA values in the DataFrame passed to the function will automatically
    be cast to 'False' / 0.
    
    Thresholding is done relative to the values recorded in the rows,
    i.e.

    .. math::

        t = min(v_{ij}) + (max(v_{ij}) - min(v_{ij})) * threshold\\_rel
    
    for :math:`v_{ij}` is any value :math:`v_i` in :math:`Row` :math:`j`
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


def _remove_low_confidence_features(df: pd.DataFrame, threshold: float=0.9,
        drop_na_cols: bool=True) -> tuple[pd.DataFrame, pd.Index]:
    """
    Removes low confidence (to many NAs) 
    items (rows) from the DataFrame. The `cutoff` argument passed to 
    the function determines how complete (i.e. the fraction of non-NA 
    values) an item (row) needs to be to retained in the DataFrame.
    Additionally, the function can be told to keep any columns that 
    are completely populated with NAs/0s as a result of removing items 
    from the DataFrame. By default those columns are dropped.

    Parameters
    ----------
    df : pandas.DataFrame
        The DataFrame that should be filtered to remove low confidence
        items.
    cutoff : float, default=0.9
        The cutoff that determines if an item is considered a low 
        confidence item, i.e. if less than a fraction ``cutoff`` of 
        data points for an item are not NaN the item is considered low 
        confidence.
    drop_na_cols : bool, default=True
        If the removal of low confidence items generates new columns in 
        the DataFrame that are entirely made up of NaN values those 
        columns will be dropped if ``drop_na_cols`` is set to `True`.

    Returns
    -------
    tuple[pandas.DataFrame, pandas.Index]
        The return tuple contains two objects:
            1. The "clean" DataFrame
            2. An index of all dropped items

    """
    
    # treating '0' as NaNs for easier counting of missing values
    df.replace(0, np.nan, inplace=True)

    # creating an index of rows (items) to filter i.e. finding the rows
    # that where the fraction of NAs is larger than 1-cutoff
    s = (
        (df.isna() # create truth table whether values is NaN
         .sum(axis=1) # sum "True" iterating over columns for each row
         /df.shape[1]) # divide by the number of columns
         .gt(1-threshold) # check if fraction of NAs (in row) is > cutoff
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