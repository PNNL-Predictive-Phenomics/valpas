"""
The main script that gets executed.
"""

import argparse
import sys

import textwrap
import pandas as pd
import networkx as nx

from pathlib import Path

from ._core.association import calc_association
from .utils.checker import check_infile
from .utils.checker import check_outfile
from .utils.checker import check_cutoff_range
from .io import write_outfile
from .io import import_asssociation_matrix
from .io import import_from_folder
from .io import import_from_files
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
    main_parser = argparse.ArgumentParser(
        add_help=True,
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
    command_parsers = main_parser.add_subparsers(
        dest="command",
        title="commands",
        required=True,
    )

    # p_associate contains all arguments needed for the subroutine that
    # establishes association values between items (proteins, lipids,
    # metabolites, etc.). This can be either associations between items
    # of one omics datatype (e.g. protein-protein) or across two
    # different omics datatypes (e.g. protein-metabolite)
    p_associate = command_parsers.add_parser(
        "associate",
        description=
            '''
            The association subroutine enables the generation of association 
            scores between data points from either one or two omics data types.
            Omics data types can be for example proteomics, transcriptomics or 
            metabolomics. Typically each data type contains multiple values 
            (conditions) per data point (e.g. a metabolite). Multiple types of 
            association metrics are available to choose from (see below).
            ''',
        add_help=True
    )
    # by default the function "associate" is executed with the arguments
    # that are passed to the tool on the command line (see also 
    # args.func(args) further down)
    p_associate.set_defaults(func=associate)
    
    # The associate command contains additional subroutines (defined
    # further down) that share certain command line arguments. To cover
    # these a new ArgumentParser is defined that will serve as parent
    # to the subparsers of 'associate'
    p_associate_shared_args = argparse.ArgumentParser(add_help=False)
    p_associate_shared_args.add_argument(
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
    p_associate_shared_args.add_argument(
        "-o", "--outfile",
        dest="OUTFILE",
        type=check_outfile,
        default=sys.stdout,
        help="Path to an optional output file. If omitted, any output "
             "generated will be piped to stdout."
    )
    p_associate_shared_args.add_argument(
        '-O', '--overwrite_output',
        dest='OVERWRITE_OUTPUT',
        action='store_true',
        help=''
    )
    p_associate_shared_args.add_argument(
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
    p_associate_shared_args.add_argument(
        "-f", "--filter_missing_values",
        dest="FILTER_CUTOFF",
        type=check_cutoff_range,
        default=0.9,
        help="Can be set to a float between [0.0, 1.0]. If passed to the "
             "command a datapoint e.g. metabolite has to be detected (a value "
             "recorded larger than 0) in at least x of a fraction of the "
             "investigated conditions."
        )
    g_file_type = p_associate_shared_args.add_mutually_exclusive_group()
    g_file_type.add_argument('--csv', action='store_true')
    g_file_type.add_argument('--xlsx', action='store_true')
    
 
    p_from_file = argparse.ArgumentParser(add_help=False)
    p_from_file.add_argument(
        "-i", "--infile",
        dest="INFILE",
        required=True,
        type=check_infile,
        help="Path to input file containing data points for which "
             "associations are to be generated. If used on it's own (without "
             "'-I') associations between data instances of only this input "
             "file will be generated."
    )
    p_from_file.add_argument(
        "-I", "--infile2",
        dest="INFILE2",
        type=check_infile,
        help="Path to an optional second input file. If passed to command "
             "associations between data instances of INFILE1 and INFILE2 will "
             "be generated."
        )
    p_from_file.add_argument(
        "-s", "--excel_sheet_name",
        dest="SHEET",
        type=str,
        help="Optional argument that defines the name of the sheet in INFILE "
             "if INFILE is an Excel file. If argument is present but imported "
             "file is not an Excel file this option will be ignored."
    )
    p_from_file.add_argument(
        "-S", "--excel_sheet_name_2",
        dest="SHEET2",
        type=str,
        help="Optional argument that defines the name of the sheet in INFILE2 "
             "if INFILE2 is an Excel file. If argument is present but imported "
             "file is not an Excel file this option will be ignored."
    )

    p_from_folder = argparse.ArgumentParser(add_help=False)
    p_from_folder.add_argument(
        "-i", "--infolder",
        dest="INFOLDER",
        required=True
    )


    # Instatiting the subparsers of 'associate'. They are used to define
    # the source of the data files. Either from up to two directly 
    # defined files, or 
    p_source = p_associate.add_subparsers(
        dest="SOURCE",
        title="source",
        required=True
    )
    p_source_from_file = p_source.add_parser(
        "from_file",
        parents=[p_associate_shared_args, p_from_file],
    )
    p_source_from_folder = p_source.add_parser(
        "from_folder",
        parents=[p_associate_shared_args, p_from_folder],
    )
    p_source_from_folder.add_argument(
        '-t',
        '--two_omics_types',
        dest="TWO_OMICS_TYPES",
        action='store_true',
        )
    p_source_from_folder.add_argument(
        "-s", "--excel_sheet_name",
        dest="SHEET",
        type=str,
        help="Optional argument that defines the name of the sheet in INFILE "
             "if INFILE is an Excel file. If argument is present but imported "
             "file is not an Excel file this option will be ignored."
    )
    p_source_from_folder.add_argument(
        "-S", "--excel_sheet_name_2",
        dest="SHEET2",
        type=str,
        help="Optional argument that defines the name of the sheet in INFILE2 "
             "if INFILE2 is an Excel file. If argument is present but imported "
             "file is not an Excel file this option will be ignored."
    )

    # the subparser definition for the visulatization component
    p_visualize = command_parsers.add_parser(
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
        type=Path,
        help="Path to a input datafile containing the association matix of "
             "datapoints."
    )
    p_visualize.add_argument(
        "-s", "--excel_sheet_name",
        dest="SHEET",
        type=str,
        help="Optional argument that defines the name of the sheet in INFILE "
             "if INFILE is an Excel file. If argument is present but imported "
             "file is not an Excel file this option will be ignored."
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
        main_parser.print_help(sys.stderr)
        sys.exit(0)
    try:
        args = main_parser.parse_args(args)
    except FileNotFoundError as e:
        sys.exit(e)
    except ValueError as e:
        sys.exit(e)
    args.func(args)


def associate(args):

    if args.csv:
        file_type = 'csv'
    elif args.xlsx:
        file_type = 'xlsx'

    sheet_names = None
    if args.SHEET is not None:
        sheet_names = [args.SHEET]
    if args.SHEET2 is not None:
        if sheet_names is not None:
            sheet_names.append(args.SHEET2)
        else:
            sheet_names = [args.SHEET2]

    if args.SOURCE == 'from_folder':
        inpath = Path(args.INFOLDER).absolute()
        files = []
        for child in inpath.glob(f'*.{file_type}'):
            files.append(child)
        if args.csv and len(files) > 2:
            raise ValueError(
                "Import of more than two CSV files currently not supported."
            )
        if args.xlsx and len(files) != 1:
            raise ValueError(
                "Import of more than one XLSX file currently not supported."
            )
        experiments = import_from_folder(
            path=inpath,
            file_type=file_type,
            sheet_names=sheet_names
            )
    else:
        experiments = import_from_files(
            filepath=args.INFILE,
            file_type=file_type,
            filepath_2=args.INFILE2,
            sheet_names=sheet_names
        )
    try:
        ret_dict = calc_association(
            experiment=experiments.pop(),
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
        if args.SHEET is None:
            sheet = 0
        else:
            sheet = args.SHEET
        try:
            df = import_asssociation_matrix(filepath=args.INFILE, sheet=sheet)
        except ValueError:
            sys.exit(f"sheet '{sheet}' not found in file '{args.INFILE}'")
        except FileNotFoundError:
            sys.exit(f"file '{args.INFILE}' not found.")
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

