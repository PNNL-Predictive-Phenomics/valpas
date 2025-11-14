"""
valpas_core.py

Core functions for the VaLPAS framework, decoupled from the CLI for direct function calls.
"""

import sys
import pandas as pd
import networkx as nx
from pathlib import Path
from valpas import CrossExperiment
from valpas.utils.checker import check_infile, check_outfile, check_cutoff_range
from valpas.io import import_asssociation_matrix, import_experiments
from valpas.annotations import AnnotationList
from valpas._core.processing import combine_results
from valpas.visualization.heatmap import create_fig
from valpas.utils.validator import validate_input
from valpas.confidence_evaluation import calculate_edge_confidence_default
from ._core.processing import beautify_series

def associate(
    association_type="pearson",
    infile=None,
    infile2=None,
    infolder=None,
    file_type="csv",
    sheet=None,
    sheet2=None,
    output_type="sorted_list",
    filter_cutoff=0.9,
    min_counts=3,
    normalization="none",
    training_interactions=None,
    calculate_confidence=False,
    transform_clr=False,
    annotation_file=None,
    annotation_args: dict={
        'primary_id_column': 'id',
        'primary_annotation_column': 'annotation',
        'sheet_name': 0,
        'validate_ids': True,
        'remove_duplicates': 'warn',
        'handle_missing_annotations': 'keep',
        'strip_whitespace': True,
        'case_sensitive': True,
        'verbose': True
    },
    learncorr_args: dict={
        'learning_method':'empirical',
        'missing_strategy':'median'
    },
    autoencoder_args: dict={
        'protein_embedding_dim':128,
        'sample_embedding_dim':64,
        'hidden_dims':[256, 128],
        'epochs':200,
        'learning_rate':1e-3,
        'mask_probability':0.15,
        'scaling_method':'robust',
        'validation_split':0.2
    },
    subset_args: dict={
        'nconds':None,
        'percentage':None,
        'keep_conds':[],
        'inplace':False,
        'random_state':0,
    },
    confidence_args: dict={
        'negative_interactions': None,
        'exclude_negative_interactions': None,
        'protein_col1': 'protein1',
        'protein_col2': 'protein2',
        'weight_col': 'weight',
        'calculate_limit': 10000,
        'return_all': False,
        'confidence_metric': 'ppv',
        'additional_metrics': None,
        'min_threshold_samples': 1,
        'negative_ratio': 0,
        'normalize_pairs': False,
        'extrapolate_confidence': False,
    },
    overwrite_output=False,
    outfile=sys.stdout,
):
    """
    Establishes association values between items (e.g., proteins, lipids, or metabolites).

    Parameters:
        association_type (str): Type of association metric (e.g., 'spearman', 'pearson').
        infile (str or Path): Path to the primary file containing data points.
        infile2 (str or Path): Path to the optional second file (cross-omics).
        infolder (str or Path): Path to folder containing multiple files.
        file_type (str): File type ('csv' or 'xlsx').
        sheet (str): Name of the Excel sheet (if applicable).
        sheet2 (str): Secondary Excel sheet for the second file (if applicable).
        output_type (str): Output format ('sorted_list', 'correlation_matrix').
        filter_cutoff (float): Cutoff for filtering missing values.
        normalization (str): Normalization mode ('pre', 'post', 'none').
        transform_clr
        training_interactions
        calculate_confidence (bool): if True and training_interactions are
            provided then use training_interactions to calculate confidence
            values for predictions
        subset_args : dict, default = {}
            Keyword arguments to pass to subsetting function
        autoencoder_args : dict, default = {}
            Keyword arguments to pass to autoencoder function
        learncorr_args : dict, default = {}
            Keyword arguments to pass to learn correlation function
        confidence_args : dict, default = {}
            Keyword arguments to pass to confidence calculation function
        overwrite_output (bool): Whether to overwrite the existing output.
        outfile (str or Path): Path for saving the output file or `sys.stdout`.

    Returns:
        result: Computed associations as a DataFrame or saves to the outfile.
    """
    sheet_names = [sheet] if sheet else None
    if sheet2:
        sheet_names = sheet_names + [sheet2] if sheet_names is not None else [sheet2]

    if infolder:
        inpath = Path(infolder).absolute()
        files = [child for child in inpath.glob(f"*.{file_type}")]
        if file_type == "csv" and len(files) > 4:
            raise ValueError("Import of more than four CSV files currently not supported.")
        if file_type == "xlsx" and len(files) > 2:
            raise ValueError("Import of more than two XLSX files currently not supported.")
        inpath2 = None
    else:
        inpath = infile
        inpath2 = infile2

    experiments = import_experiments(
        path=inpath,
        file_type=file_type,
        source="from_folder" if infolder else "from_file",
        path2=inpath2,
        sheet_names=sheet_names,
    )

    if training_interactions:
        if not isinstance(training_interactions, list):
            # we will treat this as a file path and read in a list of tuples
            # for now assume that this is tab-delimited with a header
            df = pd.read_csv(training_interactions, sep='\t', header=1)
            training_interactions = list(zip(df.iloc[:, 0], df.iloc[:, 1]))

    threshold = 0.5 if association_type in [
        "jaccard_similarity",
        "jaccard_index",
        "jaccard_distance"
    ] else None
    thresholded = bool(threshold)

    if len(experiments) == 1:
        experiment = experiments.pop()
        experiment.pre_process(rm_low_conf_features=filter_cutoff, threshold=threshold, normalize=normalization, inplace=True)
        result = experiment.associate(metric=association_type, thresholded=thresholded,
                                      training_interactions=training_interactions,
                                      transform_clr=transform_clr,
                                      subset_args=subset_args,
                                      autoencoder_args=autoencoder_args,
                                      learncorr_args=learncorr_args)
    elif len(experiments) == 2:
        cross_experiment = CrossExperiment(name="cross_experiment", experiments=experiments)
        if normalization == "pre":
            for experiment in experiments:
                experiment.pre_process(rm_low_conf_features=filter_cutoff, normalize=True, threshold=threshold, inplace=True)
            cross_experiment.combine(inplace=True)
        elif normalization == "none":
            for experiment in experiments:
                experiment.pre_process(rm_low_conf_features=filter_cutoff, normalize=False, threshold=threshold, inplace=True)
            cross_experiment.combine(inplace=True)
        elif normalization == "post":
            results = []
            for experiment in experiments:
                experiment.pre_process(rm_low_conf_features=filter_cutoff, normalize=False, threshold=threshold, inplace=True)
                results.append(experiment.associate(metric=association_type, thresholded=thresholded,
                                                    training_interactions=training_interactions,
                                                    transform_clr=transform_clr,
                                                    subset_args=subset_args,
                                                    autoencoder_args=autoencoder_args,
                                                    learncorr_args=learncorr_args))
            result = combine_results(results=results, normalization_metric="mean")
        else:
            raise ValueError(f"Normalization mode '{normalization}' not supported.")
    else:
        raise NotImplementedError("Cross-experiment associations for more than 2 experiments not supported.")

    # handle incorporation of annotations
    if annotation_file:
        result.annotations = AnnotationList(annotation_file, **annotation_args)

    if calculate_confidence and training_interactions:
        # for now confidence evaluation operates on a list of edges
        # make an edgelist so we can do things with it
        # FIXME: this should really be integrated in to the result class so that
        #        we can add confidence and annotations there - instead of doing it here
        edgelist = result.as_list()

        # filter out self edges that seem to creep in somehow
        edgelist = edgelist[edgelist.iloc[:,0] != edgelist.iloc[:,1]]

        confidencelist = calculate_edge_confidence_default(edgelist,
                        positive_interactions=training_interactions,
                        min_counts=min_counts,
                        **confidence_args)

        # this will overwrite output no problems/no check
        # add support for overwrite checking
        confidencelist.to_csv(outfile, index=False)
        return result

    result.save(
        file_handle=outfile,
        type=output_type,
        overwrite=overwrite_output,
        assocation_metric=association_type,
    )
    return result


