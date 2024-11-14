"""
Module containing functions for the calculation of associations used by 
ValPAS.
"""


from typing import Literal

import sys

import numpy as np
from numpy.typing import ArrayLike
import pandas as pd

from scipy.spatial.distance import cosine
from sklearn.metrics import jaccard_score

from valpas.utils.b_spline import mutual_information
from .. import CrossExperiment
from .. import SingleExperiment



class AssociationResult():

    def __init__(
            self,
            values: pd.DataFrame,
            counts: pd.DataFrame,
            features_x: pd.Index,
            features_y: pd.Index,
            ) -> None:
        
        self.values = values
        self.counts = counts
        self.features_x = features_x
        self.features_y = features_y
    
    # ---------------------------
    # getters, setters & deleters
    # ---------------------------   

    # values
    @property
    def values(self):
        return self._values
    
    @values.setter
    def values(self, value):
        self._values = value
    
    @values.deleter
    def values(self):
        del self._values

    # counts
    @property
    def counts(self):
        return self._counts
    
    @counts.setter
    def counts(self, value):
        self._counts = value
    
    @counts.deleter
    def counts(self):
        del self._counts

    # features_x
    @property
    def features_x(self):
        return self._features_x
    
    @features_x.setter
    def features_x(self, value):
        self._features_x = value
    
    @features_x.deleter
    def features_x(self):
        del self._features_x

    # features_y
    @property
    def features_y(self):
        return self._features_y    
    
    @features_y.setter
    def features_y(self, value):
        self._features_y = value
    
    @features_y.deleter
    def features_y(self):
        del self._features_y


