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
            'load_autoencoder', 'load_sim', 'learn_correlation'
            ]='pearson',
        thresholded: bool=False,
        training_interactions: list=None,
        learning_method: str='ridge',
        vae_protein_embedding_dim: int=64,
        vae_sample_embedding_dim: int=64,
        vae_learning_rate: float=1e-3,
        vae_epochs: int=200,
        subset_nconds: int=0,
        subset_percentage: float=0,
        subset_keep_conds: list=None,
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
        'load_autoencoder', 'load_sim', 'learn_correlation'}, default = 'pearson'
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
    subset_nconds : int, default = None
    subset_percentage : float, default = None
    subset_keep_conds : list, default = None

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
    if subset_nconds or subset_percentage or subset_keep_conds:
        experiment = experiment.subset_by_conditions(nconds=subset_nconds,
                                                    percentage=subset_percentage,
                                                    keep_conds=subset_keep_conds)

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
        #TODO: support for parameter setting for the autoencoder training
        # Train autoencoder
        model, dataset, training_history = autoencoder.train_proteomics_autoencoder(
            experiment.measurements.transpose(),
            protein_embedding_dim=vae_protein_embedding_dim,
            sample_embedding_dim=vae_sample_embedding_dim,
            learning_rate=vae_learning_rate,
            epochs=vae_epochs
        )

        # Calculate similarity matrix
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        result_values = autoencoder.calculate_protein_similarity_matrix(model, dataset, device)

        autoencoder.save_autoencoder_results(model, dataset, training_history, result_values)

        result_counts = result_values.copy(deep=True)

        # it's hard to figure out how to do this without this
        #      information as it could be any value really?
        # So this is an attempt to make it non-zero
        result_counts.iloc[:, :] = 1

    elif method == 'learn_correlation':
        results = weightedcorrelationmodel.learn_correlation_weights(
            data=experiment.measurements.transpose(),
            interactions=training_interactions,
            learning_method=learning_method,
            correlation_method='pearson',
            train_split=0.7,
            max_iterations=500 if method == 'neural' else 2000,
            verbose=True
        )
        # there is a lot more returned than just this
        # TODO: figure out how to handle that returned information
        result_values = results['weighted_correlation_matrix']

    elif method == 'load_autoencoder':
        #Kludge to allow development using an already trained model, since this
        #       takes a loooong time.
        # This anticipates that there is a folder called 'protein_analysis' to
        #      load the model from and will throw an error if it's not there.
        # Train autoencoder
        #model, dataset, training_history = autoencoder.train_proteomics_autoencoder(
        #    experiment.measurements,
        #    protein_embedding_dim=64,
        #    epochs=100
        #)
        output_dir = "proteomics_analysis"
        if not os.path.exists(output_dir):
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT),
                            output_dir)

        model_path = os.path.join(output_dir, "autoencoder_model.pth")
        model_artifacts = autoencoder.load_proteomics_autoencoder(model_path)

        # Create dataset
        # FIXME: this may not always work - if the scaling method is different, e.g.
        dataset = autoencoder.ProteomicsDataset(
            experiment.measurements,
            mask_probability=0.15,
            scaling_method='robust'
        )

        # Calculate similarity matrix
        result_values = autoencoder.calculate_protein_similarity_matrix(
                                    model_artifacts['model'],
                                    dataset,
                                    model_artifacts['device'])
        result_counts = result_values.copy(deep=True)

        # it's hard to figure out how to do this without this
        #      information as it could be any value really?
        # So this is an attempt to make it non-zero
        result_counts.iloc[:, :] = 1

    elif method == "load_sim":
        # allow loading of a similarity matrix as a csv
        output_dir = "proteomics_analysis"
        sim_path = os.path.join(output_dir, "protein_similarity_matrix.csv")
        result_values = pd.read_csv(sim_path, index_col=0)
        result_counts = result_values.copy(deep=True)

        # it's hard to figure out how to do this without this
        #      information as it could be any value really?
        # So this is an attempt to make it non-zero
        result_counts.iloc[:, :] = 1

    else:
        raise ValueError(f"Association type {method} not supported!")

    # Add in: z-score calculation for results_values Matrix
    #        this can be an option, but would make the different
    #        metrics more comparable

    # getting the counts of how many values were considered in the
    # calculation of each association value
    if method not in ["load_sim", "load_autoencoder", "autoencoder"]:
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
