"""
Module containing helper functions to deal with data handling (i.e. 
input & output).
"""

import pandas as pd

def prep_data(file_handle: str) -> pd.DataFrame:
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
    
    df_t = df.transpose()

    return df_t

