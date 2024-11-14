"""
_summary_
"""

from copy import deepcopy
from typing import Literal
import sys

import numpy as np
import pandas as pd

from .. import SingleExperiment


            

def combine_experiments(
        experiments: list[SingleExperiment],
        axis: Literal['omics', 'conditions'] = 'omics',
        ) -> pd.DataFrame:
    
    combined_df = None

    if axis == 'omics':
        axis_ = 'index'
    elif axis == 'conditions':
        axis_ = 'columns'
    else:
        raise ValueError(f"'{axis}' not in allowed values for 'axis'.")

    for experiment in experiments:
        if combined_df is None:
            combined_df = experiment.measurements
        else:
            combined_df = pd.concat(
                objs=[
                    combined_df,
                    experiment.measurements,
                ],
                axis=axis_,
                join='inner'
            )

    return combined_df
    


def prep_single_experiment(
        experiment: SingleExperiment,
        filter_threshold: float=0.9,
        cut: bool=False,
        threshold: float=None,
        ) -> tuple[pd.DataFrame, pd.Index, pd.Index]:
    """
    Imports data file(s) into pandas DataFrame. Can handle import from 
    one or two data files. If provided data files are Excel files, the 
    sheets from which to import also have to be defined.

    Parameters
    ----------
    filepath_or_buffer : str | PathLike | Path
        Defines the path to the main file to be imported and used as a 
        basis to calculate associations from. Can be CSV or Excel file.
        If ``filepath_or_buffer`` is an Excel file, ``sheet1`` needs to 
        be defined.
    filepath_or_buffer_2 : str | PathLike | Path, default = None
        Optinonal path definition to a second input file. If 
        ``filepath_or_buffer_2`` is defined, then associations between
        datapoints in ``filepath_or_buffer`` and ``filepath_or_buffer``
        are calculated. Note, if an Excel file is defined as input 
        ``sheet2`` needs to be defined.
    sheet1 : str, default = None
        Used to define the name of the Excel sheet that should be 
        imported. Only used when ``filepath_or_buffer`` points to an 
        Excel file.
    sheet2 : str, default = None
        See ``sheet1``. If ``filepath_or_buffer2`` is defined (and an 
        Excel file) the defined sheet will be imported from there. 
        Otherwise the sheet will be imported from ``filepath_or_buffer``.
    filter_cutoff : float, default = 0.9
        Rows in ``filepath_or_buffer(_2)`` need to contain at least the 
        fraction of ``filter_cutoff`` values that are not `0.0` or 
        `NaN`. Any rows that have less defined values will excluded from
        the calculation of the association value.
    cut : bool, default = False
        Determines if the values in the DataFrame should be binned for 
        further association calculations
    threshold : float, default = None
        Optional argument that defines the threshold values that is used
        for thresholding values.

    Returns
    -------
    tuple[pd.DataFrame, pd.Index, pd.Index]
        Return tuple contains three objects:
            1. a pandas DataFrame object containing transposed data
            2. a pandas Index object containing the index of the 
               DataFrame resulting from importing ``filepath_or_buffer``
            3. a pandas Index object containing the index of the 
               DataFrame resulting from importing 
               ``filepath_or_buffer_2`` or if ``filepath_or_buffer_2``
               was not passed to the function (i.e. `None`) then `None` 
               is returned as the 3rd position of the tuple

    Notes
    -----
    Imports data file(s) into pandas DataFrame object(s). If two data 
    files are provided, the two imported DataFrames are concatenated 
    over their shared columns (conditions). Finally, (depending on the 
    arguments passed to the function call) the resulting DataFrame is:

    - cleaned of low confidence items (rows) that contain to many 0 
      values.
    - binned (necessary for mutual information)
    - thresholded (necessary for Jaccard Index/Similarity)

    """


    experiment.combine_omics(inplace=True)
    experiment.rm_low_confidence_features(
        threshold=filter_threshold,
        inplace=True
        )
    idx1_ret = experiment.omic_x_features
    idx2_ret = experiment.omic_y_features

    df = experiment.measurements
    # this is done if binning is necessary (e.g. for mutual information)
    if cut:
        df = _bin(df=df)

    # this is done if thersholding is necessary (e.g. for jaccard dist)
    if threshold:
        df = _threshold_df(df=df, threshold_rel=threshold)

    return (df.transpose(), idx1_ret, idx2_ret)
    

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