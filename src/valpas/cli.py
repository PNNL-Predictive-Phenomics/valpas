"""
The main script that gets executed.
"""

import argparse
import sys

import textwrap

from pathlib import Path

from valpas.utils.checker import check_infile
from valpas.utils.checker import check_outfile
from valpas.utils.checker import check_cutoff_range


def main():
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
        "--comparison-export", metavar="REQUEST_JSON",
        help="Opt-in comparison input sidecar request; explicit identity, axes and new destination."
    )
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
            'jaccard_distance',
            'autoencoder',
            'learn_correlation'
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
        "-ti", "--training_interactions",
        dest='training_interactions',
        help="Optional argument to specify a set of training interactions "
             "to be used for learning correlation weights and/or confidence "
             "calculation. The format is [id1]\t[id2], where the ids are "
             "valid protein/gene identifiers used in the input data matrices."
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
             "association matrix (comma separated)."
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

    p_import_shared_args = argparse.ArgumentParser(add_help=False)

    g_file_type = p_import_shared_args.add_mutually_exclusive_group()
    g_file_type.add_argument('--csv', action='store_true')
    g_file_type.add_argument('--xlsx', action='store_true')

    p_import_shared_args.add_argument(
        "-s", "--excel_sheet_name",
        dest="SHEET",
        type=str,
        help="Optional argument that defines the name of the sheet in INFILE "
             "if INFILE is an Excel file. If argument is present but imported "
             "file is not an Excel file this option will be ignored."
    )
    p_import_shared_args.add_argument(
        "-S", "--excel_sheet_name_2",
        dest="SHEET2",
        type=str,
        help="Optional argument that defines the name of the sheet in INFILE2 "
             "if INFILE2 is an Excel file. If argument is present but imported "
             "file is not an Excel file this option will be ignored."
    )

    p_import_from_file = argparse.ArgumentParser(
        add_help=False,
        parents=[p_import_shared_args],
        )
    p_import_from_file.add_argument(
        "-i", "--infile",
        dest="INFILE",
        required=True,
        type=check_infile,
        help="Path to input file containing data points for which "
             "associations are to be generated. If used on it's own (without "
             "'-I') associations between data instances of only this input "
             "file will be generated."
    )
    p_import_from_file.add_argument(
        "-I", "--infile2",
        dest="INFILE2",
        type=check_infile,
        help="Path to an optional second input file. If passed to command "
             "associations between data instances of INFILE1 and INFILE2 will "
             "be generated."
        )

    p_import_from_folder = argparse.ArgumentParser(
        add_help=False,
        parents=[p_import_shared_args],
        )
    p_import_from_folder.add_argument(
        "-i", "--infolder",
        dest="INFOLDER",
        required=True
    )
    p_import_from_folder.add_argument(
        '-t',
        '--two_omics_types',
        dest="TWO_OMICS_TYPES",
        action='store_true',
    )


    # Instatiting the subparsers of 'associate'. They are used to define
    # the source of the data files. Either from up to two directly
    # defined files, or
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
    )


    p_prepare = command_parsers.add_parser(
        "prepare",
        description=
            """
            The 'prepare' command performs an optional perparation and
            validation step of the input data for the 'associate' routine.
            """
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

    p_compare = command_parsers.add_parser(
        "compare", description="Compare saved outputs: offline HTML and complete tables, no training.")
    source = p_compare.add_mutually_exclusive_group(required=True)
    source.add_argument("--manifest", type=Path)
    source.add_argument("--bundle", type=Path, help="Regenerate from a completed comparison bundle without original inputs.")
    p_compare.add_argument("--outdir", required=True, type=Path)
    p_compare.add_argument("--pool", choices=("strict", "common", "native_inspection"),
                           help="Override the manifest pool policy.")
    p_compare.add_argument("--depths", nargs="+", type=int,
                           help="Override requested positive integer summary depths.")
    p_compare.add_argument("--tables-only", action="store_true",
                           help="Export complete tables without the HTML report.")
    p_compare.add_argument("--report-query", action="append", help="Canonical query ID to embed; repeat for a subset.")
    p_compare.add_argument("--pin-candidate", action="append", help="Canonical candidate ID to embed beyond top unions; repeatable.")
    p_compare.add_argument("--max-interactive-depth", type=int)
    p_compare.add_argument("--max-payload-bytes", type=int)
    p_compare.add_argument("--omit-metadata", action="store_true", default=None,
                           help="Omit optional metadata/profiles from HTML only; full bundle remains sensitive.")
    p_compare.add_argument("--overwrite", action="store_true",
                           help="Replace only an intact owned comparison bundle containing no consumed inputs.")
    p_compare.set_defaults(func=compare)

    p_figure = command_parsers.add_parser(
        "export-query", description="Export a descriptive SVG/PDF from a saved bundle, without original inputs or training.")
    p_figure.add_argument("--bundle", required=True, type=Path)
    p_figure.add_argument("--query", required=True, help="Exact canonical query ID.")
    p_figure.add_argument("--candidate", required=True, help="Exact canonical candidate ID.")
    p_figure.add_argument("--layer", required=True, help="Exact measurement layer ID.")
    p_figure.add_argument("--output", required=True, type=Path, help="New .svg or .pdf outside the bundle; never overwritten.")
    p_figure.add_argument("--color", help="Exact metadata field for coloring.")
    p_figure.add_argument("--group", help="Exact categorical metadata field for marginal summaries.")
    p_figure.add_argument("--order", choices=("dataset", "id", "metadata"))
    p_figure.add_argument("--h", type=int)
    p_figure.add_argument("--omission", action="store_true", default=None)
    p_figure.add_argument("--no-fraction", action="store_false", dest="include_fraction", default=None)
    p_figure.add_argument("--depth", type=int, help="Inspection context only; never changes scientific pools.")
    p_figure.add_argument("--notes", help="Literal user notes included in the caption.")
    p_figure.add_argument("--session", type=Path, help="Optional strictly bound saved session.")
    p_figure.add_argument("--decision-id", help="Use an exact decision view from that session.")
    p_figure.set_defaults(func=export_query)

    # small check if a command / subparser has been passed to valpas.py
    # if not then the help will be printed (this is not standard
    # behaviour in argparse for what ever reason...)
    if len(sys.argv) == 1:
        main_parser.print_help(sys.stderr)
        sys.exit(0)
    try:
        args = main_parser.parse_args()
    except FileNotFoundError as e:
        sys.exit(e)
    except ValueError as e:
        sys.exit(e)
    args.func(args)

def export_query(args):
    """Delegate saved-bundle figure export to the public API."""
    from valpas.comparison import export_query_figure
    try:
        destination = export_query_figure(
            args.bundle, query_id=args.query, candidate_id=args.candidate,
            layer_id=args.layer, output=args.output, color=args.color, group=args.group,
            order=args.order, h=args.h, omission=args.omission,
            include_fraction=args.include_fraction, depth=args.depth, notes=args.notes,
            session=args.session, decision_id=args.decision_id)
        print(f"Descriptive figure: {destination}; no scores or ranks changed.")
    except (ValueError, OSError) as exc:
        print("export-query: " + str(exc), file=sys.stderr)
        raise SystemExit(2) from None


def compare(args):
    """Manifest CLI delegates all science and persistence to the public API."""
    from valpas.comparison import (ComparisonSettings, ReportSettings, load_manifest, compare_results,
                                   write_comparison, load_comparison_bundle)
    try:
        if args.bundle:
            if args.pool is not None or args.depths is not None:
                raise ValueError("--bundle preserves analysis settings; use report options for re-export")
            result = load_comparison_bundle(args.bundle)
        else:
            manifest = load_manifest(args.manifest)
            resolved = manifest.settings.to_dict()
            if args.pool is not None:
                resolved["pool_policy"] = args.pool
            if args.depths is not None:
                resolved["depths"] = args.depths
            result = compare_results(manifest, ComparisonSettings.from_dict(resolved))
        report = (result.report_settings or ReportSettings()).to_dict()
        for arg, key in (("report_query", "query_ids"), ("pin_candidate", "pinned_candidate_ids"),
                         ("max_interactive_depth", "max_interactive_depth"),
                         ("max_payload_bytes", "max_payload_bytes"), ("omit_metadata", "omit_metadata")):
            value = getattr(args, arg)
            if value is not None:
                report[key] = value
        destination = write_comparison(result, args.outdir, tables_only=args.tables_only,
                                       overwrite=args.overwrite, report_settings=ReportSettings.from_dict(report))
        summary = result.materialize_table("dataset_summary")[0]
        print(f"Comparison {result.comparison_id}: {summary['methods']} methods, "
              f"{summary['configurations']} configurations, {summary['outputs']} outputs; "
              f"{summary['included_queries']}/{summary['declared_queries']} queries; pool={summary['pool_policy']}.")
        evaluable, excluded = 0, 0
        for row in result.iter_table("agreement_summary"):
            evaluable += row["evaluable_queries"]
            excluded += row["excluded_queries"]
        print(f"Controlled evaluable query/pair/depth records: {evaluable}; "
              f"excluded from controlled summaries: {excluded}.")
        for reason in sorted({w.reason for w in result.warnings}):
            print("Warning: " + reason, file=sys.stderr)
        print(f"Tables-only bundle: {destination} (no HTML report)." if args.tables_only else
              f"Offline report: {destination / 'report.html'} (open directly from disk); complete tables alongside.")
    except (ValueError, OSError) as exc:
        print("compare: " + str(exc), file=sys.stderr)
        raise SystemExit(2) from None


# TODO: make this call the valpas_core function for associate to keep things
#       neat and tidy. Currently the CLI and API have different behavior.
def associate(args):
    from valpas import CrossExperiment
    from valpas.io import import_experiments
    from valpas._core.processing import combine_results

    comparison_request = getattr(args, "comparison_export", None)
    if comparison_request is not None:
        from valpas.comparison.production import load_export_request, validate_legacy_destination
        comparison_request = load_export_request(comparison_request)
        validate_legacy_destination(comparison_request, args.OUTFILE)
    # The legacy CLI omits required subset keys. Supply explicit no-subset
    # settings only for this opt-in path; preserve existing default behavior.
    comparison_kwargs = ({"subset_args": {"nconds": None, "percentage": None, "keep_conds": []}}
                         if comparison_request is not None else {})

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
        inpath2 = None
        files = []
        for child in inpath.glob(f'*.{file_type}'):
            files.append(child)
        if args.csv and len(files) > 4:
            raise ValueError(
                "Import of more than four CSV files currently not supported."
            )
        if args.xlsx and len(files) > 2:
            raise ValueError(
                "Import of more than two XLSX file currently not supported."
            )
    else:
        inpath = args.INFILE
        inpath2 = args.INFILE2

    experiments = import_experiments(
        path=inpath,
        file_type=file_type,
        source=args.SOURCE,
        path2=inpath2,
        sheet_names=sheet_names
    )

    if args.ASSOCIATION_TYPE in [
            'jaccard_similarity',
            'jaccard_index',
            'jaccard_distance'
            ]:
        threshold = 0.5
        thresholded = True
    else:
        threshold = None
        thresholded = False

    experiment_count = len(experiments)
    if len(experiments) == 1:
        experiment = experiments.pop()

        experiment.pre_process(
            rm_low_conf_features=args.FILTER_CUTOFF,
            threshold=threshold,
            inplace=True
        )
        try:
            result = experiment.associate(
                metric=args.ASSOCIATION_TYPE,
                thresholded=thresholded,
                **comparison_kwargs
            )
        except ValueError:
            sys.exit(
                f"Association type {args.ASSOCIATION_TYPE} not yet implemented"
            )

    elif len(experiments) == 2:
        for experiment in experiments:
            if args.NORMALIZATION == 'pre':
                normalize_ = True
            else:
                normalize_ = False
            experiment.pre_process(
                rm_low_conf_features=args.FILTER_CUTOFF,
                normalize=normalize_,
                threshold=threshold,
                inplace=True
            )
        if args.NORMALIZATION in ['pre', 'none']:
            cross_experiment = CrossExperiment(
                name='cross_experiment',
                experiments=experiments,
            )
            cross_experiment.combine(inplace=True)

            try:
                result = cross_experiment.associate(
                    metric=args.ASSOCIATION_TYPE,
                    thresholded=thresholded,
                    **comparison_kwargs
                )
            except ValueError:
                sys.exit(
                    f"Association type {args.ASSOCIATION_TYPE} not yet implemented"
                )

        elif args.NORMALIZATION == 'post':
            results = []
            for experiment in experiments:
                try:
                    result = experiment.associate(
                        metric=args.ASSOCIATION_TYPE,
                        thresholded=thresholded,
                        **comparison_kwargs
                    )
                except ValueError:
                    sys.exit(
                        f"Association type {args.ASSOCIATION_TYPE} not yet implemented"
                    )
                results.append(result)
            result = combine_results(
                results=results,
                normalization_metric='mean'
            )


    else:
        raise NotImplementedError(
            "Cross Experiment assocations for more than 2 experiments is"
            "currently not supported."
            )

    if comparison_request is not None:
        from valpas.comparison.production import export_requested_result
        # Post-normalization combines separate results; do not invent a cohort.
        cohort = None
        if experiment_count == 1 or args.NORMALIZATION != "post":
            actual = cross_experiment if 'cross_experiment' in locals() else experiment
            cohort = list(actual.measurements.index)
        export_requested_result(result, comparison_request, observation_ids=cohort,
                                method=args.ASSOCIATION_TYPE, transform_clr=False,
                                thresholded=thresholded,
                                preprocessing={"valpas_cli": {
                                    "zero_to_missing": True,
                                    "filter_cutoff": args.FILTER_CUTOFF,
                                    "threshold": threshold,
                                    "normalize_inputs": experiment_count == 2 and args.NORMALIZATION == "pre",
                                    "combine_result_mean": experiment_count == 2 and args.NORMALIZATION == "post",
                                }})

    result.save(
        file_handle=args.OUTFILE,
        type=args.OUTPUT_TYPE,
        overwrite=args.OVERWRITE_OUTPUT,
        assocation_metric=args.ASSOCIATION_TYPE
    )

def prepare(args):
    from valpas.io import import_experiments
    from valpas.utils.validator import validate_input

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
        inpath2 = None
        files = []
        for child in inpath.glob(f'*.{file_type}'):
            files.append(child)
        if args.csv and len(files) > 4:
            raise ValueError(
                "Import of more than four CSV files currently not supported."
            )
        if args.xlsx and len(files) > 2:
            raise ValueError(
                "Import of more than two XLSX file currently not supported."
            )
    else:
        inpath = args.INFILE
        inpath2 = args.INFILE2

    experiments = import_experiments(
        path=inpath,
        file_type=file_type,
        source=args.SOURCE,
        path2=inpath2,
        sheet_names=sheet_names
    )

    validate_input(experiments)
    pass


def visualize(args):
    if args.TYPE == "heatmap":
        from valpas.io import import_asssociation_matrix
        from valpas.visualization.heatmap import create_fig

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
    import pandas as pd

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
            value = float(df.loc[row, column].split(':')[0])
            if abs(value) > threshold:
                net.add_edge(column, row, weight = value)
    return net

def assign_clusters(net):
    import networkx as nx

    clusters = nx.community.louvain_communities(net, seed=123)
    for i in range(len(clusters)):
        for node in clusters[i]:
            net.nodes[node]['group'] = i
    return net


if __name__ == '__main__':
    import sys
    try:
        main()
    except KeyboardInterrupt:
        pass
