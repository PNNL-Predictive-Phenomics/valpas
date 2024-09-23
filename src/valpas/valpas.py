"""
The main script that gets executed.
"""

import argparse
import os
import sys
import textwrap

from valpas.utils.calc_associations import calc_correlation
from valpas.utils.calc_associations import calc_mut_info
from valpas.utils.calc_associations import calc_cosine_sim
from valpas.utils.calc_associations import calc_jaccard_sim
from valpas.utils.data_handling import write_outfile
from valpas.utils.data_handling import import_asssociation_matrix
from valpas.utils.post_processing import rm_duplicates
from valpas.utils.post_processing import idx_name

from valpas.visualization.heatmap import create_fig

def main(args):

    argp = argparse.ArgumentParser(
        add_help=False,
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=textwrap.dedent(
            '''
            VaLPAS is a framework to establish and investigate functional 
            relations between proteins and other "omics-data". It currently 
            consits of the the two sub routines:
            
                - associate    (creates associations between data instances)
                - visualize    (helps to visualize generated associations)
            ''')
    )
    parsers = argp.add_subparsers(
        dest="command",
        title="commands",
        required=True,
    )

    p_associate = parsers.add_parser(
        "associate",
        description=
            '''
            The association subroutine enables the generation of association 
            scores between data points from either one or two omics data types.
            Omics data types can be for example proteomics, transcriptomics or 
            metabolomics. Typically each data type contains multiple values 
            (conditions) per data point (e.g. a metabolite). Multiple types of 
            association metrics are available to choose from (see below).
            '''
    )
    p_associate.add_argument(
        "-a", "--association_type",
        dest="ASSOCIATION_TYPE",
        choices=(
            'spearman',
            'pearson',
            'mutual_information',
            'cosine_similarity',
            'jaccard_similarity',
            ),
        default='pearson',
        help="Defines the type of metric used for generating associations. "
             "Defaults to 'pearson' if omitted."
    )
    p_associate.add_argument(
        "-i", "--infile",
        dest="INFILE",
        required=True,
        # type=argparse.FileType('r'),
        help="Path to input file containing data points for which "
             "associations are to be generated. If used on it's own (without "
             "'-I') associations between data instances of only this input "
             "file will be generated."
    )
    p_associate.add_argument(
        "-I", "--infile2",
        dest="INFILE2",
        # type=argparse.FileType('r'),
        help="Path to an optional second input file. If passed to command "
             "associations between data instances of INFILE1 and INFILE2 will "
             "be generated."
        )
    p_associate.add_argument(
        "-s", "--excel_sheet_name",
        dest="SHEET",
        type=str,
        help="Optional argument that defines the name of the sheet in INFILE "
             "if INFILE is an Excel file. If argument is present but imported "
             "file is not an Excel file this option will be ignored."
    )
    p_associate.add_argument(
        "-S", "--excel_sheet_name_2",
        dest="SHEET2",
        type=str,
        help="Optional argument that defines the name of the sheet in INFILE2 "
             "if INFILE2 is an Excel file. If argument is present but imported "
             "file is not an Excel file this option will be ignored."
    )
    p_associate.add_argument(
        "-o", "--outfile",
        dest="OUTFILE",
        type=argparse.FileType('w'),
        default=sys.stdout,
        help="Path to an optional output file. If omitted, any output "
             "generated will be piped to stdout."
    )
    p_associate.add_argument(
        "-ot", "--output_type",
        dest="OUTPUT_TYPE",
        choices=(
            'sorted_list',
            'correlation_matrix',
        ),
        default='sorted_list',
        help="Optional argument that defines the output format. Currently the "
             "choice is between: (1) A sorted association list returning the "
             "computed associations as comma separated file, sorted in "
             "descending order starting with the highest association. (2) A "
             "correlation matrix (comma separated)."
    )
    p_associate.add_argument(
        "-or", "--reduced_output",
        dest="REDUCED_OUTPUT",
        action='store_true',
        help="By default the full list of associations is returned if " 
             "'-ot sorted_list' is chosen. Adding this flag will reduce the "
             "output to not include self hits and only one of the two "
             "permutations of a data pair. Note that enabeling this flag if "
             "two input files are passed to the command will cause incomplete "
             "results to be returned!" 
    )
    p_associate.add_argument(
        "-f", "--filter_missing_values",
        dest="FILTER_CUTOFF",
        type=cutoff_range,
        default=0.9,
        help="Can be set to a float between [0.0, 1.0]. If passed to the "
             "command a datapoint e.g. metabolite has to be detected (a value "
             "recorded larger than 0) in at least x of a fraction of the "
             "investigated conditions."
        )
    p_associate.set_defaults(func=associate)

    p_visualize = parsers.add_parser(
        "visualize",
        description=
            """
            The 'visualize' command enables visualizing results generated by 
            the 'associate' command. This can be either plots like heatmaps or 
            (still to be implemented) network visualizations of the calculated 
            associations between datapoints. 
            """

    )

    p_visualize.set_defaults(func=visualize)
    p_visualize.add_argument(
        "-i", "--infile",
        dest="INFILE",
        required=True,
        type=argparse.FileType('r'),
        help="Path to a input datafile containing the association matix of "
             "datapoints."
    )
    p_visualize.add_argument(
        "-t", "--visualization_type",
        dest="TYPE",
        choices=("heatmap", "graph"),
        default="heatmap",
        help="Defines the type of visualization that is done. Currently only "
             "heatmap visualization is implemented. Will return a png of the "
             "generated plot if used in conjunction with '-o'."
    )
    p_visualize.add_argument(
        "-cl", "--color_bar_label",
        dest="LABEL",
        default="Association Strength",
        help="Defines the label of the color_bar when generating a heatmap."
    )
    p_visualize.add_argument(
        "-o", "--outfile",
        dest="OUTFILE",
        type=str,
        help="Optional argument defining the path to where the generated plot "
             "should be stored. Note that omitting this option only makes "
             "sense in the context of running valpas.py as backend to a "
             "jupyter notebook, where you might only want to display the "
             "generated plot but not necessarily store it."
    )
    if len(sys.argv) == 1:
        argp.print_help(sys.stderr)
        sys.exit(1)
    args = argp.parse_args(args)
    args.func(args)


