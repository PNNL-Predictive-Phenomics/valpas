from __future__ import annotations

from typing import Dict, List, Optional, Union, Any, Tuple, Literal
from typing import TYPE_CHECKING

import sys
import errno
import os

import numpy as np
from numpy.typing import ArrayLike
import pandas as pd
import base64
from io import BytesIO
from datetime import datetime
import networkx as nx

import torch

from scipy.spatial.distance import cosine
from sklearn.metrics import jaccard_score
from sklearn.metrics import mutual_info_score
from sklearn.preprocessing import KBinsDiscretizer
from scipy import stats
import matplotlib.pyplot as plt

from bspline_mutual_information import mutual_information

from valpas import AssociationResult
from valpas._core import autoencoder
from valpas._core import weightedcorrelationmodel
from valpas._core import clr_transform
from .classes.analysisresults import AnalysisResults

if TYPE_CHECKING:
    from valpas._typing import(
        CrossExperiment,
        SingleExperiment,
    )

import warnings
warnings.filterwarnings('ignore')

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

    # we are currently building out the AnalysisResults usage
    analysis_results = None

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
        analysis_results = autoencoder.train_proteomics_autoencoder(
            experiment.measurements.transpose(),
            **autoencoder_args)

        result_values = analysis_results.similarity_matrix
        dataset = analysis_results.dataset
        model = analysis_results.trained_model
        training_history = analysis_results.training_history

        autoencoder.save_autoencoder_results(model, dataset, training_history, result_values)

        result_counts = result_values.copy(deep=True)
        result_counts.iloc[:, :] = len(experiment.measurements.transpose().columns)

    elif method == 'learn_correlation':
        analysis_results = weightedcorrelationmodel.learn_correlation_weights(
            data=experiment.measurements.transpose(),
            interactions=training_interactions,
            verbose=True,
            **learncorr_args
        )

        # now returns an analysis results object
        result_values = analysis_results.correlation_matrix

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

    # if we didn't have a specific one made above then
    if not analysis_results:
        # Create results object
        analysis_results = StatisticalAssociationResults(
            similarity_matrix=result_values,
            input_data=experiment.measurements.transpose(),
            method=method
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

class StatisticalAssociationResults(AnalysisResults):
    """
    Specialized class for statistical association analysis results
    """

    def __init__(self, similarity_matrix: pd.DataFrame, input_data: pd.DataFrame = None,
                 method: str = 'unknown', method_params: Dict = None,
                 significance_matrix: pd.DataFrame = None, metadata: Dict = None):
        """
        Initialize statistical association analysis results

        Args:
            similarity_matrix: Square matrix of association scores between entities
            input_data: Original dataset used to compute associations
            method: Association method used ('pearson', 'spearman', 'cosine', 'mutual_info', etc.)
            method_params: Parameters used in the association calculation
            significance_matrix: Optional p-values or significance scores
            metadata: Additional metadata about the analysis
        """
        super().__init__(
            results_dict={'similarity_matrix': similarity_matrix},
            analysis_type=f"Statistical Association Analysis ({method.title()})",
            metadata=metadata or {}
        )

        self.similarity_matrix = similarity_matrix
        self.input_data = input_data
        self.method = method.lower()
        self.method_params = method_params or {}
        self.significance_matrix = significance_matrix

        # Validate inputs
        self._validate_inputs()

        # Calculate comprehensive statistics
        self.association_stats = self._calculate_association_statistics()
        self.distribution_analysis = self._analyze_distribution()
        self.network_properties = self._calculate_network_properties()
        self.quality_metrics = self._assess_quality()

        # Store in results dict for base class compatibility
        self.results.update({
            'association_stats': self.association_stats,
            'distribution_analysis': self.distribution_analysis,
            'network_properties': self.network_properties,
            'quality_metrics': self.quality_metrics,
            'method': self.method,
            'method_params': self.method_params
        })

    def _validate_inputs(self):
        """Validate input data consistency"""
        # Check similarity matrix is square
        if self.similarity_matrix.shape[0] != self.similarity_matrix.shape[1]:
            raise ValueError("Similarity matrix must be square")

        # Check diagonal values for method-specific expectations
        diag_values = np.diag(self.similarity_matrix.values)
        if self.method in ['pearson', 'spearman', 'cosine']:
            if not np.allclose(diag_values, 1.0, atol=0.01):
                warnings.warn(f"Diagonal values should be ~1.0 for {self.method} correlation")

        # Check value ranges
        if self.method in ['pearson', 'spearman']:
            if (self.similarity_matrix.values < -1.1).any() or (self.similarity_matrix.values > 1.1).any():
                warnings.warn("Correlation values outside [-1, 1] range detected")
        elif self.method == 'cosine':
            if (self.similarity_matrix.values < -0.01).any() or (self.similarity_matrix.values > 1.01).any():
                warnings.warn("Cosine similarity values outside [0, 1] range detected")

        # Check symmetry
        if not np.allclose(self.similarity_matrix.values, self.similarity_matrix.values.T, atol=1e-10):
            warnings.warn("Similarity matrix is not symmetric")

        # Validate significance matrix if provided
        if self.significance_matrix is not None:
            if self.significance_matrix.shape != self.similarity_matrix.shape:
                raise ValueError("Significance matrix must have same shape as similarity matrix")

    def _calculate_association_statistics(self) -> Dict:
        """Calculate comprehensive association statistics"""
        # Get upper triangle (excluding diagonal)
        mask = np.triu(np.ones_like(self.similarity_matrix.values, dtype=bool), k=1)
        values = self.similarity_matrix.values[mask]

        # Remove NaN values
        valid_values = values[~np.isnan(values)]

        if len(valid_values) == 0:
            return {'error': 'No valid association values found'}

        stats_dict = {
            'n_comparisons': len(valid_values),
            'n_entities': len(self.similarity_matrix),
            'mean_association': np.mean(valid_values),
            'std_association': np.std(valid_values),
            'median_association': np.median(valid_values),
            'min_association': np.min(valid_values),
            'max_association': np.max(valid_values),
            'q25': np.percentile(valid_values, 25),
            'q75': np.percentile(valid_values, 75),
            'iqr': np.percentile(valid_values, 75) - np.percentile(valid_values, 25),
        }

        # Method-specific statistics
        if self.method in ['pearson', 'spearman']:
            stats_dict.update({
                'positive_correlations': np.sum(valid_values > 0),
                'negative_correlations': np.sum(valid_values < 0),
                'strong_positive': np.sum(valid_values > 0.7),
                'strong_negative': np.sum(valid_values < -0.7),
                'moderate_positive': np.sum((valid_values > 0.3) & (valid_values <= 0.7)),
                'moderate_negative': np.sum((valid_values < -0.3) & (valid_values >= -0.7)),
                'weak_associations': np.sum(np.abs(valid_values) <= 0.3),
            })

        elif self.method == 'cosine':
            stats_dict.update({
                'high_similarity': np.sum(valid_values > 0.8),
                'moderate_similarity': np.sum((valid_values > 0.5) & (valid_values <= 0.8)),
                'low_similarity': np.sum(valid_values <= 0.5),
            })

        elif self.method == 'mutual_info':
            stats_dict.update({
                'high_information': np.sum(valid_values > np.percentile(valid_values, 90)),
                'low_information': np.sum(valid_values < np.percentile(valid_values, 10)),
            })

        return stats_dict

    def _analyze_distribution(self) -> Dict:
        """Analyze the distribution of association values"""
        mask = np.triu(np.ones_like(self.similarity_matrix.values, dtype=bool), k=1)
        values = self.similarity_matrix.values[mask]
        valid_values = values[~np.isnan(values)]

        if len(valid_values) == 0:
            return {'error': 'No valid values for distribution analysis'}

        # Basic distribution properties
        distribution_stats = {
            'skewness': stats.skew(valid_values),
            'kurtosis': stats.kurtosis(valid_values),
            'normality_test_statistic': None,
            'normality_p_value': None,
        }

        # Test for normality
        if len(valid_values) >= 8:  # Minimum for Shapiro-Wilk
            if len(valid_values) <= 5000:  # Shapiro-Wilk limit
                stat, p_val = stats.shapiro(valid_values)
                distribution_stats['normality_test'] = 'shapiro_wilk'
            else:
                stat, p_val = stats.normaltest(valid_values)
                distribution_stats['normality_test'] = 'dagostino_pearson'

            distribution_stats['normality_test_statistic'] = stat
            distribution_stats['normality_p_value'] = p_val

        # Detect outliers
        q1, q3 = np.percentile(valid_values, [25, 75])
        iqr = q3 - q1
        lower_bound = q1 - 1.5 * iqr
        upper_bound = q3 + 1.5 * iqr

        outliers = valid_values[(valid_values < lower_bound) | (valid_values > upper_bound)]
        distribution_stats.update({
            'n_outliers': len(outliers),
            'outlier_percentage': len(outliers) / len(valid_values) * 100,
            'outlier_bounds': (lower_bound, upper_bound)
        })

        return distribution_stats

    def _calculate_network_properties(self) -> Dict:
        """Calculate network properties from the association matrix"""
        try:
            # Create a network from high associations
            threshold = self._determine_network_threshold()

            # Create adjacency matrix
            adj_matrix = (np.abs(self.similarity_matrix.values) > threshold).astype(int)
            np.fill_diagonal(adj_matrix, 0)  # Remove self-loops

            # Create NetworkX graph
            G = nx.from_numpy_array(adj_matrix)

            # Calculate network properties
            network_props = {
                'threshold_used': threshold,
                'n_nodes': G.number_of_nodes(),
                'n_edges': G.number_of_edges(),
                'density': nx.density(G),
                'n_components': nx.number_connected_components(G),
                'largest_component_size': len(max(nx.connected_components(G), key=len)) if nx.number_connected_components(G) > 0 else 0,
            }

            # Additional properties for connected graphs
            if nx.is_connected(G):
                network_props.update({
                    'average_shortest_path': nx.average_shortest_path_length(G),
                    'diameter': nx.diameter(G),
                    'radius': nx.radius(G)
                })

            # Degree statistics
            degrees = [d for n, d in G.degree()]
            if degrees:
                network_props.update({
                    'mean_degree': np.mean(degrees),
                    'max_degree': np.max(degrees),
                    'degree_assortativity': nx.degree_assortativity_coefficient(G)
                })

            # Clustering coefficient
            if G.number_of_edges() > 0:
                network_props['average_clustering'] = nx.average_clustering(G)

        except Exception as e:
            network_props = {'error': f'Network analysis failed: {str(e)}'}

        return network_props

    def _determine_network_threshold(self) -> float:
        """Determine appropriate threshold for network construction"""
        mask = np.triu(np.ones_like(self.similarity_matrix.values, dtype=bool), k=1)
        values = np.abs(self.similarity_matrix.values[mask])
        valid_values = values[~np.isnan(values)]

        if len(valid_values) == 0:
            return 0.5

        # Use different thresholds based on method
        if self.method in ['pearson', 'spearman']:
            return max(0.3, np.percentile(valid_values, 90))
        elif self.method == 'cosine':
            return max(0.5, np.percentile(valid_values, 85))
        elif self.method == 'mutual_info':
            return np.percentile(valid_values, 85)
        else:
            return np.percentile(valid_values, 90)

    def _assess_quality(self) -> Dict:
        """Assess the quality of the association analysis"""
        quality_metrics = {}

        # Data completeness
        total_cells = self.similarity_matrix.size
        non_nan_cells = (~pd.isna(self.similarity_matrix.values)).sum()
        quality_metrics['data_completeness'] = non_nan_cells / total_cells

        # Dynamic range
        mask = np.triu(np.ones_like(self.similarity_matrix.values, dtype=bool), k=1)
        values = self.similarity_matrix.values[mask]
        valid_values = values[~np.isnan(values)]

        if len(valid_values) > 0:
            quality_metrics['dynamic_range'] = np.max(valid_values) - np.min(valid_values)
            quality_metrics['effective_range'] = np.percentile(valid_values, 95) - np.percentile(valid_values, 5)

        # Signal-to-noise estimation (if input data available)
        if self.input_data is not None:
            quality_metrics['signal_to_noise'] = self._estimate_signal_to_noise()

        # Method-specific quality metrics
        if self.method in ['pearson', 'spearman']:
            quality_metrics['correlation_strength'] = np.mean(np.abs(valid_values)) if len(valid_values) > 0 else 0

        # Overall quality assessment
        quality_score = 0
        if quality_metrics.get('data_completeness', 0) > 0.95:
            quality_score += 0.3
        if quality_metrics.get('dynamic_range', 0) > 0.5:
            quality_score += 0.3
        if quality_metrics.get('correlation_strength', 0) > 0.2:
            quality_score += 0.4

        quality_metrics['overall_quality_score'] = quality_score

        return quality_metrics

    def _estimate_signal_to_noise(self) -> float:
        """Estimate signal-to-noise ratio from input data"""
        try:
            # Simple signal-to-noise estimation
            if self.input_data is not None:
                data_std = self.input_data.std().mean()
                data_mean = np.abs(self.input_data.mean()).mean()
                return data_mean / data_std if data_std > 0 else 0
        except:
            pass
        return 0

    def get_summary_stats(self) -> Dict:
        """Get comprehensive summary statistics"""
        base_stats = super().get_summary_stats()

        method_stats = {
            'association_method': self.method,
            'n_entities': self.association_stats.get('n_entities', 0),
            'n_comparisons': self.association_stats.get('n_comparisons', 0),
            'mean_association': self.association_stats.get('mean_association', 0),
            'association_range': f"[{self.association_stats.get('min_association', 0):.3f}, {self.association_stats.get('max_association', 0):.3f}]"
        }

        quality_stats = {
            'data_completeness': f"{self.quality_metrics.get('data_completeness', 0):.1%}",
            'dynamic_range': self.quality_metrics.get('dynamic_range', 0),
            'quality_assessment': self._get_quality_assessment()
        }

        network_stats = {}
        if 'error' not in self.network_properties:
            network_stats = {
                'network_edges': self.network_properties.get('n_edges', 0),
                'network_density': self.network_properties.get('density', 0),
                'connected_components': self.network_properties.get('n_components', 0)
            }

        return {**base_stats, **method_stats, **quality_stats, **network_stats}

    def _get_quality_assessment(self) -> str:
        """Get qualitative assessment of analysis quality"""
        score = self.quality_metrics.get('overall_quality_score', 0)

        if score >= 0.8:
            return "Excellent"
        elif score >= 0.6:
            return "Good"
        elif score >= 0.4:
            return "Fair"
        elif score >= 0.2:
            return "Poor"
        else:
            return "Very Poor"

    def get_top_associations(self, n: int = 10, absolute: bool = False) -> pd.DataFrame:
        """Get top N associations"""
        # Get upper triangle values with indices
        associations = []

        for i in range(len(self.similarity_matrix)):
            for j in range(i+1, len(self.similarity_matrix.columns)):
                value = self.similarity_matrix.iloc[i, j]
                if not pd.isna(value):
                    associations.append({
                        'entity_1': self.similarity_matrix.index[i],
                        'entity_2': self.similarity_matrix.columns[j],
                        'association': value,
                        'abs_association': abs(value)
                    })

        df = pd.DataFrame(associations)

        if df.empty:
            return df

        # Sort by absolute or raw value
        sort_col = 'abs_association' if absolute else 'association'
        return df.nlargest(n, sort_col)[['entity_1', 'entity_2', 'association']]

    def get_association_distribution_stats(self) -> Dict:
        """Get detailed distribution statistics"""
        stats = {}

        if self.method in ['pearson', 'spearman']:
            stats.update({
                'positive_correlations': self.association_stats.get('positive_correlations', 0),
                'negative_correlations': self.association_stats.get('negative_correlations', 0),
                'strong_correlations': self.association_stats.get('strong_positive', 0) + self.association_stats.get('strong_negative', 0),
                'weak_correlations': self.association_stats.get('weak_associations', 0)
            })

        stats.update({
            'skewness': self.distribution_analysis.get('skewness', 0),
            'kurtosis': self.distribution_analysis.get('kurtosis', 0),
            'outliers': self.distribution_analysis.get('n_outliers', 0),
            'normality_p_value': self.distribution_analysis.get('normality_p_value', None)
        })

        return stats

    def _generate_detailed_text(self) -> List[str]:
        """Generate detailed text representation"""
        lines = []

        # Method Information
        lines.append("ASSOCIATION METHOD:")
        lines.append(f"  Method: {self.method.title()}")
        if self.method_params:
            lines.append("  Parameters:")
            for key, value in self.method_params.items():
                lines.append(f"    {key}: {value}")
        lines.append("")

        # Association Statistics
        lines.append("ASSOCIATION STATISTICS:")
        lines.append(f"  Number of entities: {self.association_stats.get('n_entities', 0)}")
        lines.append(f"  Number of comparisons: {self.association_stats.get('n_comparisons', 0)}")
        lines.append(f"  Mean association: {self.association_stats.get('mean_association', 0):.4f}")
        lines.append(f"  Standard deviation: {self.association_stats.get('std_association', 0):.4f}")
        lines.append(f"  Range: [{self.association_stats.get('min_association', 0):.4f}, {self.association_stats.get('max_association', 0):.4f}]")
        lines.append(f"  Median: {self.association_stats.get('median_association', 0):.4f}")
        lines.append(f"  IQR: {self.association_stats.get('iqr', 0):.4f}")
        lines.append("")

        # Method-specific statistics
        if self.method in ['pearson', 'spearman']:
            lines.append("CORRELATION BREAKDOWN:")
            lines.append(f"  Positive correlations: {self.association_stats.get('positive_correlations', 0)}")
            lines.append(f"  Negative correlations: {self.association_stats.get('negative_correlations', 0)}")
            lines.append(f"  Strong positive (>0.7): {self.association_stats.get('strong_positive', 0)}")
            lines.append(f"  Strong negative (<-0.7): {self.association_stats.get('strong_negative', 0)}")
            lines.append(f"  Weak associations (|r|≤0.3): {self.association_stats.get('weak_associations', 0)}")
            lines.append("")

        # Distribution Analysis
        lines.append("DISTRIBUTION ANALYSIS:")
        lines.append(f"  Skewness: {self.distribution_analysis.get('skewness', 0):.4f}")
        lines.append(f"  Kurtosis: {self.distribution_analysis.get('kurtosis', 0):.4f}")
        lines.append(f"  Outliers: {self.distribution_analysis.get('n_outliers', 0)} ({self.distribution_analysis.get('outlier_percentage', 0):.2f}%)")

        if self.distribution_analysis.get('normality_p_value') is not None:
            lines.append(f"  Normality test p-value: {self.distribution_analysis.get('normality_p_value', 0):.4f}")
        lines.append("")

        # Network Properties
        if 'error' not in self.network_properties:
            lines.append("NETWORK PROPERTIES:")
            lines.append(f"  Threshold used: {self.network_properties.get('threshold_used', 0):.4f}")
            lines.append(f"  Edges: {self.network_properties.get('n_edges', 0)}")
            lines.append(f"  Density: {self.network_properties.get('density', 0):.4f}")
            lines.append(f"  Connected components: {self.network_properties.get('n_components', 0)}")
            lines.append(f"  Largest component size: {self.network_properties.get('largest_component_size', 0)}")

            if 'average_clustering' in self.network_properties:
                lines.append(f"  Average clustering: {self.network_properties['average_clustering']:.4f}")
            lines.append("")

        # Quality Assessment
        lines.append("QUALITY ASSESSMENT:")
        lines.append(f"  Data completeness: {self.quality_metrics.get('data_completeness', 0):.1%}")
        lines.append(f"  Dynamic range: {self.quality_metrics.get('dynamic_range', 0):.4f}")
        lines.append(f"  Overall quality: {self._get_quality_assessment()}")
        lines.append("")

        # Top Associations
        top_assoc = self.get_top_associations(5, absolute=True)
        if not top_assoc.empty:
            lines.append("TOP 5 ASSOCIATIONS (by absolute value):")
            for idx, row in top_assoc.iterrows():
                lines.append(f"  {row['entity_1']} - {row['entity_2']}: {row['association']:.4f}")
            lines.append("")

        return lines

    def _generate_detailed_html(self) -> str:
        """Generate detailed HTML representation"""
        html_parts = []

        # Method Information
        html_parts.append('<h3>Association Method</h3>')
        html_parts.append('<table class="results-table">')
        html_parts.append('<tr><th>Parameter</th><th>Value</th></tr>')
        html_parts.append(f'<tr><td>Method</td><td>{self.method.title()}</td></tr>')

        for key, value in self.method_params.items():
            html_parts.append(f'<tr><td>{key.replace("_", " ").title()}</td><td>{value}</td></tr>')

        html_parts.append('</table>')

        # Association Statistics
        html_parts.append('<h3>Association Statistics</h3>')
        html_parts.append('<table class="results-table">')
        html_parts.append('<tr><th>Statistic</th><th>Value</th><th>Interpretation</th></tr>')

        stats_rows = [
            ('Entities', self.association_stats.get('n_entities', 0), f"{self.association_stats.get('n_entities', 0)} entities analyzed"),
            ('Comparisons', self.association_stats.get('n_comparisons', 0), f"{self.association_stats.get('n_comparisons', 0)} pairwise comparisons"),
            ('Mean Association', f"{self.association_stats.get('mean_association', 0):.4f}", self._interpret_association_strength(self.association_stats.get('mean_association', 0))),
            ('Standard Deviation', f"{self.association_stats.get('std_association', 0):.4f}", "Variability in associations"),
            ('Range', f"[{self.association_stats.get('min_association', 0):.3f}, {self.association_stats.get('max_association', 0):.3f}]", "Min to max association values")
        ]

        for stat, value, interpretation in stats_rows:
            html_parts.append(f'<tr><td>{stat}</td><td>{value}</td><td>{interpretation}</td></tr>')

        html_parts.append('</table>')

        # Method-specific breakdown
        if self.method in ['pearson', 'spearman']:
            html_parts.append('<h3>Correlation Breakdown</h3>')
            html_parts.append('<table class="results-table">')
            html_parts.append('<tr><th>Category</th><th>Count</th><th>Percentage</th></tr>')

            total = self.association_stats.get('n_comparisons', 1)
            breakdown_data = [
                ('Strong Positive (>0.7)', self.association_stats.get('strong_positive', 0)),
                ('Moderate Positive (0.3-0.7)', self.association_stats.get('moderate_positive', 0)),
                ('Weak (|r|≤0.3)', self.association_stats.get('weak_associations', 0)),
                ('Moderate Negative (-0.7--0.3)', self.association_stats.get('moderate_negative', 0)),
                ('Strong Negative (<-0.7)', self.association_stats.get('strong_negative', 0))
            ]

            for category, count in breakdown_data:
                percentage = (count / total) * 100 if total > 0 else 0
                html_parts.append(f'<tr><td>{category}</td><td>{count}</td><td>{percentage:.1f}%</td></tr>')

            html_parts.append('</table>')

        # Top Associations
        top_assoc = self.get_top_associations(10, absolute=True)
        if not top_assoc.empty:
            html_parts.append('<h3>Top Associations</h3>')
            html_parts.append('<table class="results-table">')
            html_parts.append('<tr><th>Rank</th><th>Entity 1</th><th>Entity 2</th><th>Association</th></tr>')

            for idx, (_, row) in enumerate(top_assoc.iterrows(), 1):
                html_parts.append(f'<tr><td>{idx}</td><td>{row["entity_1"]}</td><td>{row["entity_2"]}</td><td>{row["association"]:.4f}</td></tr>')

            html_parts.append('</table>')

        # Quality Assessment
        html_parts.append('<h3>Quality Assessment</h3>')
        html_parts.append('<table class="results-table">')
        html_parts.append('<tr><th>Metric</th><th>Value</th><th>Assessment</th></tr>')

        quality_class = self._get_quality_css_class(self._get_quality_assessment())

        quality_rows = [
            ('Data Completeness', f"{self.quality_metrics.get('data_completeness', 0):.1%}", "Percentage of non-missing values"),
            ('Dynamic Range', f"{self.quality_metrics.get('dynamic_range', 0):.4f}", "Spread of association values"),
            ('Overall Quality', self._get_quality_assessment(), f'<span class="{quality_class}">Quality assessment</span>')
        ]

        for metric, value, assessment in quality_rows:
            html_parts.append(f'<tr><td>{metric}</td><td>{value}</td><td>{assessment}</td></tr>')

        html_parts.append('</table>')

        return '\n'.join(html_parts)

    def _interpret_association_strength(self, value: float) -> str:
        """Interpret association strength based on method"""
        abs_val = abs(value)

        if self.method in ['pearson', 'spearman']:
            if abs_val >= 0.9:
                return "Very strong correlation"
            elif abs_val >= 0.7:
                return "Strong correlation"
            elif abs_val >= 0.5:
                return "Moderate correlation"
            elif abs_val >= 0.3:
                return "Weak correlation"
            else:
                return "Very weak correlation"

        elif self.method == 'cosine':
            if abs_val >= 0.9:
                return "Very high similarity"
            elif abs_val >= 0.7:
                return "High similarity"
            elif abs_val >= 0.5:
                return "Moderate similarity"
            else:
                return "Low similarity"

        else:
            return "Association strength varies by method"

    def _get_quality_css_class(self, quality_str: str) -> str:
        """Get CSS class for quality assessment"""
        quality_lower = quality_str.lower()
        if quality_lower in ['excellent', 'good']:
            return 'metric-good'
        elif quality_lower == 'fair':
            return 'metric-warning'
        else:
            return 'metric-poor'

    def create_plots(self, figsize: Tuple[int, int] = (16, 12), **kwargs) -> Dict:
        """Create visualization plots for association analysis"""
        plots = {}

        try:
            # 1. Association matrix heatmap
            fig1 = plt.figure(figsize=(12, 10))

            # Main heatmap
            ax1 = plt.subplot(2, 2, 1)

            # Sample for display if too large
            if len(self.similarity_matrix) > 100:
                sample_indices = np.random.choice(len(self.similarity_matrix), 100, replace=False)
                plot_matrix = self.similarity_matrix.iloc[sample_indices, sample_indices]
                title_suffix = " (100 random entities)"
            else:
                plot_matrix = self.similarity_matrix
                title_suffix = ""

            # Choose colormap based on method
            if self.method in ['pearson', 'spearman']:
                cmap = 'RdBu_r'
                center = 0
            else:
                cmap = 'viridis'
                center = None

            sns.heatmap(plot_matrix, cmap=cmap, center=center, square=True,
                       cbar_kws={'label': f'{self.method.title()} Association'}, ax=ax1)
            ax1.set_title(f'{self.method.title()} Association Matrix{title_suffix}')

            # Distribution histogram
            ax2 = plt.subplot(2, 2, 2)
            mask = np.triu(np.ones_like(self.similarity_matrix.values, dtype=bool), k=1)
            values = self.similarity_matrix.values[mask]
            valid_values = values[~np.isnan(values)]

            ax2.hist(valid_values, bins=50, alpha=0.7, edgecolor='black', density=True)
            ax2.axvline(np.mean(valid_values), color='red', linestyle='--',
                       label=f'Mean: {np.mean(valid_values):.3f}')
            ax2.axvline(np.median(valid_values), color='orange', linestyle='--',
                       label=f'Median: {np.median(valid_values):.3f}')
            ax2.set_xlabel(f'{self.method.title()} Association')
            ax2.set_ylabel('Density')
            ax2.set_title('Association Distribution')
            ax2.legend()
            ax2.grid(True, alpha=0.3)

            # Q-Q plot for normality
            ax3 = plt.subplot(2, 2, 3)
            try:
                stats.probplot(valid_values, dist="norm", plot=ax3)
                ax3.set_title('Q-Q Plot (Normality Check)')
                ax3.grid(True, alpha=0.3)
            except:
                ax3.text(0.5, 0.5, 'Q-Q plot not available', ha='center', va='center', transform=ax3.transAxes)
                ax3.set_title('Q-Q Plot')

            # Method-specific plot
            ax4 = plt.subplot(2, 2, 4)

            if self.method in ['pearson', 'spearman']:
                # Correlation strength breakdown
                categories = ['Strong\nPositive', 'Moderate\nPositive', 'Weak', 'Moderate\nNegative', 'Strong\nNegative']
                counts = [
                    self.association_stats.get('strong_positive', 0),
                    self.association_stats.get('moderate_positive', 0),
                    self.association_stats.get('weak_associations', 0),
                    self.association_stats.get('moderate_negative', 0),
                    self.association_stats.get('strong_negative', 0)
                ]
                colors = ['darkgreen', 'lightgreen', 'gray', 'lightcoral', 'darkred']

                bars = ax4.bar(categories, counts, color=colors, alpha=0.7)
                ax4.set_ylabel('Count')
                ax4.set_title('Correlation Strength Distribution')
                ax4.grid(True, alpha=0.3)

                # Add value labels
                for bar, count in zip(bars, counts):
                    if count > 0:
                        ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(counts)*0.01,
                                str(count), ha='center', va='bottom')
            else:
                # Generic association strength plot
                bins = np.linspace(np.min(valid_values), np.max(valid_values), 6)
                hist, _ = np.histogram(valid_values, bins=bins)
                bin_centers = (bins[:-1] + bins[1:]) / 2

                ax4.bar(bin_centers, hist, width=np.diff(bins), alpha=0.7, edgecolor='black')
                ax4.set_xlabel(f'{self.method.title()} Association')
                ax4.set_ylabel('Count')
                ax4.set_title('Association Value Distribution')
                ax4.grid(True, alpha=0.3)

            plt.tight_layout()
            plots['association_analysis'] = fig1

            # 2. Network visualization (if network properties calculated)
            if 'error' not in self.network_properties and self.network_properties.get('n_edges', 0) > 0:
                fig2 = plt.figure(figsize=(14, 10))

                # Network metrics
                ax1 = plt.subplot(2, 3, 1)
                metrics = ['Nodes', 'Edges', 'Components']
                values = [
                    self.network_properties.get('n_nodes', 0),
                    self.network_properties.get('n_edges', 0),
                    self.network_properties.get('n_components', 0)
                ]

                bars = ax1.bar(metrics, values, alpha=0.7)
                ax1.set_ylabel('Count')
                ax1.set_title('Network Structure')
                ax1.grid(True, alpha=0.3)

                for bar, val in zip(bars, values):
                    ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + max(values)*0.01,
                            str(val), ha='center', va='bottom')

                # Density and clustering
                ax2 = plt.subplot(2, 3, 2)
                properties = []
                prop_values = []

                if 'density' in self.network_properties:
                    properties.append('Density')
                    prop_values.append(self.network_properties['density'])

                if 'average_clustering' in self.network_properties:
                    properties.append('Avg\nClustering')
                    prop_values.append(self.network_properties['average_clustering'])

                if properties:
                    bars = ax2.bar(properties, prop_values, alpha=0.7, color='orange')
                    ax2.set_ylabel('Value')
                    ax2.set_title('Network Properties')
                    ax2.set_ylim(0, 1)
                    ax2.grid(True, alpha=0.3)

                    for bar, val in zip(bars, prop_values):
                        ax2.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                                f'{val:.3f}', ha='center', va='bottom')

                # Network summary
                ax3 = plt.subplot(2, 3, (3, 6))
                ax3.axis('off')

                network_summary = f"""Network Analysis Summary:

Threshold: {self.network_properties.get('threshold_used', 0):.4f}
Nodes: {self.network_properties.get('n_nodes', 0)}
Edges: {self.network_properties.get('n_edges', 0)}
Density: {self.network_properties.get('density', 0):.4f}

Connected Components: {self.network_properties.get('n_components', 0)}
Largest Component: {self.network_properties.get('largest_component_size', 0)} nodes

Mean Degree: {self.network_properties.get('mean_degree', 0):.2f}
Max Degree: {self.network_properties.get('max_degree', 0)}

{"Average Clustering: " + str(round(self.network_properties.get('average_clustering', 0), 4)) if 'average_clustering' in self.network_properties else ''}
                """

                ax3.text(0.05, 0.95, network_summary, transform=ax3.transAxes, fontsize=11,
                        verticalalignment='top', fontfamily='monospace',
                        bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.8))

                plt.tight_layout()
                plots['network_analysis'] = fig2

            # 3. Quality assessment plot
            fig3 = plt.figure(figsize=(12, 8))

            # Quality metrics radar chart (simplified)
            ax1 = plt.subplot(1, 2, 1)

            quality_metrics = {
                'Data\nCompleteness': self.quality_metrics.get('data_completeness', 0),
                'Dynamic\nRange': min(self.quality_metrics.get('dynamic_range', 0) / 2, 1),  # Normalize
                'Signal\nStrength': min(self.quality_metrics.get('correlation_strength', 0) * 2, 1) if 'correlation_strength' in self.quality_metrics else 0.5
            }

            categories = list(quality_metrics.keys())
            values = list(quality_metrics.values())

            bars = ax1.bar(categories, values, alpha=0.7, color=['green', 'blue', 'orange'])
            ax1.set_ylim(0, 1)
            ax1.set_ylabel('Quality Score')
            ax1.set_title('Quality Assessment')
            ax1.grid(True, alpha=0.3)

            for bar, val in zip(bars, values):
                ax1.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.02,
                        f'{val:.3f}', ha='center', va='bottom')

            # Overall summary
            ax2 = plt.subplot(1, 2, 2)
            ax2.axis('off')

            summary_text = f"""Analysis Summary:

Method: {self.method.title()}
Entities: {self.association_stats.get('n_entities', 0)}
Comparisons: {self.association_stats.get('n_comparisons', 0)}

Association Statistics:
  Mean: {self.association_stats.get('mean_association', 0):.4f}
  Std: {self.association_stats.get('std_association', 0):.4f}
  Range: [{self.association_stats.get('min_association', 0):.3f}, {self.association_stats.get('max_association', 0):.3f}]

Distribution:
  Skewness: {self.distribution_analysis.get('skewness', 0):.3f}
  Outliers: {self.distribution_analysis.get('n_outliers', 0)}

Quality: {self._get_quality_assessment()}
            """

            ax2.text(0.05, 0.95, summary_text, transform=ax2.transAxes, fontsize=11,
                    verticalalignment='top', fontfamily='monospace',
                    bbox=dict(boxstyle='round', facecolor='lightgray', alpha=0.8))

            plt.tight_layout()
            plots['quality_assessment'] = fig3

        except Exception as e:
            print(f"Warning: Error creating plots: {e}")

        return plots

    def export_associations(self, filepath: str, format: str = 'csv', threshold: float = None):
        """
        Export association data to file

        Args:
            filepath: Path to save file
            format: Format ('csv', 'excel', 'json')
            threshold: Optional threshold to filter associations
        """
        # Create association list
        associations = []

        for i in range(len(self.similarity_matrix)):
            for j in range(i+1, len(self.similarity_matrix.columns)):
                value = self.similarity_matrix.iloc[i, j]

                if not pd.isna(value) and (threshold is None or abs(value) >= threshold):
                    associations.append({
                        'entity_1': self.similarity_matrix.index[i],
                        'entity_2': self.similarity_matrix.columns[j],
                        'association': value,
                        'abs_association': abs(value)
                    })

        df = pd.DataFrame(associations).sort_values('abs_association', ascending=False)

        if format == 'csv':
            df.to_csv(filepath, index=False)
        elif format == 'excel':
            df.to_excel(filepath, index=False)
        elif format == 'json':
            df.to_json(filepath, orient='records', indent=2)
        else:
            raise ValueError(f"Unsupported format: {format}")

        print(f"Exported {len(df)} associations to {filepath}")

