"""
Module containing helper functions for post processing as required in 
other parts of the valpas package
"""

import numpy as np
import pandas as pd

def sort_associations(df: pd.DataFrame) -> pd.Series:
    """
    Takes a matrix like pandas Dataframe object, extracts the upper 
    triangle, stacks and sorts the cell values.
    
    Returns a sorted pandas Series object with a multiindex comprised 
    of index pairs from *df* as axis labels and the value of the *df* 
    cell as values.
    """
    upper_tri = np.triu(df, -1)
    upper_tri[np.tril_indices(upper_tri.shape[0], 0)] = np.nan

    df_upper_tri = pd.DataFrame(
        data=upper_tri,
        index=df.index,
        columns=df.columns
        )

    df_sorted = df_upper_tri.stack().sort_values(ascending=False)

    return df_sorted