def prepare(infile=None, infile2=None, infolder=None, file_type="csv", sheet=None, sheet2=None):
    """
    Prepares and validates input data for association analysis.

    Parameters:
        infile (str or Path): Path to the primary file.
        infile2 (str or Path): Path to the optional second file.
        infolder (str or Path): Path to folder containing multiple files.
        file_type (str): File type ('csv' or 'xlsx').
        sheet (str): Name of the Excel sheet (if applicable).
        sheet2 (str): Secondary Excel sheet for the second file (if applicable).

    Returns:
        experiments: Validated experiment objects.
    """
    sheet_names = [sheet] if sheet else None
    if sheet2:
        sheet_names = sheet_names + [sheet2] if sheet_names is not None else [sheet2]

    if infolder:
        inpath = Path(infolder).absolute()
        files = [child for child in inpath.glob(f"*.{file_type}")]
    else:
        inpath = infile
        inpath2 = infile2

    experiments = import_experiments(
        path=inpath,
        file_type=file_type,
        source="from_folder" if infolder else "from_file",
        path2=inpath2,
        sheet_names=sheet_names,
    )

    validate_input(experiments)
    return experiments


def visualize(
    infile,
    sheet=None,
    visualization_type="heatmap",
    label="Association Strength",
    outfile=None
):
    """
    Visualizes association results.

    Parameters:
        infile (str or Path): Input file containing the association matrix.
        sheet (str): Name of the Excel sheet (if applicable).
        visualization_type (str): Type of visualization ('heatmap', 'graph').
        label (str): Label for the heatmap color bar.
        outfile (str or Path): Path for saving the visualization.

    Returns:
        fig: Generated figure object (optional).
    """
    sheet = sheet if sheet else 0
    try:
        df = import_asssociation_matrix(filepath=infile, sheet=sheet)
    except ValueError:
        raise ValueError(f"Sheet '{sheet}' not found in file '{infile}'")
    except FileNotFoundError:
        raise FileNotFoundError(f"File '{infile}' not found.")

    if visualization_type == "heatmap":
        fig = create_fig(df=df, fig_out=outfile, cbarlabel=label)
        return fig
    else:
        raise NotImplementedError("Only heatmap visualization is currently supported.")