def cutoff_range(x):
    try:
        x = float(x)
    except ValueError:
        raise argparse.ArgumentTypeError(f'{x} not a float')
    if x < 0.0 or x > 1.0:
        raise argparse.ArgumentTypeError(f'{x} not in range [0.0, 1.0]')
    return x


def associate(args):
    if args.ASSOCIATION_TYPE in ('pearson', 'spearman'):
        correlate(args)
    elif args.ASSOCIATION_TYPE == 'mutual_information':
        print("Calculation of mutual information is currently disabled",
              file=sys.stderr)
        #mutual_information(args)
    elif args.ASSOCIATION_TYPE == 'cosine_similarity':
        cosine_similarity(args)
    elif args.ASSOCIATION_TYPE == 'jaccard_similarity':
        jaccard_similarity(args)
    else:
        print(
            *("Association type", args.ASSOCIATION_TYPE,
              "not yet implemented"), 
            sep=" ",
            file=sys.stderr
            )

def visualize(args):
    if args.TYPE == "heatmap":
        df = import_asssociation_matrix(file_handle=args.INFILE)
        fig = create_fig(df=df, fig_out=args.OUTFILE, cbarlabel=args.LABEL)
    else:
        print("Not yet implemented.", file=sys.stderr)

def correlate(args):
    df_corr, idx1, idx2 = calc_correlation(
        filepath_or_buffer=args.INFILE,
        filepath_or_buffer_2=args.INFILE2,
        sheet1=args.SHEET,
        sheet2=args.SHEET2,
        corr_func=args.ASSOCIATION_TYPE,
        filter_cutoff=args.FILTER_CUTOFF,
        )
    if idx2 is not None and not args.REDUCED_OUTPUT:
        df_corr = rm_duplicates(df=df_corr, idx1=idx1, idx2=idx2)
    df_corr = idx_name(df_corr, idx1=idx1, idx2=idx2)

    write_outfile(
        df=df_corr,
        file_handle=args.OUTFILE,
        output_type=args.OUTPUT_TYPE,
        reduced_output=args.REDUCED_OUTPUT,
        )

def mutual_information(args):
    df_mut_inf = calc_mut_info(
        filepath_or_buffer=args.INFILE,
        filepath_or_buffer_2=args.INFILE2,
        filter_cutoff=args.FILTER_CUTOFF,
    )
    write_outfile(
        df=df_mut_inf,
        file_handle=args.OUTFILE,
        output_type=args.OUTPUT_TYPE,
        reduced_output=args.REDUCED_OUTPUT,
    )

def cosine_similarity(args):
    df_mut_inf = calc_cosine_sim(
        filepath_or_buffer=args.INFILE,
        filepath_or_buffer_2=args.INFILE2,
        filter_cutoff=args.FILTER_CUTOFF,
    )
    write_outfile(
        df=df_mut_inf,
        file_handle=args.OUTFILE,
        output_type=args.OUTPUT_TYPE,
        reduced_output=args.REDUCED_OUTPUT,
    )

def jaccard_similarity(args):
    df_jaccard_sim = calc_jaccard_sim(
        filepath_or_buffer=args.INFILE,
        filepath_or_buffer_2=args.INFILE2,
        filter_cutoff=args.FILTER_CUTOFF,
    )
    write_outfile(
        df=df_jaccard_sim,
        file_handle=args.OUTFILE,
        output_type=args.OUTPUT_TYPE,
        reduced_output=args.REDUCED_OUTPUT,
    )
