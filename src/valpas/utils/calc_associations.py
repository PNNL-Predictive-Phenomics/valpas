"""
Module containing functions for the calculation of associations used by 
ValPAS.
"""

from typing import Literal

import pandas as pd

from valpas.utils.data_handling import prep_data

def calc_correlation(
        fpath_1: str,
        fpath_2: str=None,
        corr_func: Literal['pearson', 'kendall', 'spearman']='pearson',
    ) -> pd.DataFrame:
    
    df_1 = prep_data(fpath_1)
    if fpath_2 is None:
        df_corr = df_1.corr(method=corr_func)
    else:
        df_2 = prep_data(fpath_2)
        df_corr = df_1.apply(df_2.corrwith)

    return df_corr
    