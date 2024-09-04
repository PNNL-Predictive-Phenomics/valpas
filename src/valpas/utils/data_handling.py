"""
Module containing helper functions to deal with data handling (i.e. 
input & output).
"""

import pandas as pd

from valpas.utils.post_processing import beautify_series
from valpas.utils.post_processing import sort_associations

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