# Example usage and testing
if __name__ == "__main__":
    # Create sample data for testing
    np.random.seed(42)

    # Generate sample dataset
    n_entities = 50
    n_features = 100

    entity_names = [f'Entity_{i:03d}' for i in range(n_entities)]
    feature_names = [f'Feature_{i:03d}' for i in range(n_features)]

    # Create structured data with some correlations
    data = np.random.randn(n_entities, n_features)

    # Add some correlation structure
    for i in range(0, n_entities, 5):
        end_idx = min(i + 3, n_entities)
        base_pattern = np.random.randn(n_features)
        for j in range(i, end_idx):
            data[j] = base_pattern + 0.3 * np.random.randn(n_features)

    input_df = pd.DataFrame(data, index=entity_names, columns=feature_names)

    # Calculate different association matrices
    print("Testing StatisticalAssociationResults class...")

    # Test with Pearson correlation
    print("\n" + "="*60)
    print("Testing Pearson Correlation")
    print("="*60)

    pearson_matrix = input_df.T.corr(method='pearson')

    pearson_results = StatisticalAssociationResults(
        similarity_matrix=pearson_matrix,
        input_data=input_df,
        method='pearson',
        method_params={'method': 'pearson'},
        metadata={'description': 'Pearson correlation analysis'}
    )

    # Test summary stats
    summary = pearson_results.get_summary_stats()
    print("Summary stats:")
    for key, value in summary.items():
        print(f"  {key}: {value}")

    # Test text output
    print("\nText output (first 1000 chars):")
    text_output = pearson_results.to_text()
    print(text_output[:1000] + "...")

    # Test specific methods
    top_assoc = pearson_results.get_top_associations(5)
    print(f"\nTop 5 associations:\n{top_assoc}")

    dist_stats = pearson_results.get_association_distribution_stats()
    print(f"\nDistribution stats: {dist_stats}")

    # Test with cosine similarity
    print("\n" + "="*60)
    print("Testing Cosine Similarity")
    print("="*60)

    from sklearn.metrics.pairwise import cosine_similarity
    cosine_sim = cosine_similarity(input_df.values)
    cosine_df = pd.DataFrame(cosine_sim, index=entity_names, columns=entity_names)

    cosine_results = StatisticalAssociationResults(
        similarity_matrix=cosine_df,
        input_data=input_df,
        method='cosine',
        method_params={'metric': 'cosine'}
    )

    print(f"Cosine similarity summary: {cosine_results._get_quality_assessment()}")

    # Test plots
    print("\n" + "="*60)
    print("Creating plots...")
    print("="*60)

    plots = pearson_results.create_plots()
    print(f"Created {len(plots)} plots: {list(plots.keys())}")

    # Clean up plots
    for fig in plots.values():
        plt.close(fig)

    # Test HTML output
    print("\n" + "="*60)
    print("HTML output (first 500 chars):")
    print("="*60)
    html_output = pearson_results.to_html()
    print(html_output[:500] + "...")

    # Test export
    print("\n" + "="*60)
    print("Testing export functionality...")
    print("="*60)

    pearson_results.export_associations('test_associations.csv', threshold=0.5)
    pearson_results.save_results('test_pearson_results.html', format='html')

    print("Export completed")

    # Clean up test files
    import os
    for filename in ['test_associations.csv', 'test_pearson_results.html']:
        if os.path.exists(filename):
            os.remove(filename)

    print("\nTest completed successfully!")
