"""
The main script that gets executed.
"""

import argparse
import os
import sys

from valpas.utils.calc_associations import calc_correlation
from valpas.utils.calc_associations import calc_mut_info
from valpas.utils.calc_associations import calc_cosine_sim
from valpas.utils.data_handling import write_outfile
from valpas.utils.data_handling import import_asssociation_matrix

from valpas.visualization.heatmap import create_fig

def main(args):

    argp = argparse.ArgumentParser()
    parsers = argp.add_subparsers(
        dest="command",
        title="commands",
        required=True,
    )

    p_associate = parsers.add_parser(
        "associate",
        help="",
    )
    p_associate.add_argument(
        "-a", "--association_type",
        dest="ASSOCIATION_TYPE",
        choices=(
            'spearman',
            'pearson',
            'mutual_information',
            'cosine_similarity',
            ),
        default='pearson'
    )
    p_associate.add_argument(
        "-i", "--infile",
        dest="INFILE",
        required=True,
        type=argparse.FileType('r'),
    )
    p_associate.add_argument(
        "-I", "--infile2",
        dest="INFILE2",
        type=argparse.FileType('r'),
        )
    p_associate.add_argument(
        "-o", "--outfile",
        dest="OUTFILE",
        type=argparse.FileType('w'),
        default=sys.stdout,
    )
    p_associate.add_argument(
        "-ot", "--output_type",
        dest="OUTPUT_TYPE",
        choices=(
            'sorted_list',
            'correlation_matrix',
        ),
        default='sorted_list',
    )
    p_associate.add_argument(
        "-or", "--reduced_output",
        dest="REDUCED_OUTPUT",
        action='store_true',
    )
    p_associate.add_argument(
        "-f", "--filter_missing_values",
        dest="FILTER_CUTOFF",
        type=cutoff_range
        )
    p_associate.set_defaults(func=associate)

    p_visualize = parsers.add_parser(
        "visualize",
        help=""
    )

    p_visualize.set_defaults(func=visualize)
    p_visualize.add_argument(
        "-i", "--infile",
        dest="INFILE",
        required=True,
        type=argparse.FileType('r'),
    )
    p_visualize.add_argument(
        "-t", "--visualization_type",
        dest="TYPE",
        choices=("heatmap", "graph"),
        default="heatmap",
    )
    p_visualize.add_argument(
        "-cl", "--color_bar_label",
        dest="LABEL",
        default="Association Strength",
    )
    p_visualize.add_argument(
        "-o", "--outfile",
        dest="OUTFILE",
        type=str,
    )

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
        mutual_information(args)
    elif args.ASSOCIATION_TYPE == 'cosine_similarity':
        cosine_similarity(args)
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
    df_corr = calc_correlation(
        fpath_1=args.INFILE,
        fpath_2=args.INFILE2,
        corr_func=args.ASSOCIATION_TYPE,
        filter_cutoff=args.FILTER_CUTOFF,
        )
    write_outfile(
        df=df_corr,
        file_handle=args.OUTFILE,
        output_type=args.OUTPUT_TYPE,
        reduced_output=args.REDUCED_OUTPUT,
        )

def mutual_information(args):
    df_mut_inf = calc_mut_info(
        fpath_1=args.INFILE,
        fpath_2=args.INFILE2,
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
        fpath_1=args.INFILE,
        fpath_2=args.INFILE2,
        filter_cutoff=args.FILTER_CUTOFF,
    )
    write_outfile(
        df=df_mut_inf,
        file_handle=args.OUTFILE,
        output_type=args.OUTPUT_TYPE,
        reduced_output=args.REDUCED_OUTPUT,
    )