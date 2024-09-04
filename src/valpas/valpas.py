"""
The main script that gets executed.
"""

import argparse
import os
import sys

from valpas.utils.calc_associations import calc_correlation

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
    p_associate.set_defaults(func=associate)

    args = argp.parse_args(args)
    args.func(args)


def associate(args):
    if args.ASSOCIATION_TYPE in ('pearson', 'spearman'):
        correlate(args)
    else:
        print(
            *("Association type", args.ASSOCIATION_TYPE,
              "not yet implemented"), 
            sep=" ",
            file=sys.stderr
            )


def correlate(args):
    df_cross_corr = calc_correlation(
        fpath_1=args.INFILE,
        fpath_2=args.INFILE2,
        corr_func=args.ASSOCIATION_TYPE
        )
    print(df_cross_corr, file=sys.stdout)