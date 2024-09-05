"""
The main script that gets executed.
"""

import argparse
import os
import sys

from valpas.utils.calc_associations import calc_correlation
from valpas.utils.calc_associations import calc_mut_info
from valpas.utils.data_handling import write_outfile

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
        "-f", "--filter_missing_values",
        dest="FILTER_CUTOFF",
        type=cutoff_range
        )
    p_associate.set_defaults(func=associate)

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
    else:
        print(
            *("Association type", args.ASSOCIATION_TYPE,
              "not yet implemented"), 
            sep=" ",
            file=sys.stderr
            )


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
    )