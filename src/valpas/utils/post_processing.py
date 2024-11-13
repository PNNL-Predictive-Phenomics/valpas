"""
Module containing helper functions for post processing as required in 
other parts of the valpas package
"""

import numpy as np
import pandas as pd

from warnings import warn

def sort_associations(df: pd.DataFrame, reduced_output: bool=False) -> pd.Series:
    """
    Takes a matrix like pandas Dataframe object, extracts the upper 
    triangle, stacks and sorts the cell values.

    .. deprecated:: 0 
        The functionality has been moved to ``.beatify_series`` and 
        ``.rm_duplicates``.

    Returns a sorted pandas Series object with a multiindex comprised 
    of index pairs from *df* as axis labels and the value of the *df* 
    cell as values.
    """
    warn(
        "Sorting functionality moved to *.beautify_series. Duplication "
        "removal moved to novel function *.rm_duplicates.",
        DeprecationWarning,
        stacklevel=2
        )


    if reduced_output:
        # use case for this block: if the correlation matrix is NxN and 
        # each n in N is from only one data source we can reduce the 
        # output to pervent *association(i,j)* and *association(j,i)*
        # to show up in the output. Note that if the correlation matrix 
        # contains NxM elements and N & M are two different sets of 
        # data points, choosing to reduce the input will remove unique 
        # results.
        # 
        # The code block extracts the upper triangle of the matrix, 
        # sets the lower triangle (including the diagonal) to NaN.
        # `pd.DataFrame.stack()` drops NaNs by default and therefore 
        # excludes the pairs from sorting and being returned.
        upper_tri = np.triu(df, -1)
        upper_tri[np.tril_indices(upper_tri.shape[0], 0)] = np.nan

        df_upper_tri = pd.DataFrame(
            data=upper_tri,
            index=df.index,
            columns=df.columns
            )
        df_sorted = df_upper_tri.stack().sort_values(ascending=False)
    
    else:
        # by default full output of the sorted list is generated to 
        # guarantuee that all results are returned. This is especially 
        # important if association between two different data types was 
        # generated and no "self-hits" exsist
        df_sorted = df.stack().sort_values(ascending=False) 


    return df_sorted

def rm_duplicates(
        df: pd.DataFrame, idx1: pd.Index, idx2: pd.Index=None
        ) -> pd.DataFrame:
    """
    Removes duplicates of omics data pairs that have been generated 
    during the calculation of association values.

    Parameters
    ----------
    df : pandas.DataFrame
        DataFrame that should be cleaned.
    idx1 : pandas.Index
        Index object containing omics identifiers. If ``idx2`` is not 
        passed to the function the assumption is that items recoreded in
        ``idx1`` are associated with each other.
    idx2 : pandas.Index, default=None
        Index object containing omics identifiers. If provided the
        assumption is that association pairs should only be of type
        [idx1, idx2]. Any pairs [idx1, idx1] or [idx2, idx2] are 
        removed. 
        
    Returns
    -------
    pandas.DataFrame
        Filtered panadas.DataFrame object that has duplicates removed.
    
    Notes
    -----
    The function serves two purposes:
    
    1. If the `DataFrame` passed to the function contains items from 
       only one omics type (indicated by omitting `idx2` / setting it to 
       `None`, see also ``valpas.utils.data_handling.prep_data`)), then
       the function will extract the upper triangle (any association 
       measure implemented should be symmetric i.e. 
       :math:`A(a,b)=A(b,a)`)
    2. If both `idx1` and `idx2` is passed to the function, it is 
       assumed that the DF contains items from two different omics
       types. In this case the DF is filtered such that `DF.index` only 
       contains items from `idx1` and `DF.columns` contains only items
       of `idx2`.
    """

    if idx2 is None:
        # use case for this block: if the correlation matrix is NxN and 
        # each n in N is from only one data source we can reduce the 
        # output to pervent *association(i,j)* and *association(j,i)*
        # to show up in the output. Note that if the correlation matrix 
        # contains NxM elements and N & M are two different sets of 
        # data points, choosing to reduce the input will remove unique 
        # results.
        # 
        # The code block extracts the upper triangle of the matrix, 
        # sets the lower triangle (including the diagonal) to NaN.
        # `pd.DataFrame.stack()` drops NaNs by default and therefore 
        # excludes the pairs from sorting and being returned.
        upper_tri = np.triu(df, -1)
        upper_tri[np.tril_indices(upper_tri.shape[0], 0)] = np.nan

        df_ret = pd.DataFrame(
            data=upper_tri,
            index=df.index,
            columns=df.columns
            )
        return df_ret
    else:
        # This covers case (2) listed in the docstring, i.e. the 
        # the DataFrame contains data from two different omics data 
        # data types. In this case we filter the DF such that the rows 
        # are limited to items from `idx1` and the columns are limited 
        # to `idx2`.

        df_ret = df.drop(
            labels=df.index.difference(idx2),
            axis='index',
            )
        df_ret.drop(
            labels=df.columns.difference(idx1),
            axis='columns',
            inplace=True)
        return df_ret


def beautify_series(df: pd.Series, value: str="Correlation") -> pd.DataFrame:
    """
    Takes ``pandas.DataFrame`` object, extracts index names and 
    transforms the data into a ``pandas.DataFrame`` with column 1 & 2
    being the indices of the Series and column 3 the association value.

    Parameters
    ----------
    df : pandas.DataFrame
        DataFrame containing association values between omics data 
        items.
    value : str, default="Correlation"
        Describes the association type of the values.

    Returns
    -------
    pd.DataFrame
        A DataFrame object with three columns. (1) & (2) are omics 
        identifiers, (3) is the association value
    """
    df = df.stack().sort_values(ascending=False)
    try:
        if df.index.names[0] == df.index.names[1]:
            id_1 = '_'.join([df.index.names[0], '1'])
            id_2 = '_'.join([df.index.names[0], '2'])
        else:
            id_1 = df.index.names[0]
            id_2 = df.index.names[1]
    except TypeError:
        print(df.index[0])
    df_return = pd.DataFrame({
        id_1: df.index.get_level_values(0),
        id_2: df.index.get_level_values(1),
        value: df.values
        })
    return df_return


def idx_name(
        df: pd.DataFrame, idx1: pd.Index, idx2: pd.Index=None
        ) -> pd.DataFrame:
    """
    Helper function to assign index and column names.

    Parameters
    ----------
    df : pandas.DataFrame
        DataFrame object whose index and column should be named.
    idx1 : pandas.Index
        Index object that contains the name and the indentifiers for the
        index (rows) of the DataFrame
    idx2 : pandas.Index, default=None
        Index object that contains the name and the indentifiers for the
        columns of the DataFrame

    Returns
    -------
    pd.DataFrame
        DataFrame with named columns and index.
    """
    df.index.name = idx1.name
    if idx2 is None:
        df.columns.name = idx1.name
    else:
        df.columns.name = idx2.name
    
    return df
