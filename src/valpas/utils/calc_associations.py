"""
Module containing functions for the calculation of associations used by 
ValPAS.
"""


from os import PathLike
from pathlib import Path
from typing import Literal

import sys

import numpy as np
from numpy.typing import ArrayLike
import pandas as pd

from scipy.spatial.distance import cosine
from sklearn.metrics import mutual_info_score
from sklearn.metrics import jaccard_score

from valpas.utils.data_handling import prep_data
from valpas.utils.b_spline import mutual_information


def calc_association(
        filepath_or_buffer: str | PathLike | Path,
        filepath_or_buffer_2: (str | PathLike | Path)=None,
        sheet1: str=None,
        sheet2: str=None,
        association: Literal[
            'pearson', 'spearman',
            'jaccard_similarity', 'jaccard_distance', 'jaccard_index',
            'mutual_information',
            'cosine_similarity', 'cosine_distance',
            ]='pearson',
        filter_cutoff: float=0.9,
        threshold: float=None,
    ) -> dict:

    if association in ['pearson', 'spearman']:
        try:
            df_assoc, df_counts, idx1, idx2 = _calc_correlation(
                filepath_or_buffer=filepath_or_buffer,
                filepath_or_buffer_2=filepath_or_buffer_2,
                sheet1=sheet1,
                sheet2=sheet2,
                corr_func=association,
                filter_cutoff=filter_cutoff,
            )
        except ValueError as e:
            sys.exit(e)
    elif association in ['cosine_similarity', 'cosine_distance']:
        try:
            df_assoc, df_counts, idx1, idx2 = _calc_cosine_dist(
                filepath_or_buffer=filepath_or_buffer,
                filepath_or_buffer_2=filepath_or_buffer_2,
                sheet1=sheet1,
                sheet2=sheet2,
                filter_cutoff=filter_cutoff,
                threshold=threshold
            )
        except ValueError as e:
            sys.exit(e)
        if association == 'cosine_similarity':
            # converting distance to similarity
            df_assoc = df_assoc.rsub(1)

    elif association in ['jaccard_similarity', 'jaccard_distance',
                         'jaccard_index']:
        if threshold is None:
            threshold = 0.5
        try:
            df_assoc, df_counts, idx1, idx2 = _calc_jaccard_sim(
                filepath_or_buffer=filepath_or_buffer,
                filepath_or_buffer_2=filepath_or_buffer_2,
                sheet1=sheet1,
                sheet2=sheet2,
                filter_cutoff=filter_cutoff,
                threshold=threshold
            )
        except ValueError as e:
            sys.exit(e)
        if association == 'jaccard_distance':
            # converting jaccard similarity to distance
            df_assoc = df_assoc.rsub(1)
    
    elif association == 'mutual_information':
        try:
            df_assoc, df_counts, idx1, idx2 = _calc_mut_info(
                filepath_or_buffer=filepath_or_buffer,
                filepath_or_buffer_2=filepath_or_buffer_2,
                sheet1=sheet1,
                sheet2=sheet2,
                filter_cutoff=filter_cutoff
            )
        except ValueError as e:
            sys.exit(e)

    else:
        raise ValueError(f"Association type {association} not supported!")
    
    ret = {
        'df_assoc': df_assoc, 'df_counts': df_counts,
        'idx1': idx1, 'idx2': idx2
        }
    return ret


def _calc_correlation(
        filepath_or_buffer: str | PathLike | Path,
        filepath_or_buffer_2: (str | PathLike | Path)=None,
        sheet1: str=None,
        sheet2: str=None,
        corr_func: Literal['pearson', 'kendall', 'spearman']='pearson',
        filter_cutoff: float=0.9,
    ) -> pd.DataFrame:
    
    try:
        df, idx1, idx2 = prep_data(
            filepath_or_buffer=filepath_or_buffer,
            filepath_or_buffer_2=filepath_or_buffer_2,
            sheet1=sheet1,
            sheet2=sheet2,
            filter_cutoff=filter_cutoff)
    except ValueError as e:
        raise e
    df_corr = df.corr(method=corr_func)
    df_counts = df.corr(method=count_vals_in_association)

    return df_corr, df_counts, idx1, idx2


