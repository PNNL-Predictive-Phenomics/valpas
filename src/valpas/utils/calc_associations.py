"""
Module containing functions for the calculation of associations used by 
ValPAS.
"""


from os import PathLike
from typing import Literal
from typing import TextIO

import numpy as np
from numpy.typing import ArrayLike
import pandas as pd

from scipy.spatial.distance import cosine
from sklearn.metrics import mutual_info_score
from sklearn.metrics import jaccard_score

from valpas.utils.data_handling import prep_data

def calc_correlation(
        filepath_or_buffer: str | PathLike | TextIO,
        filepath_or_buffer_2: (str | PathLike | TextIO)=None,
        corr_func: Literal['pearson', 'kendall', 'spearman']='pearson',
        filter_cutoff: float=0.9,
    ) -> pd.DataFrame:
    
    df, idx1, idx2 = prep_data(
        filepath_or_buffer=filepath_or_buffer,
        filepath_or_buffer_2=filepath_or_buffer_2,
        filter_cutoff=filter_cutoff)
    df_corr = df.corr(method=corr_func)

    return df_corr, idx1, idx2

def calc_mut_info(
        filepath_or_buffer: str | PathLike | TextIO,
        filepath_or_buffer_2: (str | PathLike | TextIO)=None,
        filter_cutoff: float=0.9,
        cut: bool=True
        ) -> pd.DataFrame:
    
    df, idx1, idx2 = prep_data(
        filepath_or_buffer=filepath_or_buffer,
        filepath_or_buffer_2=filepath_or_buffer_2,
        filter_cutoff=filter_cutoff,
        cut=cut)
    df_mut_inf = df.corr(method=mutual_info_score)
    
    return df_mut_inf, idx1, idx2

def calc_cosine_sim(
        filepath_or_buffer: str | PathLike | TextIO,
        filepath_or_buffer_2: (str | PathLike | TextIO)=None,
        filter_cutoff: float=0.9,
        threshold: float=None
        ) -> pd.DataFrame:

    df, idx1, idx2 = prep_data(
        filepath_or_buffer=filepath_or_buffer,
        filepath_or_buffer_2=filepath_or_buffer_2,
        filter_cutoff=filter_cutoff,
        threshold=threshold
    )
    df_cos_dist = df.corr(method=cosine)
    df_cos_sim = df_cos_dist.rsub(1) # converting distance to similarity
    
    return df_cos_sim, idx1, idx2

def calc_jaccard_sim(
        filepath_or_buffer: str | PathLike | TextIO,
        filepath_or_buffer_2: (str | PathLike | TextIO)=None,
        filter_cutoff: float=0.9,
        threshold: float=0.5
        ) -> pd.DataFrame:
    
    df, idx1, idx2 = prep_data(
        filepath_or_buffer=filepath_or_buffer,
        filepath_or_buffer_2=filepath_or_buffer_2,
        filter_cutoff=filter_cutoff,
        threshold=threshold
    )
    df_jaccard_sim = df.corr(method=jaccard_score)
    
    return df_jaccard_sim, idx1, idx2


def count_vals_in_association(a: ArrayLike, b: ArrayLike) -> int:
    # a_logical lists positions as True where both values are !NaN 
    a_logical = np.logical_not( # inverts T/F values from below
        np.logical_or( # compares the two arrays from below
            np.isnan(a), # returns logical array where NaNs -> True
            np.isnan(b) # same as above
            )
        )
    return sum(a_logical.astype(int)) # converts True to 1 and sums