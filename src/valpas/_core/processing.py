"""
_summary_
"""


from copy import deepcopy
from typing import Literal
# from typing import TYPE_CHECKING
import sys
from warnings import warn

import numpy as np
import pandas as pd

from valpas import AssociationResult
from valpas import Omic
# if TYPE_CHECKING:
#     from valpas._typing import(
#         AssociationResult,
#     )

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


def combine_results(
        results: list[AssociationResult],
        normalization_metric:str='mean'
        ):

    merged_results_vals = None
    merged_results_counts = None
    omic_x_type = None
    omic_x_features = None
    omic_y_type = None
    omic_y_features = None

    for result in results:
        if merged_results_vals is None:
            merged_results_vals = deepcopy(result.values)
        else:
            merged_results_vals = merged_results_vals.add(result.values, fill_value=np.nan)

        if merged_results_counts is None:
            merged_results_counts = deepcopy(result.counts)
        else:
            merged_results_counts = merged_results_counts.add(result.counts, fill_value=np.nan)

        if omic_x_type is None:
            omic_x_type = deepcopy(result.omic_x.type)
            omic_x_features = deepcopy(result.omic_x.features)
        elif str(omic_x_type) != str(result.omic_x.type):
            raise ValueError("Omic types don't match between results")
        else:
            omic_x_features = omic_x_features.intersection(result.omic_x.features)

        if omic_y_type is None:
            omic_y_type = deepcopy(result.omic_y.type)
            omic_y_features = deepcopy(result.omic_y.features)
        elif str(omic_y_type) != str(result.omic_y.type):
            raise ValueError("Omic types don't match between results")
        else:
            omic_y_features = omic_y_features.intersection(result.omic_y.features)

    if normalization_metric == 'mean':
        merged_results_vals = merged_results_vals.div(2)

    merged_result = AssociationResult(
        values=merged_results_vals,
        counts=merged_results_counts,
        omic_x=Omic(type=omic_x_type, features=omic_x_features),
        omic_y=Omic(type=omic_y_type, features=omic_y_features),
    )

    return merged_result

def normalize(
        data: pd.DataFrame,
        method: Literal['z-score', 'pareto', 'power-scaling']='z-score'
        ):

    if method == 'z-score':
        return _norm_z_score(data)
    elif method == 'pareto':
        return _norm_pareto(data)
    elif method == 'power-scaling':
        return _norm_power_trans(data)


def _norm_z_score(data: pd.DataFrame) -> pd.DataFrame:
    mean = np.nanmean(data.values)
    std = np.nanstd(data.values, ddof=1)
    ret_data = data.map(lambda x: (x - mean)/std, na_action='ignore')

    return ret_data

def _norm_pareto(data: pd.DataFrame) -> pd.DataFrame:
    mean = np.nanmean(data.values)
    std = np.nanstd(data.values, ddof=1)
    ret_data = data.map(lambda x: (x - mean)/np.sqrt(std), na_action='ignore')

    return ret_data

def _norm_power_trans(data: pd.DataFrame) -> pd.DataFrame:
    sqmean = np.nanmean(np.sqrt(data.values))
    ret_data = data.map(lambda x: np.sqrt(x)-sqmean, na_action='ignore')

    return ret_data


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

    # Remove self-loops
    #df = df[df[id_1] != df[id_2]]

    df_return = pd.DataFrame({
        id_1: df.index.get_level_values(0),
        id_2: df.index.get_level_values(1),
        value: df.values
        })

    # Remove duplicate edges (e.g., (A,B) and (B,A))
    # Sort the nodes in each pair to ensure uniqueness
    df_return['sorted_nodes'] = df_return.apply(lambda row: tuple(sorted([row[id_1], row[id_2]])),
                                        axis=1)

    df_return = df_return.drop_duplicates(subset='sorted_nodes')
    df_return = df_return.drop(columns='sorted_nodes')

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
