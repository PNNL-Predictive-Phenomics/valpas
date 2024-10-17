"""
The main script that gets executed.
"""

import argparse
import sys

import textwrap
import pandas as pd
import networkx as nx

from .utils.calc_associations import calc_association
from .utils.checker import check_infile
from .utils.checker import check_outfile
from .utils.checker import check_cutoff_range
from .utils.data_handling import write_outfile
from .utils.data_handling import import_asssociation_matrix
from .utils.post_processing import rm_duplicates
from .utils.post_processing import idx_name

from .visualization.heatmap import create_fig

def main(args):
    """
    The main method.
    """

    # Defining the argument parser. There are sereval (currently two)
    # subroutines (commands) that can be executed. For each of those a
    # seperate subparser is instanciated.
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

    # p_associate contains all arguments needed for the subroutine that
    # establishes association values between items (proteins, lipids,
    # metabolites, etc.). This can be either associations between items
    # of one omics datatype (e.g. protein-protein) or across two
    # different omics datatypes (e.g. protein-metabolite)
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
    # by default the function "associate" is executed with the arguments
    # that are passed to the tool on the command line (see also 
    # args.func(args) further down)
    p_associate.set_defaults(func=associate)
    p_associate.add_argument(
        "-a", "--association_type",
        dest="ASSOCIATION_TYPE",
        choices=(
            'spearman',
            'pearson',
            'mutual_information',
            'cosine_similarity',
            'cosine_distance',
            'jaccard_similarity',
            'jaccard_index',
            'jaccard_distance'
            ),
        default='pearson',
        help="Defines the type of metric used for generating associations. "
             "Defaults to 'pearson' if omitted."
    )
    p_associate.add_argument(
        "-i", "--infile",
        dest="INFILE",
        required=True,
        type=check_infile,
        help="Path to input file containing data points for which "
             "associations are to be generated. If used on it's own (without "
             "'-I') associations between data instances of only this input "
             "file will be generated."
    )
    p_associate.add_argument(
        "-I", "--infile2",
        dest="INFILE2",
        type=check_infile,
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
        type=check_outfile,
        default=sys.stdout,
        help="Path to an optional output file. If omitted, any output "
             "generated will be piped to stdout."
    )
    p_associate.add_argument(
        '-O', '--overwrite_output',
        dest='OVERWRITE_OUTPUT',
        action='store_true',
        help=''
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
        "-f", "--filter_missing_values",
        dest="FILTER_CUTOFF",
        type=check_cutoff_range,
        default=0.9,
        help="Can be set to a float between [0.0, 1.0]. If passed to the "
             "command a datapoint e.g. metabolite has to be detected (a value "
             "recorded larger than 0) in at least x of a fraction of the "
             "investigated conditions."
        )

    # the subparser definition for the visulatization component
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
    # definition of default function call
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

    # small check if a command / subparser has been passed to valpas.py
    # if not then the help will be printed (this is not standard
    # behaviour in argparse for what ever reason...) 
    if len(sys.argv) == 1:
        argp.print_help(sys.stderr)
        sys.exit(0)
    try:
        args = argp.parse_args(args)
    except FileNotFoundError as e:
        sys.exit(e)
    except ValueError as e:
        sys.exit(e)
    args.func(args)


def associate(args):

    try:
        ret_dict = calc_association(
            filepath_or_buffer=args.INFILE,
                filepath_or_buffer_2=args.INFILE2,
                sheet1=args.SHEET,
                sheet2=args.SHEET2,
                association=args.ASSOCIATION_TYPE,
                filter_cutoff=args.FILTER_CUTOFF,  
        )
    except ValueError:
        sys.exit(
            f"Association type {args.ASSOCIATION_TYPE} not yet implemented"
            )
    
    idx1 = ret_dict['idx1']
    idx2 = ret_dict['idx2']

    df_assoc = rm_duplicates(df=ret_dict['df_assoc'], idx1=idx1, idx2=idx2)
    df_counts = rm_duplicates(df=ret_dict['df_counts'], idx1=idx1, idx2=idx2)
    df_assoc = idx_name(df_assoc, idx1=idx1, idx2=idx2)
    df_counts = idx_name(df_counts, idx1=idx1, idx2=idx2)
    if idx2 is None:
        idx1_name = '_'.join((idx1.name, '1'))
        idx2_name = '_'.join((idx1.name, '2'))
    else:
        idx1_name = idx1.name
        idx2_name = idx2.name
    write_outfile(
        data=(df_assoc, df_counts),
        file_handle=args.OUTFILE,
        idx=(idx1_name, idx2_name),
        output_type=args.OUTPUT_TYPE,
        overwrite=args.OVERWRITE_OUTPUT,
        association_type=args.ASSOCIATION_TYPE
    )

def visualize(args):
    if args.TYPE == "heatmap":
        df = import_asssociation_matrix(file_handle=args.INFILE)
        fig = create_fig(df=df, fig_out=args.OUTFILE, cbarlabel=args.LABEL)
    else:
        print("Not yet implemented.", file=sys.stderr)


def df_to_graph(file_path, index_name, net, threshold):
    #read in data
    df = pd.read_csv(file_path)
    #set row names
    df = df.set_index(index_name)
    df.index.names = [None]
    #collect data for nodes, only grab edges over a given threshold
    for column in df:
        net.add_node(column, label=column)
        for row in df.index:
            net.add_node(row, label=row)
            value = df.loc[row, column]
            if abs(value) > threshold:
                net.add_edge(column, row, weight = value)
    return net

def assign_clusters(net):
    clusters = nx.community.louvain_communities(net, seed=123)
    for i in range(len(clusters)):
        for node in clusters[i]:
            net.nodes[node]['group'] = i
    return net

