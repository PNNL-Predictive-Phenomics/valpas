"""
Module containing functions for the calculation of associations used by
ValPAS.
"""

from copy import deepcopy
from io import TextIOBase
from os import PathLike
from pathlib import Path
from typing import Literal, Dict, List, Optional, Union, Tuple

import numpy as np
import pandas as pd

import base64
from io import BytesIO
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
import json
import warnings
warnings.filterwarnings('ignore')

from .omics import Omic
from .analysisresults import AnalysisResults
from .annotations import AnnotationList

class AssociationResult():
    def __init__(
            self,
            values: pd.DataFrame,
            counts: pd.DataFrame,
            omic_x: Omic,
            omic_y: Omic,
            analysis_results: AnalysisResults = None,
            annotationlist: AnnotationList = None,
            edgelist: pd.DataFrame = None
            ) -> None:

        self.values = values
        self.counts = counts
        self.omic_x = omic_x
        self.omic_y = omic_y
        self.analysis_results = analysis_results
        self.annotationlist = annotationlist
        self.edgelist = edgelist

    # ---------------------------
    # getters, setters & deleters
    # ---------------------------

    # values
    @property
    def values(self):
        return self._values

    @values.setter
    def values(self, value):
        self._values = value

    @values.deleter
    def values(self):
        del self._values

    # counts
    @property
    def counts(self):
        return self._counts

    @counts.setter
    def counts(self, value):
        self._counts = value

    @counts.deleter
    def counts(self):
        del self._counts

    # omic_x
    @property
    def omic_x(self):
        return self._omic_x

    @omic_x.setter
    def omic_x(self, value):
        self._omic_x = value

    @omic_x.deleter
    def omic_x(self):
        del self._omic_x

    # omic_y
    @property
    def omic_y(self):
        return self._omic_y

    @omic_y.setter
    def omic_y(self, value):
        self._omic_y = value

    @omic_y.deleter
    def omic_y(self):
        del self._omic_y

    def as_list(self, association_type='correlation'):
        from ...io import result_to_list

        if self.omic_y is None:
            self.omic_y = deepcopy(self.omic_x)
            self.omic_x.type = "_".join([self.omic_x.type, "1"])
            self.omic_y.type = "_".join([self.omic_y.type, "2"])

        self.values.index.name = self.omic_x.type
        self.values.columns.name = self.omic_y.type

        self.counts.index.name = self.omic_x.type
        self.counts.columns.name = self.omic_y.type

        edgelist = result_to_list([self.values, self.counts],
                              idx=(self.omic_x.type, self.omic_y.type),
                              association_type=association_type)

        if not self.annotationlist == None:
            edgelist = self.merge_edge_annotations(edgelist)

        return edgelist

    def save(
            self,
            file_handle: str | PathLike | Path | TextIOBase,
            type: Literal['sorted_list', 'assocation_matrix']='sorted_list',
            overwrite: bool=False,
            **kwargs
            ) -> None:
        from ...io import write_outfile

        assocation_metric = kwargs.get('association_metric', 'association')

        if self.omic_y is None:
            self.omic_y = deepcopy(self.omic_x)
            self.omic_x.type = "_".join([self.omic_x.type, "1"])
            self.omic_y.type = "_".join([self.omic_y.type, "2"])

        self.values = _rm_duplicates(
            df=self.values,
            idx1=self.omic_x.features,
            idx2=self.omic_y.features,
        )

        self.counts = _rm_duplicates(
            df=self.counts,
            idx1=self.omic_x.features,
            idx2=self.omic_y.features,
        )

        self.values.index.name = self.omic_x.type
        self.values.columns.name = self.omic_y.type

        self.counts.index.name = self.omic_x.type
        self.counts.columns.name = self.omic_y.type

        write_outfile(
            data=(self.values, self.counts),
            file_handle=file_handle,
            idx=(self.omic_x.type, self.omic_y.type),
            output_type=type,
            overwrite=overwrite,
            association_type=assocation_metric
        )

    # function to add annotations to the edgelist
    # FIXME: currently won't handle multiple omics types gracefully
    #        (requires merged annotations)
    def merge_edge_annotations(self, edgelist):
        edgelist = pd.merge(
            left=edgelist,
            right=self.annotationlist.annotations,
            left_on=self.omic_x.type,
            right_on=self.annotationlist.primary_id_column,
            how='left',
            validate="m:1",
            )

        edgelist = pd.merge(
            left=edgelist,
            right=self.annotationlist.annotations,
            left_on=self.omic_y.type,
            right_on=self.annotationlist.primary_id_column,
            how='left',
            validate='m:1'
        )
        return edgelist

    def generate_report(self,
        weight_col: str = 'weight',
        confidence_col: str = 'confidence',
        count_col: str = 'counts',
        top_n: int = 50,
        output_format: str = 'html',
        output_file: str = None,
        title: str = "Association Analysis Report",
        include_statistics: bool = False,
        include_plots: bool = True,
        percentile_analysis: List[int] = [10, 20, 30, 40],
        annotation_filter_categories: List[str] = None,
        sort_by: str = None,
        ascending: bool = False,
        interactive_html: bool = True,
        include_analysis_report: bool = True,
        plot_format: str = 'png',
        custom_css: str = None
    ) -> Union[str, Tuple[str, Dict]]:
        """
        Generate an interactive report for protein interaction data

        Args:
            weight_col: Column name for interaction weight/score
            confidence_col: Column name for confidence score
            count_col: Column name for the counts
            top_n: Number of top results to display
            output_format: 'html' or 'text'
            output_file: Path to save output file (optional)
            title: Report title
            include_statistics: Whether to include statistical analysis
            include_plots: Whether to include plots (HTML only)
            percentile_analysis: List of percentiles to analyze
            annotation_filter_categories: Specific annotation categories to highlight
            sort_by: Column to sort by (default: weight_col)
            ascending: Sort order
            interactive_html: Whether to include interactive elements (HTML only)
            include_analysis_report: Whether to include a detailed output of analysis.
            plot_format: Format for embedded plots ('png', 'svg')
            custom_css: Custom CSS styles for HTML report

        Returns:
            String report (text) or tuple of (html_string, analysis_dict)
        """
        if self.edgelist is None:
            df = self.as_list()
        else:
            df = self.edgelist

        protein1_col = self.omic_x.type
        protein2_col = self.omic_y.type
        annotation1_col = f'{self.annotationlist.primary_annotation_column}_x'
        annotation2_col = f'{self.annotationlist.primary_annotation_column}_y'

        # Validate inputs
        self._validate_inputs(df, protein1_col, protein2_col, weight_col,
                            annotation1_col, annotation2_col, confidence_col)

        # Prepare data
        analysis_data = self._prepare_analysis_data(
            df, protein1_col, protein2_col, weight_col,
            annotation1_col, annotation2_col, confidence_col, count_col,
            top_n, sort_by, ascending, annotation_filter_categories
        )

        # Generate statistics
        if include_statistics:
            stats = self._calculate_statistics(analysis_data, percentile_analysis)
            analysis_data['statistics'] = stats

        # Generate report
        if output_format.lower() == 'html':
            report = self._generate_html_report(
                analysis_data, title, include_plots, interactive_html,
                plot_format, custom_css, include_analysis_report
            )
        else:
            report = self._generate_text_report(analysis_data, title,
                                            include_analysis_report)

        # Save to file if specified
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"Report saved to: {output_file}")

        if output_format.lower() == 'html':
            return report, analysis_data
        else:
            return report

    def _validate_inputs(self, df: pd.DataFrame, protein1_col: str, protein2_col: str,
                        weight_col: str, annotation1_col: str, annotation2_col: str,
                        confidence_col: str):
        """Validate input parameters"""

        required_cols = [protein1_col, protein2_col, weight_col]
        missing_cols = [col for col in required_cols if col not in df.columns]

        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")

        optional_cols = [col for col in [annotation1_col, annotation2_col, confidence_col]
                        if col is not None]
        missing_optional = [col for col in optional_cols if col not in df.columns]

        if missing_optional:
            raise ValueError(f"Specified columns not found: {missing_optional}")

        if df.empty:
            raise ValueError("Input DataFrame is empty")

        # Check for numeric columns
        if not pd.api.types.is_numeric_dtype(df[weight_col]):
            raise ValueError(f"Weight column '{weight_col}' must be numeric")

        if confidence_col and not pd.api.types.is_numeric_dtype(df[confidence_col]):
            raise ValueError(f"Confidence column '{confidence_col}' must be numeric")

    def _prepare_analysis_data(self, df: pd.DataFrame, protein1_col: str, protein2_col: str,
                              weight_col: str, annotation1_col: str, annotation2_col: str,
                              confidence_col: str, count_column: str, top_n: int, sort_by: str,
                              ascending: bool, annotation_filter_categories: List[str]) -> Dict:
        """Prepare data for analysis"""

        # Create working copy
        work_df = df.copy()

        # Add combined annotation analysis columns
        if annotation1_col and annotation2_col:
            work_df['_both_annotated'] = (~work_df[annotation1_col].isna()) & (~work_df[annotation2_col].isna())
            work_df['_one_annotated'] = ((~work_df[annotation1_col].isna()) & (work_df[annotation2_col].isna())) | \
                                       ((work_df[annotation1_col].isna()) & (~work_df[annotation2_col].isna()))
            work_df['_neither_annotated'] = (work_df[annotation1_col].isna()) & (work_df[annotation2_col].isna())

            # Create annotation status description
            work_df['_annotation_status'] = 'Neither annotated'
            work_df.loc[work_df['_one_annotated'], '_annotation_status'] = 'One annotated'
            work_df.loc[work_df['_both_annotated'], '_annotation_status'] = 'Both annotated'

        # Sort data
        sort_column = sort_by if sort_by else weight_col
        work_df = work_df.sort_values(sort_column, ascending=ascending)

        # Get top N results
        top_results = work_df.head(top_n).copy()

        # Analyze annotation categories
        annotation_analysis = {}
        if annotation_filter_categories:
            annotation_analysis = self._analyze_annotation_categories(
                work_df, annotation1_col, annotation2_col, annotation_filter_categories
            )

        analysis_data = {
            'original_df': df,
            'processed_df': work_df,
            'top_results': top_results,
            'top_n': top_n,
            'columns': {
                'protein1': protein1_col,
                'protein2': protein2_col,
                'weight': weight_col,
                'count': count_column,
                'annotation1': annotation1_col,
                'annotation2': annotation2_col,
                'confidence': confidence_col
            },
            'annotation_analysis': annotation_analysis,
            'total_interactions': len(work_df),
            'timestamp': datetime.now()
        }

        return analysis_data

    def _analyze_annotation_categories(self, df: pd.DataFrame, annotation1_col: str,
                                     annotation2_col: str, categories: List[str]) -> Dict:
        """Analyze specific annotation categories"""

        category_analysis = {}

        for category in categories:
            # Find interactions involving this category
            matches = pd.DataFrame()

            if annotation1_col:
                mask1 = df[annotation1_col].astype(str).str.contains(
                    category, case=False, na=False
                )
                matches = pd.concat([matches, df[mask1]])

            if annotation2_col:
                mask2 = df[annotation2_col].astype(str).str.contains(
                    category, case=False, na=False
                )
                matches = pd.concat([matches, df[mask2]])

            # Remove duplicates
            matches = matches.drop_duplicates()

            category_analysis[category] = {
                'total_matches': len(matches),
                'top_interactions': matches.head(10) if len(matches) > 0 else pd.DataFrame()
            }

        return category_analysis

    def _calculate_statistics(self, analysis_data: Dict, percentiles: List[int]) -> Dict:
        """Calculate comprehensive statistics"""

        df = analysis_data['processed_df']
        cols = analysis_data['columns']

        stats = {
            'basic_stats': {},
            'percentile_analysis': {},
            'annotation_stats': {},
            'distribution_stats': {}
        }

        # Basic statistics
        weight_col = cols['weight']
        stats['basic_stats']['weight'] = {
            'mean': df[weight_col].mean(),
            'median': df[weight_col].median(),
            'std': df[weight_col].std(),
            'min': df[weight_col].min(),
            'max': df[weight_col].max(),
            'count': len(df),
            'missing': df[weight_col].isna().sum()
        }

        if cols['confidence']:
            conf_col = cols['confidence']
            stats['basic_stats']['confidence'] = {
                'mean': df[conf_col].mean(),
                'median': df[conf_col].median(),
                'std': df[conf_col].std(),
                'min': df[conf_col].min(),
                'max': df[conf_col].max(),
                'missing': df[conf_col].isna().sum()
            }

        # Percentile analysis
        for percentile in percentiles:
            threshold = np.percentile(df[weight_col].dropna(), 100 - percentile)
            top_subset = df[df[weight_col] >= threshold]

            percentile_stats = {
                'threshold': threshold,
                'count': len(top_subset),
                'percentage_of_total': (len(top_subset) / len(df)) * 100,
                'weight_stats': {
                    'mean': top_subset[weight_col].mean(),
                    'std': top_subset[weight_col].std(),
                    'range': top_subset[weight_col].max() - top_subset[weight_col].min()
                }
            }

            if cols['confidence']:
                conf_subset = top_subset[cols['confidence']].dropna()
                if len(conf_subset) > 0:
                    percentile_stats['confidence_stats'] = {
                        'mean': conf_subset.mean(),
                        'std': conf_subset.std(),
                        'missing': top_subset[cols['confidence']].isna().sum()
                    }

            # Annotation analysis for this percentile
            if cols['annotation1'] and cols['annotation2']:
                percentile_stats['annotation_breakdown'] = {
                    'both_annotated': top_subset['_both_annotated'].sum(),
                    'one_annotated': top_subset['_one_annotated'].sum(),
                    'neither_annotated': top_subset['_neither_annotated'].sum()
                }

            stats['percentile_analysis'][f'top_{percentile}%'] = percentile_stats

        # Annotation statistics
        if cols['annotation1'] and cols['annotation2']:
            stats['annotation_stats'] = {
                'total_both_annotated': df['_both_annotated'].sum(),
                'total_one_annotated': df['_one_annotated'].sum(),
                'total_neither_annotated': df['_neither_annotated'].sum(),
                'annotation1_coverage': (~df[cols['annotation1']].isna()).sum() / len(df) * 100,
                'annotation2_coverage': (~df[cols['annotation2']].isna()).sum() / len(df) * 100
            }

            # Unique annotations
            if cols['annotation1']:
                unique_ann1 = df[cols['annotation1']].dropna().nunique()
                stats['annotation_stats']['unique_annotation1'] = unique_ann1

            if cols['annotation2']:
                unique_ann2 = df[cols['annotation2']].dropna().nunique()
                stats['annotation_stats']['unique_annotation2'] = unique_ann2

        return stats

    def _generate_html_report(self, analysis_data: Dict, title: str, include_plots: bool,
                             interactive_html: bool, plot_format: str, custom_css: str,
                             include_analysis_report: bool) -> str:
        """Generate HTML report"""

        html_parts = []

        # HTML header
        html_parts.extend([
            "<!DOCTYPE html>",
            "<html lang='en'>",
            "<head>",
            "<meta charset='UTF-8'>",
            "<meta name='viewport' content='width=device-width, initial-scale=1.0'>",
            f"<title>{title}</title>",
            self._get_default_css() if custom_css is None else custom_css,
            self._get_javascript() if interactive_html else "",
            "</head>",
            "<body>"
        ])

        # Report header
        html_parts.extend([
            f'<div class="report-container">',
            f'<h1 class="report-title">{title}</h1>',
            f'<p class="report-meta">Generated on: {analysis_data["timestamp"].strftime("%Y-%m-%d %H:%M:%S")}</p>',
            f'<p class="report-meta">Total interactions: {analysis_data["total_interactions"]:,}</p>',
            f'<p class="report-meta">Showing top {analysis_data["top_n"]} results</p>'
        ])

        # Interactive controls
        if interactive_html:
            html_parts.append(self._generate_interactive_controls(analysis_data))

        # Statistics section
        if 'statistics' in analysis_data:
            html_parts.append(self._generate_statistics_html(analysis_data['statistics']))

        # Top results table
        html_parts.append(self._generate_results_table_html(analysis_data, interactive_html))

        # Plots section
        if include_plots:
            html_parts.append(self._generate_plots_html(analysis_data, plot_format))

        # Annotation analysis
        if analysis_data['annotation_analysis']:
            html_parts.append(self._generate_annotation_analysis_html(analysis_data))

        if include_analysis_report:
            html_parts.extend(self.analysis_results.to_html(standalone=False, return_lines=True))

        # Footer
        html_parts.extend([
            '</div>',
            '</body>',
            '</html>'
        ])

        return '\n'.join(html_parts)

    def _generate_interactive_controls(self, analysis_data: Dict) -> str:
        """Generate interactive filter and sort controls"""

        cols = analysis_data['columns']

        controls_html = f'''
        <div class="controls-section">
            <h2>Interactive Controls</h2>

            <div class="control-group">
                <label for="filter-annotation">Filter by Annotation Status:</label>
                <select id="filter-annotation" onchange="filterTable()">
                    <option value="all">Show All</option>
                    <option value="both">Both Annotated</option>
                    <option value="one">One Annotated</option>
                    <option value="neither">Neither Annotated</option>
                </select>
            </div>

            <div class="control-group">
                <label for="sort-column">Sort By:</label>
                <select id="sort-column" onchange="sortTable()">
                    <option value="{cols['weight']}">Weight</option>
                    {f'<option value="{cols["confidence"]}">Confidence</option>' if cols['confidence'] else ''}
                    <option value="{cols['protein1']}">Protein 1</option>
                    <option value="{cols['protein2']}">Protein 2</option>
                </select>

                <label for="sort-order">Order:</label>
                <select id="sort-order" onchange="sortTable()">
                    <option value="desc">Descending</option>
                    <option value="asc">Ascending</option>
                </select>
            </div>

            <div class="control-group">
                <label for="search-box">Search Proteins:</label>
                <input type="text" id="search-box" placeholder="Enter protein name..."
                       onkeyup="searchTable()" />
            </div>

            <div class="control-group">
                <button onclick="resetFilters()">Reset All Filters</button>
            </div>
        </div>
        '''

        return controls_html

    def _generate_statistics_html(self, stats: Dict) -> str:
        """Generate statistics section HTML"""

        html_parts = ['<div class="statistics-section">', '<h2>Statistical Summary</h2>']

        # Basic statistics
        html_parts.append('<div class="stats-grid">')

        # Weight statistics
        weight_stats = stats['basic_stats']['weight']
        html_parts.append(f'''
            <div class="stat-card">
                <h3>Weight Statistics</h3>
                <table class="stat-table">
                    <tr><td>Mean:</td><td>{weight_stats["mean"]:.4f}</td></tr>
                    <tr><td>Median:</td><td>{weight_stats["median"]:.4f}</td></tr>
                    <tr><td>Std Dev:</td><td>{weight_stats["std"]:.4f}</td></tr>
                    <tr><td>Range:</td><td>[{weight_stats["min"]:.4f}, {weight_stats["max"]:.4f}]</td></tr>
                    <tr><td>Count:</td><td>{weight_stats["count"]:,}</td></tr>
                </table>
            </div>
        ''')

        # Confidence statistics (if available)
        if 'confidence' in stats['basic_stats']:
            conf_stats = stats['basic_stats']['confidence']
            html_parts.append(f'''
                <div class="stat-card">
                    <h3>Confidence Statistics</h3>
                    <table class="stat-table">
                        <tr><td>Mean:</td><td>{conf_stats["mean"]:.4f}</td></tr>
                        <tr><td>Median:</td><td>{conf_stats["median"]:.4f}</td></tr>
                        <tr><td>Std Dev:</td><td>{conf_stats["std"]:.4f}</td></tr>
                        <tr><td>Range:</td><td>[{conf_stats["min"]:.4f}, {conf_stats["max"]:.4f}]</td></tr>
                        <tr><td>Missing:</td><td>{conf_stats["missing"]:,}</td></tr>
                    </table>
                </div>
            ''')

        # Annotation statistics (if available)
        if 'annotation_stats' in stats:
            ann_stats = stats['annotation_stats']
            html_parts.append(f'''
                <div class="stat-card">
                    <h3>Annotation Coverage</h3>
                    <table class="stat-table">
                        <tr><td>Both Annotated:</td><td>{ann_stats["total_both_annotated"]:,}</td></tr>
                        <tr><td>One Annotated:</td><td>{ann_stats["total_one_annotated"]:,}</td></tr>
                        <tr><td>Neither Annotated:</td><td>{ann_stats["total_neither_annotated"]:,}</td></tr>
                        <tr><td>Annotation 1 Coverage:</td><td>{ann_stats["annotation1_coverage"]:.1f}%</td></tr>
                        <tr><td>Annotation 2 Coverage:</td><td>{ann_stats["annotation2_coverage"]:.1f}%</td></tr>
                    </table>
                </div>
            ''')

        html_parts.append('</div>')

        # Percentile analysis
        html_parts.append('<h3>Top Percentile Analysis</h3>')
        html_parts.append('<div class="percentile-grid">')

        for percentile_name, percentile_data in stats['percentile_analysis'].items():
            html_parts.append(f'''
                <div class="percentile-card">
                    <h4>{percentile_name.replace('_', ' ').title()}</h4>
                    <table class="stat-table">
                        <tr><td>Threshold:</td><td>{percentile_data["threshold"]:.4f}</td></tr>
                        <tr><td>Count:</td><td>{percentile_data["count"]:,}</td></tr>
                        <tr><td>% of Total:</td><td>{percentile_data["percentage_of_total"]:.2f}%</td></tr>
                        <tr><td>Mean Weight:</td><td>{percentile_data["weight_stats"]["mean"]:.4f}</td></tr>
                        <tr><td>Weight Range:</td><td>{percentile_data["weight_stats"]["range"]:.4f}</td></tr>
                    </table>
            ''')

            if 'annotation_breakdown' in percentile_data:
                breakdown = percentile_data['annotation_breakdown']
                html_parts.append(f'''
                    <div class="annotation-breakdown">
                        <strong>Annotation Breakdown:</strong><br>
                        Both: {breakdown["both_annotated"]}<br>
                        One: {breakdown["one_annotated"]}<br>
                        Neither: {breakdown["neither_annotated"]}
                    </div>
                ''')

            html_parts.append('</div>')

        html_parts.extend(['</div>', '</div>'])

        return '\n'.join(html_parts)

    def _generate_results_table_html(self, analysis_data: Dict, interactive: bool) -> str:
        """Generate results table HTML"""

        df = analysis_data['top_results']
        cols = analysis_data['columns']

        table_id = 'results-table' if interactive else ''
        table_class = 'interactive-table' if interactive else 'results-table'

        html_parts = [
            '<div class="results-section">',
            f'<h2>Top {analysis_data["top_n"]} Interactions</h2>',
            f'<table id="{table_id}" class="{table_class}">',
            '<thead><tr>'
        ]

        # Table headers
        headers = [
            ('Rank', 'rank'),
            ('Protein 1', cols['protein1']),
            ('Protein 2', cols['protein2']),
            ('Weight', cols['weight']),
            ('Count', cols['count'])
        ]

        if cols['confidence']:
            headers.append(('Confidence', cols['confidence']))

        if cols['annotation1']:
            headers.append(('Annotation 1', cols['annotation1']))

        if cols['annotation2']:
            headers.append(('Annotation 2', cols['annotation2']))

        if cols['annotation1'] and cols['annotation2']:
            headers.append(('Ann. Status', '_annotation_status'))

        for header_text, col_name in headers:
            html_parts.append(f'<th data-column="{col_name}">{header_text}</th>')

        html_parts.extend(['</tr>', '</thead>', '<tbody>'])

        # Table rows
        for idx, (_, row) in enumerate(df.iterrows(), 1):
            row_class = self._get_row_class(row, cols)
            html_parts.append(f'<tr class="{row_class}" data-annotation-status="{row.get("_annotation_status", "")}">')

            # Rank
            html_parts.append(f'<td>{idx}</td>')

            # Protein identifiers
            html_parts.append(f'<td class="protein-id">{row[cols["protein1"]]}</td>')
            html_parts.append(f'<td class="protein-id">{row[cols["protein2"]]}</td>')

            # Weight
            weight_val = row[cols['weight']]
            html_parts.append(f'<td class="numeric">{weight_val:.6f}</td>')

            count_val = row[cols['count']]
            html_parts.append(f'<td class="numeric">{count_val}</td>')

            # Confidence (if available)
            if cols['confidence']:
                conf_val = row[cols['confidence']]
                conf_str = f'{conf_val:.4f}' if not pd.isna(conf_val) else 'N/A'
                html_parts.append(f'<td class="numeric">{conf_str}</td>')

            # Annotations
            if cols['annotation1']:
                ann1 = row[cols['annotation1']] if not pd.isna(row[cols['annotation1']]) else 'N/A'
                html_parts.append(f'<td class="annotation">{ann1}</td>')

            if cols['annotation2']:
                ann2 = row[cols['annotation2']] if not pd.isna(row[cols['annotation2']]) else 'N/A'
                html_parts.append(f'<td class="annotation">{ann2}</td>')

            # Annotation status
            if cols['annotation1'] and cols['annotation2']:
                status = row.get('_annotation_status', 'Unknown')
                html_parts.append(f'<td class="status">{status}</td>')

            html_parts.append('</tr>')

        html_parts.extend(['</tbody>', '</table>', '</div>'])

        return '\n'.join(html_parts)

    def _get_row_class(self, row: pd.Series, cols: Dict) -> str:
        """Determine CSS class for table row based on annotation status"""

        if cols['annotation1'] and cols['annotation2']:
            if row.get('_both_annotated', False):
                return 'both-annotated'
            elif row.get('_one_annotated', False):
                return 'one-annotated'
            else:
                return 'neither-annotated'

        return ''

    def _generate_plots_html(self, analysis_data: Dict, plot_format: str) -> str:
        """Generate plots section HTML"""

        html_parts = ['<div class="plots-section">', '<h2>Data Visualizations</h2>']

        try:
            plots = self._create_analysis_plots(analysis_data)

            for plot_name, fig in plots.items():
                if fig is not None:
                    img_str = self._fig_to_base64(fig, format=plot_format)

                    html_parts.append(f'<div class="plot-container">')
                    html_parts.append(f'<h3>{plot_name.replace("_", " ").title()}</h3>')
                    html_parts.append(f'<img src="data:image/{plot_format};base64,{img_str}" alt="{plot_name}" class="plot-image">')
                    html_parts.append('</div>')

                    plt.close(fig)

        except Exception as e:
            html_parts.append(f'<p class="error">Error generating plots: {str(e)}</p>')

        html_parts.append('</div>')

        return '\n'.join(html_parts)

    def _create_analysis_plots(self, analysis_data: Dict) -> Dict:
        """Create analysis plots"""

        plots = {}
        df = analysis_data['processed_df']
        cols = analysis_data['columns']

        try:
            # Weight distribution
            fig1 = plt.figure(figsize=(12, 8))

            # Weight histogram
            ax1 = plt.subplot(2, 2, 1)
            df[cols['weight']].hist(bins=50, alpha=0.7, ax=ax1)
            ax1.set_xlabel('Weight')
            ax1.set_ylabel('Frequency')
            ax1.set_title('Weight Distribution')
            ax1.grid(True, alpha=0.3)

            # Top percentiles comparison
            ax2 = plt.subplot(2, 2, 2)
            if 'statistics' in analysis_data:
                percentiles = analysis_data['statistics']['percentile_analysis']
                perc_names = list(percentiles.keys())
                perc_means = [percentiles[p]['weight_stats']['mean'] for p in perc_names]

                ax2.bar(perc_names, perc_means, alpha=0.7)
                ax2.set_xlabel('Percentile')
                ax2.set_ylabel('Mean Weight')
                ax2.set_title('Mean Weight by Percentile')
                ax2.tick_params(axis='x', rotation=45)

            # Confidence vs Weight (if available)
            if cols['confidence']:
                ax3 = plt.subplot(2, 2, 3)
                valid_data = df[[cols['weight'], cols['confidence']]].dropna()
                ax3.scatter(valid_data[cols['weight']], valid_data[cols['confidence']],
                           alpha=0.6, s=20)
                ax3.set_xlabel('Weight')
                ax3.set_ylabel('Confidence')
                ax3.set_title('Weight vs Confidence')
                ax3.grid(True, alpha=0.3)

            # Annotation status breakdown
            if cols['annotation1'] and cols['annotation2']:
                ax4 = plt.subplot(2, 2, 4)
                status_counts = df['_annotation_status'].value_counts()
                colors = ['#ff9999', '#66b3ff', '#99ff99']

                wedges, texts, autotexts = ax4.pie(status_counts.values,
                                                  labels=status_counts.index,
                                                  autopct='%1.1f%%',
                                                  colors=colors)
                ax4.set_title('Annotation Status Distribution')

            plt.tight_layout()
            plots['distribution_analysis'] = fig1

            # Percentile analysis plot
            if 'statistics' in analysis_data:
                fig2 = plt.figure(figsize=(10, 6))

                stats = analysis_data['statistics']['percentile_analysis']
                percentiles = list(stats.keys())

                # Extract data for plotting
                counts = [stats[p]['count'] for p in percentiles]
                thresholds = [stats[p]['threshold'] for p in percentiles]

                ax1 = plt.subplot(1, 2, 1)
                ax1.bar(percentiles, counts, alpha=0.7, color='skyblue')
                ax1.set_xlabel('Percentile')
                ax1.set_ylabel('Number of Interactions')
                ax1.set_title('Interaction Counts by Percentile')
                ax1.tick_params(axis='x', rotation=45)

                ax2 = plt.subplot(1, 2, 2)
                ax2.bar(percentiles, thresholds, alpha=0.7, color='lightcoral')
                ax2.set_xlabel('Percentile')
                ax2.set_ylabel('Weight Threshold')
                ax2.set_title('Weight Thresholds by Percentile')
                ax2.tick_params(axis='x', rotation=45)

                plt.tight_layout()
                plots['percentile_analysis'] = fig2

        except Exception as e:
            print(f"Error creating plots: {e}")

        return plots

    def _generate_annotation_analysis_html(self, analysis_data: Dict) -> str:
        """Generate annotation analysis section HTML"""

        html_parts = [
            '<div class="annotation-analysis-section">',
            '<h2>Annotation Category Analysis</h2>'
        ]

        for category, data in analysis_data['annotation_analysis'].items():
            html_parts.append(f'''
                <div class="category-analysis">
                    <h3>Category: {category}</h3>
                    <p>Total matches: {data["total_matches"]}</p>
            ''')

            if len(data['top_interactions']) > 0:
                html_parts.append('<h4>Top Interactions:</h4>')
                html_parts.append('<ul>')

                cols = analysis_data['columns']
                for _, row in data['top_interactions'].head(5).iterrows():
                    html_parts.append(f'''
                        <li>{row[cols["protein1"]]} - {row[cols["protein2"]]}
                        (Weight: {row[cols["weight"]]: .4f})</li>
                    ''')

                html_parts.append('</ul>')

            html_parts.append('</div>')

        html_parts.append('</div>')

        return '\n'.join(html_parts)

    def _generate_text_report(self, analysis_data: Dict, title: str, include_analysis_report: bool) -> str:
        """Generate text format report"""

        lines = []

        # Header
        lines.extend([
            "=" * 80,
            title.upper(),
            "=" * 80,
            f"Generated on: {analysis_data['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}",
            f"Total interactions: {analysis_data['total_interactions']:,}",
            f"Showing top {analysis_data['top_n']} results",
            ""
        ])

        # Statistics
        if 'statistics' in analysis_data:
            lines.append("STATISTICAL SUMMARY")
            lines.append("-" * 40)

            # Weight statistics
            weight_stats = analysis_data['statistics']['basic_stats']['weight']
            lines.extend([
                f"Weight Statistics:",
                f"  Mean: {weight_stats['mean']:.4f}",
                f"  Median: {weight_stats['median']:.4f}",
                f"  Std Dev: {weight_stats['std']:.4f}",
                f"  Range: [{weight_stats['min']:.4f}, {weight_stats['max']:.4f}]",
                f"  Count: {weight_stats['count']:,}",
                ""
            ])

            # Percentile analysis
            lines.append("Percentile Analysis:")
            for perc_name, perc_data in analysis_data['statistics']['percentile_analysis'].items():
                lines.extend([
                    f"  {perc_name.replace('_', ' ').title()}:",
                    f"    Threshold: {perc_data['threshold']:.4f}",
                    f"    Count: {perc_data['count']:,} ({perc_data['percentage_of_total']:.2f}%)",
                    f"    Mean Weight: {perc_data['weight_stats']['mean']:.4f}",
                    ""
                ])

        # Top results
        lines.extend([
            f"TOP {analysis_data['top_n']} INTERACTIONS",
            "-" * 40
        ])

        cols = analysis_data['columns']
        df = analysis_data['top_results']

        # Create header
        header_parts = ["Rank", "Protein 1", "Protein 2", "Weight"]
        if cols['confidence']:
            header_parts.append("Confidence")
        if cols['annotation1']:
            header_parts.append("Annotation 1")
        if cols['annotation2']:
            header_parts.append("Annotation 2")

        lines.append(" | ".join(f"{h:15s}" for h in header_parts))
        lines.append("-" * (len(header_parts) * 17))

        # Add data rows
        for idx, (_, row) in enumerate(df.iterrows(), 1):
            row_parts = [
                f"{idx:4d}",
                f"{str(row[cols['protein1']])[:14]:15s}",
                f"{str(row[cols['protein2']])[:14]:15s}",
                f"{row[cols['weight']]:15.6f}"
            ]

            if cols['confidence']:
                conf_val = row[cols['confidence']] if not pd.isna(row[cols['confidence']]) else 'N/A'
                conf_str = f"{conf_val:.4f}" if conf_val != 'N/A' else 'N/A'
                row_parts.append(f"{conf_str:15s}")

            if cols['annotation1']:
                ann1 = str(row[cols['annotation1']])[:14] if not pd.isna(row[cols['annotation1']]) else 'N/A'
                row_parts.append(f"{ann1:15s}")

            if cols['annotation2']:
                ann2 = str(row[cols['annotation2']])[:14] if not pd.isna(row[cols['annotation2']]) else 'N/A'
                row_parts.append(f"{ann2:15s}")

            lines.append(" | ".join(row_parts))

        # Annotation analysis
        if analysis_data['annotation_analysis']:
            lines.extend([
                "",
                "ANNOTATION CATEGORY ANALYSIS",
                "-" * 40
            ])

            for category, data in analysis_data['annotation_analysis'].items():
                lines.extend([
                    f"Category: {category}",
                    f"  Total matches: {data['total_matches']}",
                    ""
                ])

        if include_analysis_report:
            lines.extend(self.analysis_results.to_text(return_lines=True))

        return "\n".join(lines)

    def _fig_to_base64(self, fig, format: str = 'png') -> str:
        """Convert matplotlib figure to base64 string"""
        buffer = BytesIO()
        fig.savefig(buffer, format=format, bbox_inches='tight', dpi=150)
        buffer.seek(0)
        img_str = base64.b64encode(buffer.getvalue()).decode()
        buffer.close()
        return img_str

    def _get_default_css(self) -> str:
        """Get default CSS styles for HTML report"""
        return '''
        <style>
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                margin: 0;
                padding: 20px;
                background-color: #f5f5f5;
                line-height: 1.6;
            }

            .report-container {
                max-width: 1400px;
                margin: 0 auto;
                background: white;
                padding: 30px;
                border-radius: 10px;
                box-shadow: 0 0 20px rgba(0,0,0,0.1);
            }

            .report-title {
                color: #2c3e50;
                border-bottom: 3px solid #3498db;
                padding-bottom: 10px;
                margin-bottom: 20px;
            }

            .report-meta {
                color: #7f8c8d;
                margin: 5px 0;
            }

            .controls-section {
                background: #ecf0f1;
                padding: 20px;
                border-radius: 5px;
                margin: 20px 0;
            }

            .control-group {
                display: inline-block;
                margin: 10px 20px 10px 0;
            }

            .control-group label {
                font-weight: bold;
                margin-right: 10px;
            }

            .control-group select, .control-group input {
                padding: 5px;
                border: 1px solid #bdc3c7;
                border-radius: 3px;
            }

            .statistics-section {
                margin: 30px 0;
            }

            .stats-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 20px;
                margin: 20px 0;
            }

            .stat-card {
                background: #f8f9fa;
                padding: 20px;
                border-radius: 8px;
                border-left: 4px solid #3498db;
            }

            .stat-table {
                width: 100%;
                border-collapse: collapse;
            }

            .stat-table td {
                padding: 8px;
                border-bottom: 1px solid #eee;
            }

            .stat-table td:first-child {
                font-weight: bold;
            }

            .percentile-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 15px;
                margin: 20px 0;
            }

            .percentile-card {
                background: #fff3cd;
                padding: 15px;
                border-radius: 5px;
                border: 1px solid #ffeaa7;
            }

            .results-table, .interactive-table {
                width: 100%;
                border-collapse: collapse;
                margin: 20px 0;
            }

            .results-table th, .interactive-table th {
                background-color: #34495e;
                color: white;
                padding: 12px;
                text-align: left;
                cursor: pointer;
            }

            .results-table td, .interactive-table td {
                padding: 10px;
                border-bottom: 1px solid #ddd;
            }

            .results-table tr:hover, .interactive-table tr:hover {
                background-color: #f5f5f5;
            }

            .protein-id {
                font-family: monospace;
                font-weight: bold;
                color: #2c3e50;
            }

            .numeric {
                text-align: right;
                font-family: monospace;
            }

            .annotation {
                max-width: 200px;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            .both-annotated {
                background-color: #d5f4e6 !important;
            }

            .one-annotated {
                background-color: #fff3cd !important;
            }

            .neither-annotated {
                background-color: #f8d7da !important;
            }

            .plots-section {
                margin: 30px 0;
            }

            .plot-container {
                margin: 30px 0;
                text-align: center;
            }

            .plot-image {
                max-width: 100%;
                height: auto;
                border: 1px solid #ddd;
                border-radius: 5px;
            }

            .annotation-analysis-section {
                margin: 30px 0;
            }

            .category-analysis {
                background: #f8f9fa;
                padding: 20px;
                margin: 15px 0;
                border-radius: 5px;
                border-left: 4px solid #e74c3c;
            }

            .error {
                color: #e74c3c;
                background: #fadbd8;
                padding: 10px;
                border-radius: 5px;
            }

            .hidden {
                display: none;
            }

            button {
                background-color: #3498db;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                cursor: pointer;
            }

            button:hover {
                background-color: #2980b9;
            }
        </style>
        '''

    def _get_javascript(self) -> str:
        """Get JavaScript for interactive functionality"""
        return '''
        <script>
            let originalTableData = [];

            document.addEventListener('DOMContentLoaded', function() {
                // Store original table data
                const table = document.getElementById('results-table');
                if (table) {
                    const rows = table.querySelectorAll('tbody tr');
                    rows.forEach(row => {
                        originalTableData.push(row.cloneNode(true));
                    });
                }
            });

            function filterTable() {
                const filterValue = document.getElementById('filter-annotation').value;
                const table = document.getElementById('results-table');
                const rows = table.querySelectorAll('tbody tr');

                rows.forEach(row => {
                    const annotationStatus = row.getAttribute('data-annotation-status').toLowerCase();

                    if (filterValue === 'all') {
                        row.style.display = '';
                    } else if (filterValue === 'both' && annotationStatus === 'both annotated') {
                        row.style.display = '';
                    } else if (filterValue === 'one' && annotationStatus === 'one annotated') {
                        row.style.display = '';
                    } else if (filterValue === 'neither' && annotationStatus === 'neither annotated') {
                        row.style.display = '';
                    } else {
                        row.style.display = 'none';
                    }
                });

                updateRowNumbers();
            }

            function sortTable() {
                const table = document.getElementById('results-table');
                const tbody = table.querySelector('tbody');
                const sortColumn = document.getElementById('sort-column').value;
                const sortOrder = document.getElementById('sort-order').value;

                const rows = Array.from(tbody.querySelectorAll('tr'));
                const columnIndex = getColumnIndex(sortColumn);

                rows.sort((a, b) => {
                    let aVal = a.cells[columnIndex].textContent.trim();
                    let bVal = b.cells[columnIndex].textContent.trim();

                    // Try to parse as numbers
                    const aNum = parseFloat(aVal);
                    const bNum = parseFloat(bVal);

                    if (!isNaN(aNum) && !isNaN(bNum)) {
                        return sortOrder === 'asc' ? aNum - bNum : bNum - aNum;
                    } else {
                        return sortOrder === 'asc' ?
                            aVal.localeCompare(bVal) : bVal.localeCompare(aVal);
                    }
                });

                // Clear and repopulate tbody
                tbody.innerHTML = '';
                rows.forEach(row => tbody.appendChild(row));

                updateRowNumbers();
            }

            function searchTable() {
                const searchTerm = document.getElementById('search-box').value.toLowerCase();
                const table = document.getElementById('results-table');
                const rows = table.querySelectorAll('tbody tr');

                rows.forEach(row => {
                    const text = row.textContent.toLowerCase();
                    if (text.includes(searchTerm)) {
                        row.style.display = '';
                    } else {
                        row.style.display = 'none';
                    }
                });

                updateRowNumbers();
            }

            function resetFilters() {
                document.getElementById('filter-annotation').value = 'all';
                document.getElementById('sort-column').selectedIndex = 0;
                document.getElementById('sort-order').value = 'desc';
                document.getElementById('search-box').value = '';

                // Restore original table
                const table = document.getElementById('results-table');
                const tbody = table.querySelector('tbody');
                tbody.innerHTML = '';

                originalTableData.forEach(row => {
                    tbody.appendChild(row.cloneNode(true));
                });

                updateRowNumbers();
            }

            function getColumnIndex(columnName)   {
                const table = document.getElementById('results-table');
                const headers = table.querySelectorAll('th');

                for (let i = 0; i < headers.length; i++) {
                    if (headers[i].getAttribute('data-column') === columnName) {
                        return i;
                    }
                }
                return 0;
            }

            function updateRowNumbers() {
                const table = document.getElementById('results-table');
                const visibleRows = table.querySelectorAll('tbody tr:not([style*="display: none"])');

                visibleRows.forEach((row, index) => {
                    row.cells[0].textContent = index + 1;
                });
            }
        </script>
        '''