def calc_association(    
        experiment: SingleExperiment | CrossExperiment,
        association: Literal[
            'pearson', 'spearman',
            'jaccard_similarity', 'jaccard_distance', 'jaccard_index',
            'mutual_information',
            'cosine_similarity', 'cosine_distance',
            ]='pearson',
        filter_cutoff: float=0.9,
        threshold: float=None,
    ) -> dict:
    """
    Universal wrapper function that can be called to calculate any of
    the suppored associations between data types. Calls individual 
    private functions internally.

    Parameters
    ----------
    filepath_or_buffer : str | PathLike | Path
        Defines the path to the main file to be imported and used as a 
        basis to calculate associations from. Can be CSV or Excel file.
        If ``filepath_or_buffer`` is an Excel file, ``sheet1`` needs to 
        be defined.
    filepath_or_buffer_2 : str | PathLike | Path, default = None
        Optinonal path definition to a second input file. If 
        ``filepath_or_buffer_2`` is defined, then associations between
        datapoints in ``filepath_or_buffer`` and ``filepath_or_buffer``
        are calculated. Note, if an Excel file is defined as input 
        ``sheet2`` needs to be defined.
    sheet1 : str, default = None
        Used to define the name of the Excel sheet that should be 
        imported. Only used when ``filepath_or_buffer`` points to an 
        Excel file.
    sheet2 : str, default = None
        See ``sheet1``. If ``filepath_or_buffer2`` is defined (and an 
        Excel file) the defined sheet will be imported from there. 
        Otherwise the sheet will be imported from ``filepath_or_buffer``. 
    association : {'pearson', 'spearman', 'jaccard_similarity', \
        'jaccard_distance', 'jaccard_index', 'mutual_information', \
        'cosine_similarity', 'cosine_distance'}, default = 'pearson'
        Defines the type of association measure that should be 
        calculated.
    filter_cutoff : float, default = 0.9
        Rows in ``filepath_or_buffer(_2)`` need to contain at least the 
        fraction of ``filter_cutoff`` values that are not `0.0` or 
        `NaN`. Any rows that have less defined values will excluded from
        the calculation of the association value.
    threshold : float, default = None
        Optional argument that defines the threshold values that is used
        for thresholding values if `cosine_similarity`,
        `cosine_distance`, `jaccard_similiary`, `jaccard_index` or 
        `jaccard_distance` is chosen as the ``association`` metric.

    Returns
    -------
    dict
        Return dictionary contains 4 key/value pairs:
            - `df_assoc`: ``pandas.DataFrame`` containing the 
              association values
            - `df_counts`: ``pandas.DataFrame`` containing metadata 
              / counts 
            - `idx1`: ``pandas.Index`` containing the data items of 
              ``x``
            - `idx2`: ``pandas.Index`` containing the data items of 
              ``y``

    Raises
    ------
    ValueError
        ValueError that is passed along from 
        ``valpas.utils.data_handling.prep_single_experiment()``
    """

    if association in ['pearson', 'spearman']:
        try:
            df_assoc, df_counts, idx1, idx2 = _calc_correlation(
                experiment=experiment,
                corr_func=association,
                filter_cutoff=filter_cutoff,
            )
        except ValueError as e:
            sys.exit(e)
    elif association in ['cosine_similarity', 'cosine_distance']:
        try:
            df_assoc, df_counts, idx1, idx2 = _calc_cosine_dist(
                experiment=experiment,
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
                experiment=experiment,
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
                experiment=experiment,
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
        experiment: SingleExperiment,
        corr_func: Literal['pearson', 'kendall', 'spearman']='pearson',
        filter_cutoff: float=0.9,
    ) -> tuple:
    """
    Helper function to calculate correlation between two omics data
    types. Omics data types are either extraced from two Excel file
    sheets (from either the same or two different Excel files) or two 
    CSV files.  

    Parameters
    ----------
    filepath_or_buffer : str | PathLike | Path
        Defines the path to the main file to be imported and used as a 
        basis to calculate associations from. Can be CSV or Excel file.
        If ``filepath_or_buffer`` is an Excel file, ``sheet1`` needs to 
        be defined.
    filepath_or_buffer_2 : str | PathLike | Path, default = None
        Optinonal path definition to a second input file. If 
        ``filepath_or_buffer_2`` is defined, then associations between
        datapoints in ``filepath_or_buffer`` and ``filepath_or_buffer``
        are calculated. Note, if an Excel file is defined as input 
        ``sheet2`` needs to be defined.
    sheet1 : str, default = None
        Used to define the name of the Excel sheet that should be 
        imported. Only used when ``filepath_or_buffer`` points to an 
        Excel file.
    sheet2 : str, default = None
        See ``sheet1``. If ``filepath_or_buffer2`` is defined (and an 
        Excel file) the defined sheet will be imported from there. 
        Otherwise the sheet will be imported from ``filepath_or_buffer``.
    corr_func : {'pearson', 'kendall', 'spearman'}, default='pearson'
        Definets the correlation function that is to be used.
    filter_cutoff : float, default = 0.9
        Rows in ``filepath_or_buffer(_2)`` need to contain at least the 
        fraction of ``filter_cutoff`` values that are not `0.0` or 
        `NaN`. Any rows that have less defined values will excluded from
        the calculation of the association value.

    Returns
    -------
    tuple(pd.DataFrame, pd.DataFrame, pd.Axis, pd.Axis)
        Returns a tuple containing four elements, two pd.DataFrames 
        containing the correlation values as well as the counts of data
        values that contributed to the association, as well as two
        pd.Axis objects containing the row and column identifier for 
        the pd.DataFrame that contains the association values

    Raises
    ------
    ValueError
        Passes along ValueError that might be raised by prep_single_experiment().
    """

    try:

        experiment.pre_process(
            rm_low_conf_features=filter_cutoff,
            inplace=True
            )
        df = experiment.measurements
        idx1 = experiment.omic_x.features
        idx2 = experiment.omic_y.features

    except ValueError as e:
        raise e
    df_corr = df.corr(method=corr_func)
    df_counts = df.corr(method=count_vals_in_association)

    return df_corr, df_counts, idx1, idx2


