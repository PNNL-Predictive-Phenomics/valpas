"""
Module containing functions for the calculation of associations used by 
ValPAS.
"""

from typing import Literal

import pandas as pd
from sklearn.metrics import mutual_info_score

from valpas.utils.data_handling import prep_data

def calc_correlation(
        fpath_1: str,
        fpath_2: str=None,
        corr_func: Literal['pearson', 'kendall', 'spearman']='pearson',
        filter_cutoff: float=None,
    ) -> pd.DataFrame:
    
    df_1 = prep_data(fpath_1, filter_cutoff=filter_cutoff)
    if fpath_2 is None:
        df_corr = df_1.corr(method=corr_func)
    else:
        df_2 = prep_data(fpath_2)
        df_corr = df_1.apply(df_2.corrwith)

    return df_corr

def calc_mut_info(
        fpath_1: str,
        fpath_2: str=None,
        filter_cutoff: float=None,
        ) -> pd.DataFrame:
    
    df_1 = prep_data(fpath_1, cut=True, filter_cutoff=filter_cutoff)
    if fpath_2 is None:
        df_mut_inf = df_1.corr(method=mutual_info_score)
    else:
        df_2 = prep_data(fpath_2, cut=True)
        df_mut_inf = df_1.apply(df_2.corrwith, method=mutual_info_score)
    
    return df_mut_inf