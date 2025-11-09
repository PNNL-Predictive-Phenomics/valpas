from __future__ import annotations

from typing import Literal
from typing import TYPE_CHECKING

import sys
import errno
import os

import numpy as np
from numpy.typing import ArrayLike
import pandas as pd

import torch

from scipy.spatial.distance import cosine
from sklearn.metrics import jaccard_score

from valpas.utils.b_spline import mutual_information

from valpas import AssociationResult
from valpas._core import autoencoder
from valpas._core import weightedcorrelationmodel
from valpas._core import clr_transform

if TYPE_CHECKING:
    from valpas._typing import(
        CrossExperiment,
        SingleExperiment,
    )


def calculate_association(
        experiment: SingleExperiment | CrossExperiment,
        method: Literal[
            'pearson', 'spearman',
            'jaccard_similarity', 'jaccard_distance', 'jaccard_index',
            'mutual_information',
            'cosine_similarity', 'cosine_distance', 'autoencoder',
            'load_sim', 'learn_correlation'
            ]='pearson',
        thresholded: bool=False,
        training_interactions: list=None,
        transform_clr: bool=False,
        learncorr_args: dict={},
        autoencoder_args: dict={},
        subset_args: dict={},
    ) -> AssociationResult:
    """
    Universal wrapper function that can be called to calculate any of
    the supported associations between data types. Calls individual
    private functions internally.

    Parameters
    ----------
    experiment: SingleExperiment | CrossExperiment
        An ``Experiment`` object that has all the required information
        stored associated with the experiment that the association
        values should be calculated for
    association : {'pearson', 'spearman', 'jaccard_similarity', \
        'jaccard_distance', 'jaccard_index', 'mutual_information', \
        'cosine_similarity', 'cosine_distance', 'autoencoder',
        'load_sim', 'learn_correlation'}, default = 'pearson'
        Defines the type of association measure that should be
        calculated.
    filter_cutoff : float, default = 0.9
        Rows in ``filepath_or_buffer(_2)`` need to contain at least the
        fraction of ``filter_cutoff`` values that are not `0.0` or
        `NaN`. Any rows that have fewer defined values will excluded from
        the calculation of the association value.
    threshold : float, default = None
        Optional argument that defines the threshold values that is used
        for thresholding values if `cosine_similarity`,
        `cosine_distance`, `jaccard_similiary`, `jaccard_index` or
        `jaccard_distance` is chosen as the ``association`` metric.
    training_interactions : list, default = None
        Optional argument used for training (currently only learn_correlation)
        which should be a list of tuples that represent known interactions.
    transform_clr : bool, default = False
        If True process final similarity matrix (from specified method) using
        the mean of Z-scores from row and column like the CLR method.
    subset_args : dict, default = {}
        Keyword arguments to pass to subsetting function
    autoencoder_args : dict, default = {}
        Keyword arguments to pass to autoencoder function
    learncorr_args : dict, default = {}
        Keyword arguments to pass to learn correlation function

    Returns
    -------
    AssociationResult

    Raises
    ------
    ValueError
        ValueError that is passed along from
        ``valpas.utils.data_handling.prep_single_experiment()``
    """

    # Subset the input measurements first?
    if subset_args['nconds'] or subset_args['percentage'] or subset_args['keep_conds']:
        experiment = experiment.subset_by_conditions(**subset_args)

    if method in ['pearson', 'spearman']:
        result_values = experiment.measurements.corr(method=method)

    elif method in ['cosine_similarity', 'cosine_distance']:
        # `scipy.spatial.distance.cosine()` calculates cosine distance
        # by default
        result_values = experiment.measurements.corr(method=cosine)

        if method == 'cosine_similarity':
            # converting distance to similarity
            result_values = result_values.rsub(1)

    elif method in [
        'jaccard_similarity', 'jaccard_distance', 'jaccard_index'
            ]:

        # `sklearn.metrics.jaccard_score` calculates jaccard similarity
        # (also known as jaccard index) by default
        result_values = experiment.measurements.corr(method=jaccard_score)

        if method == 'jaccard_distance':
            # converting similarity to distance
            result_values = result_values.rsub(1)

    elif method == 'mutual_information':
        result_values = experiment.measurements.corr(method=mutual_information)

    elif method == 'autoencoder':
        # Train autoencoder
        model, dataset, training_history = autoencoder.train_proteomics_autoencoder(
            experiment.measurements.transpose(),
            **autoencoder_args)

        # Calculate similarity matrix
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        result_values = autoencoder.calculate_protein_similarity_matrix(model, dataset, device)

        autoencoder.save_autoencoder_results(model, dataset, training_history, result_values)

        result_counts = result_values.copy(deep=True)

        result_counts.iloc[:, :] = len(experiment.measurements.transpose().columns)

    elif method == 'learn_correlation':
        anlysis_results = weightedcorrelationmodel.learn_correlation_weights(
            data=experiment.measurements.transpose(),
            interactions=training_interactions,
            verbose=True,
            **learncorr_args
        )

        # now returns an analysis results object
        result_values = analysis_results.weighted_correlation_matrix

    elif method == "load_sim":
        # allow loading of a similarity matrix as a csv
        output_dir = "proteomics_analysis"
        sim_path = os.path.join(output_dir, "protein_similarity_matrix.csv")
        result_values = pd.read_csv(sim_path, index_col=0)
        result_counts = result_values.copy(deep=True)

        # it's hard to figure out how to do this without this
        #      information as it could be any value really?
        # So this is an attempt to make it non-zero
        result_counts.iloc[:, :] = len(experiment.measurements.transpose().columns)

    else:
        raise ValueError(f"Association type {method} not supported!")

    # Tranform similarity matrix using the CLR-style Zscore transform
    if transform_clr:
        result_values = clr_transform.clr_transform(result_values)

    # getting the counts of how many values were considered in the
    # calculation of each association value
    if method not in ["load_sim", "autoencoder"]:
        if thresholded:
            result_counts = experiment.measurements.corr(
                method=count_vals_in_thresholded_association
                )
        else:
            result_counts = experiment.measurements.corr(
                method=count_vals_in_association
                )

    result = AssociationResult(
        values=result_values,
        counts=result_counts,
        omic_x=experiment.omic_x,
        omic_y=experiment.omic_y,
        analysis_results=analysis_results
    )

    return result


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