def _calc_cosine_dist(
        experiment: SingleExperiment,
        filter_cutoff: float=0.9,
        threshold: float=None
        ) -> pd.DataFrame:
    """
    Helper function to calculate Cosine Distance between two omics data
    types. Omics data types are either extraced from two Excel file
    sheets (from either the same or two different Excel files) or two 
    CSV files.  

    Parameters
    ----------
    filepath_or_buffer : str | PathLike | Path
        Defines the path to the main file to be imported and used as a 
        basis to calculate associations from. Can be CSV or Excel file.
        If ``filepath_or_buffer`` is an Excel file, ``sheet1`` needs to 
        be defined.
    filepath_or_buffer_2 : str | PathLike | Path, default = None
        Optinonal path definition to a second input file. If 
        ``filepath_or_buffer_2`` is defined, then associations between
        datapoints in ``filepath_or_buffer`` and ``filepath_or_buffer``
        are calculated. Note, if an Excel file is defined as input 
        ``sheet2`` needs to be defined.
    sheet1 : str, default = None
        Used to define the name of the Excel sheet that should be 
        imported. Only used when ``filepath_or_buffer`` points to an 
        Excel file.
    sheet2 : str, default = None
        See ``sheet1``. If ``filepath_or_buffer2`` is defined (and an 
        Excel file) the defined sheet will be imported from there. 
        Otherwise the sheet will be imported from ``filepath_or_buffer``.
    filter_cutoff : float, default = 0.9
        Rows in ``filepath_or_buffer(_2)`` need to contain at least the 
        fraction of ``filter_cutoff`` values that are not `0.0` or 
        `NaN`. Any rows that have less defined values will excluded from
        the calculation of the association value.
    threshold : float, default = 0.5
        Optional argument that defines the threshold values that is used
        for thresholding values.

    Returns
    -------
    tuple(pd.DataFrame, pd.DataFrame, pd.Axis, pd.Axis)
        Returns a tuple containing four elements, two pd.DataFrames 
        containing the association values as well as the counts of data
        values that contributed to the calculation, as well as two
        pd.Axis objects containing the row and column identifier for 
        the pd.DataFrame that contains the association values

    Raises
    ------
    ValueError
        Passes along ValueError that might be raised by prep_single_experiment().
    """

    try:

        experiment.pre_process(
            rm_low_conf_features=filter_cutoff,
            threshold=threshold,
            inplace=True
            )
        df = experiment.measurements
        idx1 = experiment.omic_x.features
        idx2 = experiment.omic_y.features

    except ValueError as e:
        raise e
    df_cos_dist = df.corr(method=cosine)
    if threshold is None:
        df_counts = df.corr(method=count_vals_in_association)
    else:
        df_counts = df.corr(method=count_vals_in_thresholded_association)

    return df_cos_dist, df_counts, idx1, idx2


def _calc_jaccard_sim(
        experiment: SingleExperiment,
        filter_cutoff: float=0.9,
        threshold: float=0.5
        ) -> pd.DataFrame:
    """
    Helper function to calculate Jaccard Index between two omics data
    types. Omics data types are either extraced from two Excel file
    sheets (from either the same or two different Excel files) or two 
    CSV files.  

    Parameters
    ----------
    filepath_or_buffer : str | PathLike | Path
        Defines the path to the main file to be imported and used as a 
        basis to calculate associations from. Can be CSV or Excel file.
        If ``filepath_or_buffer`` is an Excel file, ``sheet1`` needs to 
        be defined.
    filepath_or_buffer_2 : str | PathLike | Path, default = None
        Optinonal path definition to a second input file. If 
        ``filepath_or_buffer_2`` is defined, then associations between
        datapoints in ``filepath_or_buffer`` and ``filepath_or_buffer``
        are calculated. Note, if an Excel file is defined as input 
        ``sheet2`` needs to be defined.
    sheet1 : str, default = None
        Used to define the name of the Excel sheet that should be 
        imported. Only used when ``filepath_or_buffer`` points to an 
        Excel file.
    sheet2 : str, default = None
        See ``sheet1``. If ``filepath_or_buffer2`` is defined (and an 
        Excel file) the defined sheet will be imported from there. 
        Otherwise the sheet will be imported from ``filepath_or_buffer``.
    filter_cutoff : float, default = 0.9
        Rows in ``filepath_or_buffer(_2)`` need to contain at least the 
        fraction of ``filter_cutoff`` values that are not `0.0` or 
        `NaN`. Any rows that have less defined values will excluded from
        the calculation of the association value.
    threshold : float, default = 0.5
        Optional argument that defines the threshold values that is used
        for thresholding values.

    Returns
    -------
    tuple(pd.DataFrame, pd.DataFrame, pd.Axis, pd.Axis)
        Returns a tuple containing four elements, two pd.DataFrames 
        containing the association values as well as the counts of data
        values that contributed to the calculation, as well as two
        pd.Axis objects containing the row and column identifier for 
        the pd.DataFrame that contains the association values

    Raises
    ------
    ValueError
        Passes along ValueError that might be raised by prep_single_experiment().
    """

    try:

        experiment.pre_process(
            rm_low_conf_features=filter_cutoff,
            threshold=threshold,
            inplace=True
            )
        df = experiment.measurements
        idx1 = experiment.omic_x.features
        idx2 = experiment.omic_y.features

    except ValueError as e:
        raise e
    df_jaccard_sim = df.corr(method=jaccard_score)
    df_counts = df.corr(method=count_vals_in_thresholded_association)

    return df_jaccard_sim, df_counts, idx1, idx2