def _calc_cosine_dist(
        filepath_or_buffer: str | PathLike | Path,
        filepath_or_buffer_2: (str | PathLike | Path)=None,
        sheet1: str=None,
        sheet2: str=None,
        filter_cutoff: float=0.9,
        threshold: float=None
        ) -> pd.DataFrame:
    try:
        df, idx1, idx2 = prep_data(
            filepath_or_buffer=filepath_or_buffer,
            filepath_or_buffer_2=filepath_or_buffer_2,
            sheet1=sheet1,
            sheet2=sheet2,
            filter_cutoff=filter_cutoff,
            threshold=threshold
        )
    except ValueError as e:
        raise e
    df_cos_dist = df.corr(method=cosine)
    if threshold is None:
        df_counts = df.corr(method=count_vals_in_association)
    else:
        df_counts = df.corr(method=count_vals_in_thresholded_association)

    return df_cos_dist, df_counts, idx1, idx2


def _calc_jaccard_sim(
        filepath_or_buffer: str | PathLike | Path,
        filepath_or_buffer_2: (str | PathLike | Path)=None,
        sheet1: str=None,
        sheet2: str=None,
        filter_cutoff: float=0.9,
        threshold: float=0.5
        ) -> pd.DataFrame:
    
    try:
        df, idx1, idx2 = prep_data(
            filepath_or_buffer=filepath_or_buffer,
            filepath_or_buffer_2=filepath_or_buffer_2,
            sheet1=sheet1,
            sheet2=sheet2,
            filter_cutoff=filter_cutoff,
            threshold=threshold
        )
    except ValueError as e:
        raise e
    df_jaccard_sim = df.corr(method=jaccard_score)
    df_counts = df.corr(method=count_vals_in_thresholded_association)

    return df_jaccard_sim, df_counts, idx1, idx2


def _calc_mut_info(
        filepath_or_buffer: str | PathLike | Path,
        filepath_or_buffer_2: (str | PathLike | Path)=None,
        sheet1: str=None,
        sheet2: str=None,
        filter_cutoff: float=0.9,
        ) -> pd.DataFrame:
    
    try:
        df, idx1, idx2 = prep_data(
            filepath_or_buffer=filepath_or_buffer,
            filepath_or_buffer_2=filepath_or_buffer_2,
            sheet1=sheet1,
            sheet2=sheet2,
            filter_cutoff=filter_cutoff)
    except ValueError as e:
        raise e
    df_mut_inf = df.corr(method=mutual_information)
    df_counts = df.corr(method=count_vals_in_association)
    
    return df_mut_inf, df_counts, idx1, idx2


def count_vals_in_association(a: ArrayLike, b: ArrayLike) -> int:
    # find positions i in a and b where no NaNs are present
    a_logical = np.logical_not( # inverts T/F values from below
        np.logical_or( # compares the two arrays from below
            np.isnan(a), # returns logical array where NaNs -> True
            np.isnan(b) # same as above
            )
        )
    return sum(a_logical.astype(int)) # converts True to 1 and sums


def count_vals_in_thresholded_association(
        a: ArrayLike, b: ArrayLike) -> int:
    # find positions i in a and b where no NaNs are present
    a_logical = np.logical_not( # inverts T/F values from below
        np.logical_or( # compares the two arrays from below
            np.isnan(a), # returns logical array where NaNs -> True
            np.isnan(b) # same as above
            )
        )
    # add only where no NaNs are present
    # positions where at least either a or b = 1 and neither of them is 
    # NaN will add up to >=1
    a_counts = np.add(a, b, where=a_logical)

    # count positions where a_count >= 1
    ret_val = sum(np.greater_equal(a_counts, 1).astype(int))

    return ret_val