def _rm_duplicates(
        df: pd.DataFrame, idx1: pd.Index, idx2: pd.Index=None
        ) -> pd.DataFrame:
    """
    Removes duplicates of omics data pairs that have been generated
    during the calculation of association values.

    Parameters
    ----------
    df : pandas.DataFrame
        DataFrame that should be cleaned.
    idx1 : pandas.Index
        Index object containing omics identifiers. If ``idx2`` is not
        passed to the function the assumption is that items recoreded in
        ``idx1`` are associated with each other.
    idx2 : pandas.Index, default=None
        Index object containing omics identifiers. If provided the
        assumption is that association pairs should only be of type
        [idx1, idx2]. Any pairs [idx1, idx1] or [idx2, idx2] are
        removed.

    Returns
    -------
    pandas.DataFrame
        Filtered panadas.DataFrame object that has duplicates removed.

    Notes
    -----
    The function serves two purposes:

    1. If the `DataFrame` passed to the function contains items from
       only one omics type (indicated by omitting `idx2` / setting it to
       `None`, see also ``valpas.utils.data_handling.prep_data`)), then
       the function will extract the upper triangle (any association
       measure implemented should be symmetric i.e.
       :math:`A(a,b)=A(b,a)`)
    2. If both `idx1` and `idx2` is passed to the function, it is
       assumed that the DF contains items from two different omics
       types. In this case the DF is filtered such that `DF.index` only
       contains items from `idx1` and `DF.columns` contains only items
       of `idx2`.
    """

    if idx1.equals(idx2):
        # use case for this block: if the correlation matrix is NxN and
        # each n in N is from only one data source we can reduce the
        # output to pervent *association(i,j)* and *association(j,i)*
        # to show up in the output. Note that if the correlation matrix
        # contains NxM elements and N & M are two different sets of
        # data points, choosing to reduce the input will remove unique
        # results.
        #
        # The code block extracts the upper triangle of the matrix,
        # sets the lower triangle (including the diagonal) to NaN.
        # `pd.DataFrame.stack()` drops NaNs by default and therefore
        # excludes the pairs from sorting and being returned.
        upper_tri = np.triu(df, -1)
        upper_tri[np.tril_indices(upper_tri.shape[0], 0)] = np.nan

        df_ret = pd.DataFrame(
            data=upper_tri,
            index=df.index,
            columns=df.columns
            )
        return df_ret
    else:
        # This covers case (2) listed in the docstring, i.e. the
        # the DataFrame contains data from two different omics data
        # data types. In this case we filter the DF such that the rows
        # are limited to items from `idx1` and the columns are limited
        # to `idx2`.

        df_ret = df.drop(
            labels=df.index.difference(idx2),
            axis='index',
            )
        df_ret.drop(
            labels=df.columns.difference(idx1),
            axis='columns',
            inplace=True)
        return df_ret