def _calc_mut_info(
        experiment: SingleExperiment,
        filter_cutoff: float=0.9,
        ) -> pd.DataFrame:
    """
    Helper function to calculate Mutual Information between two omics 
    data types. Omics data types are either extraced from two Excel file
    sheets (from either the same or two different Excel files) or two 
    CSV files.  

    Parameters
    ----------
    filepath_or_buffer : str | PathLike | Path
        Defines the path to the main file to be imported and used as a 
        basis to calculate associations from. Can be CSV or Excel file.
        If ``filepath_or_buffer`` is an Excel file, ``sheet1`` needs to 
        be defined.
    filepath_or_buffer_2 : str | PathLike | Path, default = None
        Optinonal path definition to a second input file. If 
        ``filepath_or_buffer_2`` is defined, then associations between
        datapoints in ``filepath_or_buffer`` and ``filepath_or_buffer``
        are calculated. Note, if an Excel file is defined as input 
        ``sheet2`` needs to be defined.
    sheet1 : str, default = None
        Used to define the name of the Excel sheet that should be 
        imported. Only used when ``filepath_or_buffer`` points to an 
        Excel file.
    sheet2 : str, default = None
        See ``sheet1``. If ``filepath_or_buffer2`` is defined (and an 
        Excel file) the defined sheet will be imported from there. 
        Otherwise the sheet will be imported from ``filepath_or_buffer``.
    filter_cutoff : float, default = 0.9
        Rows in ``filepath_or_buffer(_2)`` need to contain at least the 
        fraction of ``filter_cutoff`` values that are not `0.0` or 
        `NaN`. Any rows that have less defined values will excluded from
        the calculation of the association value.

    Returns
    -------
    tuple(pd.DataFrame, pd.DataFrame, pd.Axis, pd.Axis)
        Returns a tuple containing four elements, two pd.DataFrames 
        containing the association values as well as the counts of data
        values that contributed to the calculation, as well as two
        pd.Axis objects containing the row and column identifier for 
        the pd.DataFrame that contains the association values

    Raises
    ------
    ValueError
        Passes along ValueError that might be raised by prep_single_experiment().
    """
    try:

        experiment.pre_process(
            rm_low_conf_features=filter_cutoff,
            inplace=True
            )
        df = experiment.measurements
        idx1 = experiment.omic_x.features
        idx2 = experiment.omic_y.features

    except ValueError as e:
        raise e
    df_mut_inf = df.corr(method=mutual_information)
    df_counts = df.corr(method=count_vals_in_association)
    
    return df_mut_inf, df_counts, idx1, idx2


def count_vals_in_association(a: ArrayLike, b: ArrayLike) -> int:
    """
    Helper function that counts the number of values that are utilized 
    in the calculation of an association score between two arrays of 
    data points.

    Parameters
    ----------
    a : ArrayLike
        One of the two arrays in the pair of arrays for which an
        association value should be calculated. 
    b : ArrayLike
        The second of the two arrays in the pair of arrays for which an
        association value should be calculated. 

    Returns
    -------
    int
        The count of values in both arrays that are used to calculate 
        the association value.
    """

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
    """
    Helper function that counts the number of values that are utilized 
    in the calculation of an association score between two thresholdeded
    arrays of data points. Note this function performs a slightly 
    different set of instructions in comparison to 
    ``count_vals_in_association`` to account for the thresholding of 
    values that has been done prior.

    Parameters
    ----------
    a : ArrayLike
        One of the two arrays in the pair of arrays for which an
        association value should be calculated. 
    b : ArrayLike
        The second of the two arrays in the pair of arrays for which an
        association value should be calculated. 

    Returns
    -------
    int
        The count of values in both arrays that are used to calculate 
        the association value.
    """

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
