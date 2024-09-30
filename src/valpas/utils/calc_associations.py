"""
Module containing functions for the calculation of associations used by 
ValPAS.
"""


from os import PathLike
from pathlib import Path
from typing import Literal

import sys

import pandas as pd

from scipy.spatial.distance import cosine
from sklearn.metrics import mutual_info_score
from sklearn.metrics import jaccard_score

from valpas.utils.data_handling import prep_data

def calc_correlation(
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
        sys.exit(e)
    df_corr = df.corr(method=corr_func)

    return df_corr, idx1, idx2

def calc_mut_info(
        filepath_or_buffer: str | PathLike | Path,
        filepath_or_buffer_2: (str | PathLike | Path)=None,
        sheet1: str=None,
        sheet2: str=None,
        filter_cutoff: float=0.9,
        cut: bool=True
        ) -> pd.DataFrame:
    
    try:
        df, idx1, idx2 = prep_data(
            filepath_or_buffer=filepath_or_buffer,
            filepath_or_buffer_2=filepath_or_buffer_2,
            sheet1=sheet1,
            sheet2=sheet2,
            filter_cutoff=filter_cutoff,
            cut=cut)
    except ValueError as e:
        sys.exit(e)
    df_mut_inf = df.corr(method=mutual_info_score)
    
    return df_mut_inf, idx1, idx2

def calc_cosine_sim(
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
        sys.exit(e)
    df_cos_dist = df.corr(method=cosine)
    df_cos_sim = df_cos_dist.rsub(1) # converting distance to similarity
    
    return df_cos_sim, idx1, idx2

def calc_jaccard_sim(
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
        sys.exit(e)
    df_jaccard_sim = df.corr(method=jaccard_score)
    
    return df_jaccard_sim, idx1, idx2
