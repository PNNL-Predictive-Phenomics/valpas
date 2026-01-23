"""
The main script that gets executed.
"""

import argparse
import sys
import textwrap
import pandas as pd
import networkx as nx

from pathlib import Path

from valpas import CrossExperiment

from valpas.utils.checker import check_infile
from valpas.utils.checker import check_outfile
from valpas.utils.checker import check_cutoff_range

from valpas.visualization.heatmap import create_fig

from valpas.io import import_asssociation_matrix
from valpas.io import import_experiments

from valpas._core.processing import combine_results

from valpas.utils.validator import validate_input

# Import the core associate function
from valpas.valpas_core import associate as core_associate


def main():
    """
    The main method.
    """

    main_parser = argparse.ArgumentParser(
        prog="valpas",
        description=textwrap.dedent("""
            VaLPAS (Variation-Leveraged Phenomic Association Study) is a toolkit
            for generating associations between different omics datatypes.
        """),
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    command_parsers = main_parser.add_subparsers(
        dest="command",
        title="commands",
        required=True,
    )

    # =========================================================================
    # Shared argument parsers (to avoid repetition)
    # =========================================================================

    # Shared arguments for importing from file
    p_import_from_file = argparse.ArgumentParser(add_help=False)
    p_import_from_file.add_argument(
        "-i", "--infile",
        dest="INFILE",
        required=True,
        type=check_infile,
        help="Path to input data file."
    )
    p_import_from_file.add_argument(
        "-i2", "--infile2",
        dest="INFILE2",
        type=check_infile,
        help="Path to second input data file (for cross-experiment analysis)."
    )
    p_import_from_file.add_argument(
        "-s", "--sheet",
        dest="SHEET",
        type=str,
        help="Sheet name if input is an Excel file."
    )
    p_import_from_file.add_argument(
        "-s2", "--sheet2",
        dest="SHEET2",
        type=str,
        help="Sheet name for second input file if Excel."
    )

    # Shared arguments for importing from folder
    p_import_from_folder = argparse.ArgumentParser(add_help=False)
    p_import_from_folder.add_argument(
        "-d", "--infolder",
        dest="INFOLDER",
        required=True,
        type=Path,
        help="Path to folder containing input data files."
    )

    # Shared arguments for associate command
    p_associate_shared_args = argparse.ArgumentParser(add_help=False)
    p_associate_shared_args.add_argument(
        "-a", "--association_type",
        dest="ASSOCIATION_TYPE",
        choices=(
            "pearson", "spearman",
            "jaccard_similarity", "jaccard_distance", "jaccard_index",
            "mutual_information",
            "cosine_similarity", "cosine_distance",
            "autoencoder", "learn_correlation"
        ),
        default="pearson",
        help="Type of association metric to use. Default is 'pearson'."
    )
    p_associate_shared_args.add_argument(
        "-f", "--filter_cutoff",
        dest="FILTER_CUTOFF",
        type=check_cutoff_range,
        default=0.9,
        help="Cutoff for filtering low-confidence features. Default is 0.9."
    )
    p_associate_shared_args.add_argument(
        "-m", "--min_counts",
        dest="MIN_COUNTS",
        type=int,
        default=3,
        help="Minimum number of counts required. Default is 3."
    )
    p_associate_shared_args.add_argument(
        "-o", "--outfile",
        dest="OUTFILE",
        type=check_outfile,
        help="Path to output file."
    )
    p_associate_shared_args.add_argument(
        "-ot", "--output_type",
        dest="OUTPUT_TYPE",
        choices=("sorted_list", "correlation_matrix"),
        default="sorted_list",
        help="Output format. Default is 'sorted_list'."
    )
    p_associate_shared_args.add_argument(
        "-ft", "--file_type",
        dest="FILE_TYPE",
        choices=("csv", "tsv", "xlsx"),
        default="csv",
        help="Input file type. Default is 'csv'."
    )
    p_associate_shared_args.add_argument(
        "--overwrite",
        dest="OVERWRITE",
        action="store_true",
        help="Overwrite output file if it exists."
    )
    p_associate_shared_args.add_argument(
        "--clr",
        dest="TRANSFORM_CLR",
        action="store_true",
        help="Apply CLR transformation to the results."
    )
    p_associate_shared_args.add_argument(
        "--training-interactions",
        dest="TRAINING_INTERACTIONS",
        type=str,
        help="Path to file containing known interactions for training."
    )
    p_associate_shared_args.add_argument(
        "--calculate-confidence",
        dest="CALCULATE_CONFIDENCE",
        action="store_true",
        help="Calculate confidence scores for edges."
    )
    p_associate_shared_args.add_argument(
        "--annotation-file",
        dest="ANNOTATION_FILE",
        type=str,
        help="Path to annotation file."
    )
    p_associate_shared_args.add_argument(
        "--report-file",
        dest="REPORT_FILE",
        type=str,
        help="Path to save analysis report."
    )
    # NEW: Confidence model arguments
    p_associate_shared_args.add_argument(
        "--confidence-model",
        dest="CONFIDENCE_MODEL",
        type=str,
        default=None,
        help="Path to a pre-trained confidence model (.pkl) to use for "
             "confidence scoring instead of training a new one."
    )
    p_associate_shared_args.add_argument(
        "--save-confidence-model",
        dest="SAVE_CONFIDENCE_MODEL",
        type=str,
        default=None,
        help="Path to save the trained confidence model (.pkl) for reuse "
             "in future analyses."
    )
    p_associate_shared_args.add_argument(
        "--confidence-model-type",
        dest="CONFIDENCE_MODEL_TYPE",
        type=str,
        choices=("logistic", "random_forest"),
        default="logistic",
        help="Type of model to use for confidence prediction. "
             "Default is 'logistic'."
    )

    # =========================================================================
    # Associate command
    # =========================================================================

    p_associate = command_parsers.add_parser(
        "associate",
        description=textwrap.dedent("""
            The 'associate' command generates associations between data instances
            using various correlation and similarity metrics.
        """),
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    p_source = p_associate.add_subparsers(
        dest="SOURCE",
        title="source",
        required=True
    )

    p_associate_from_file = p_source.add_parser(
        "from_file",
        parents=[p_associate_shared_args, p_import_from_file],
    )

    p_associate_from_folder = p_source.add_parser(
        "from_folder",
        parents=[p_associate_shared_args, p_import_from_folder],
    )
    p_associate_from_folder.add_argument(
        "-n", "--normalization",
        dest="NORMALIZATION",
        choices=('pre', 'post', 'none'),
        default='none',
        help="Normalization strategy. Default is 'none'."
    )

    p_associate.set_defaults(func=associate)

    # =========================================================================
    # Prepare command
    # =========================================================================

    p_prepare = command_parsers.add_parser(
        "prepare",
        description=textwrap.dedent("""
            The 'prepare' command performs an optional preparation and
            validation step of the input data for the 'associate' routine.
        """)
    )

    p_source = p_prepare.add_subparsers(
        dest="SOURCE",
        title="source",
        required=True,
    )

    p_prepare_from_file = p_source.add_parser(
        "from_file",
        parents=[p_import_from_file],
    )

    p_prepare_from_folder = p_source.add_parser(
        "from_folder",
        parents=[p_import_from_folder],
    )

    p_prepare.set_defaults(func=prepare)

    # =========================================================================
    # Visualize command
    # =========================================================================

    p_visualize = command_parsers.add_parser(
        "visualize",
        description=textwrap.dedent("""
            The 'visualize' command creates visualizations of association data.
        """)
    )

    p_visualize.set_defaults(func=visualize)
    p_visualize.add_argument(
        "-i", "--infile",
        dest="INFILE",
        required=True,
        type=Path,
        help="Path to input datafile containing the association matrix."
    )
    p_visualize.add_argument(
        "-s", "--excel_sheet_name",
        dest="SHEET",
        type=str,
        help="Sheet name if input is an Excel file."
    )
    p_visualize.add_argument(
        "-t", "--visualization_type",
        dest="TYPE",
        choices=("heatmap", "graph"),
        default="heatmap",
        help="Type of visualization. Default is 'heatmap'."
    )
    p_visualize.add_argument(
        "-cl", "--color_bar_label",
        dest="LABEL",
        default="Association Strength",
        help="Label for the color bar in heatmap."
    )
    p_visualize.add_argument(
        "-o", "--outfile",
        dest="OUTFILE",
        type=str,
        help="Path to save the generated plot."
    )

    # =========================================================================
    # Parse and execute
    # =========================================================================

    args = main_parser.parse_args()

    if args.command is None:
        main_parser.print_help()
        sys.exit(1)

    # Call the appropriate function
    args.func(args)


def associate(args):
    """
    CLI handler for the 'associate' command.
    Delegates to valpas_core.associate() with mapped arguments.
    """

    # Determine input source
    if args.SOURCE == "from_file":
        infile = args.INFILE
        infile2 = getattr(args, 'INFILE2', None)
        infolder = None
        sheet = getattr(args, 'SHEET', None)
        sheet2 = getattr(args, 'SHEET2', None)
    elif args.SOURCE == "from_folder":
        infile = None
        infile2 = None
        infolder = args.INFOLDER
        sheet = None
        sheet2 = None
    else:
        print(f"Unknown source: {args.SOURCE}", file=sys.stderr)
        sys.exit(1)

    # Get normalization (only available for from_folder)
    normalization = getattr(args, 'NORMALIZATION', 'none') or 'none'

    # Determine output file handle
    if hasattr(args, 'OUTFILE') and args.OUTFILE is not None:
        outfile = args.OUTFILE
    else:
        outfile = sys.stdout

    # Call the core associate function
    try:
        core_associate(
            association_type=args.ASSOCIATION_TYPE,
            infile=infile,
            infile2=infile2,
            infolder=infolder,
            file_type=args.FILE_TYPE,
            sheet=sheet,
            sheet2=sheet2,
            output_type=args.OUTPUT_TYPE,
            filter_cutoff=args.FILTER_CUTOFF,
            normalization=normalization,
            min_counts=args.MIN_COUNTS,
            training_interactions=getattr(args, 'TRAINING_INTERACTIONS', None),
            calculate_confidence=getattr(args, 'CALCULATE_CONFIDENCE', False),
            transform_clr=getattr(args, 'TRANSFORM_CLR', False),
            annotation_file=getattr(args, 'ANNOTATION_FILE', None),
            overwrite_output=getattr(args, 'OVERWRITE', False),
            outfile=outfile,
            report_file=getattr(args, 'REPORT_FILE', None),
            # NEW: Confidence model parameters
            confidence_model_path=getattr(args, 'CONFIDENCE_MODEL', None),
            save_confidence_model=getattr(args, 'SAVE_CONFIDENCE_MODEL', None),
            confidence_model_type=getattr(args, 'CONFIDENCE_MODEL_TYPE', 'logistic'),
        )
    except Exception as e:
        print(f"Error during association: {e}", file=sys.stderr)
        sys.exit(1)


def prepare(args):
    """
    CLI handler for the 'prepare' command.
    Validates and prepares input data.
    """

    if args.SOURCE == "from_file":
        path = args.INFILE
        path2 = getattr(args, 'INFILE2', None)
        source = "from_file"
        sheet_names = [getattr(args, 'SHEET', None), getattr(args, 'SHEET2', None)]
    elif args.SOURCE == "from_folder":
        path = args.INFOLDER
        path2 = None
        source = "from_folder"
        sheet_names = [None, None]
    else:
        print(f"Unknown source: {args.SOURCE}", file=sys.stderr)
        sys.exit(1)

    try:
        experiments = import_experiments(
            path=path,
            file_type="csv",  # default, could be made configurable
            source=source,
            path2=path2,
            sheet_names=sheet_names,
        )

        validate_input(experiments)
        print("Validation complete. Input data is ready for association.")

    except Exception as e:
        print(f"Error during preparation: {e}", file=sys.stderr)
        sys.exit(1)


def visualize(args):
    """
    CLI handler for the 'visualize' command.
    Creates visualizations of association data.
    """

    try:
        # Import association matrix
        df = import_asssociation_matrix(
            path=args.INFILE,
            sheet_name=getattr(args, 'SHEET', None)
        )

        if args.TYPE == "heatmap":
            create_fig(
                df=df,
                fig_out=getattr(args, 'OUTFILE', None),
                cbarlabel=args.LABEL
            )
        elif args.TYPE == "graph":
            # Graph visualization would go here
            print("Graph visualization not yet fully implemented.", file=sys.stderr)
            sys.exit(1)
        else:
            print(f"Unknown visualization type: {args.TYPE}", file=sys.stderr)
            sys.exit(1)

    except Exception as e:
        print(f"Error during visualization: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
