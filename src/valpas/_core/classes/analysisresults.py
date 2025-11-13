import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Dict, List, Optional, Union, Any, Tuple
import base64
from io import BytesIO
import json
import torch
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

class AnalysisResults:
    """
    Base class for storing and presenting analysis results
    """

    def __init__(self, results_dict: Dict = None, analysis_type: str = "Generic Analysis",
                 timestamp: datetime = None, metadata: Dict = None):
        """
        Initialize base analysis results

        Args:
            results_dict: Dictionary containing analysis results
            analysis_type: Type of analysis performed
            timestamp: When analysis was performed
            metadata: Additional metadata about the analysis
        """
        self.results = results_dict or {}
        self.analysis_type = analysis_type
        self.timestamp = timestamp or datetime.now()
        self.metadata = metadata or {}

    def get_result(self, key: str, default=None):
        """Get a specific result by key"""
        return self.results.get(key, default)

    def set_result(self, key: str, value: Any):
        """Set a specific result"""
        self.results[key] = value

    def get_summary_stats(self) -> Dict:
        """Get summary statistics - to be overridden by subclasses"""
        return {
            'analysis_type': self.analysis_type,
            'timestamp': self.timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'n_results': len(self.results),
            'result_keys': list(self.results.keys())
        }

    def to_text(self, include_details: bool = True) -> str:
        """
        Generate text representation of results

        Args:
            include_details: Whether to include detailed results

        Returns:
            Formatted text string
        """
        text_parts = []

        # Header
        text_parts.append(f"{'='*60}")
        text_parts.append(f"{self.analysis_type.upper()}")
        text_parts.append(f"{'='*60}")
        text_parts.append(f"Analysis Date: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
        text_parts.append("")

        # Summary statistics
        summary = self.get_summary_stats()
        text_parts.append("SUMMARY:")
        for key, value in summary.items():
            if key not in ['analysis_type', 'timestamp']:
                text_parts.append(f"  {key}: {value}")
        text_parts.append("")

        # Metadata
        if self.metadata:
            text_parts.append("METADATA:")
            for key, value in self.metadata.items():
                text_parts.append(f"  {key}: {value}")
            text_parts.append("")

        if include_details:
            text_parts.append("DETAILED RESULTS:")
            text_parts.append("-" * 40)
            text_parts.extend(self._generate_detailed_text())

        return "\n".join(text_parts)

    def to_html(self, standalone: bool = True, include_plots: bool = True,
                plot_format: str = 'png', **plot_kwargs) -> str:
        """
        Generate HTML representation of results

        Args:
            standalone: Whether to generate complete HTML page or just content
            include_plots: Whether to include plots in HTML
            plot_format: Format for embedded plots ('png', 'svg')
            **plot_kwargs: Additional arguments for plotting

        Returns:
            HTML string
        """
        html_parts = []

        # HTML header (if standalone)
        if standalone:
            html_parts.extend([
                "<!DOCTYPE html>",
                "<html>",
                "<head>",
                f"<title>{self.analysis_type} Results</title>",
                "<style>",
                self._get_default_css(),
                "</style>",
                "</head>",
                "<body>"
            ])

        # Main content
        html_parts.append(f'<div class="analysis-results">')

        # Header
        html_parts.extend([
            f'<h1 class="analysis-title">{self.analysis_type}</h1>',
            f'<p class="analysis-date">Analysis Date: {self.timestamp.strftime("%Y-%m-%d %H:%M:%S")}</p>'
        ])

        # Summary
        html_parts.append('<div class="summary-section">')
        html_parts.append('<h2>Summary</h2>')
        html_parts.append(self._generate_summary_html())
        html_parts.append('</div>')

        # Metadata
        if self.metadata:
            html_parts.append('<div class="metadata-section">')
            html_parts.append('<h2>Metadata</h2>')
            html_parts.append(self._generate_metadata_html())
            html_parts.append('</div>')

        # Detailed results
        html_parts.append('<div class="details-section">')
        html_parts.append('<h2>Detailed Results</h2>')
        html_parts.append(self._generate_detailed_html())
        html_parts.append('</div>')

        # Plots
        if include_plots:
            html_parts.append('<div class="plots-section">')
            html_parts.append('<h2>Visualizations</h2>')
            html_parts.append(self._generate_plots_html(plot_format, **plot_kwargs))
            html_parts.append('</div>')

        html_parts.append('</div>')

        # HTML footer (if standalone)
        if standalone:
            html_parts.extend([
                "</body>",
                "</html>"
            ])

        return "\n".join(html_parts)

    def save_results(self, filepath: str, format: str = 'json'):
        """
        Save results to file

        Args:
            filepath: Path to save file
            format: Format to save ('json', 'pickle', 'text', 'html')
        """
        if format == 'json':
            # Convert numpy arrays and other non-serializable objects
            serializable_results = self._make_json_serializable(self.results)
            with open(filepath, 'w') as f:
                json.dump({
                    'analysis_type': self.analysis_type,
                    'timestamp': self.timestamp.isoformat(),
                    'metadata': self.metadata,
                    'results': serializable_results
                }, f, indent=2)

        elif format == 'pickle':
            import pickle
            with open(filepath, 'wb') as f:
                pickle.dump(self, f)

        elif format == 'text':
            with open(filepath, 'w') as f:
                f.write(self.to_text())

        elif format == 'html':
            with open(filepath, 'w') as f:
                f.write(self.to_html())

        else:
            raise ValueError(f"Unsupported format: {format}")

    def _generate_detailed_text(self) -> List[str]:
        """Generate detailed text representation - to be overridden"""
        return [f"{key}: {value}" for key, value in self.results.items()]

    def _generate_summary_html(self) -> str:
        """Generate summary HTML"""
        summary = self.get_summary_stats()
        html = '<table class="summary-table">'
        for key, value in summary.items():
            if key not in ['analysis_type', 'timestamp']:
                html += f'<tr><td><strong>{key.replace("_", " ").title()}:</strong></td><td>{value}</td></tr>'
        html += '</table>'
        return html

    def _generate_metadata_html(self) -> str:
        """Generate metadata HTML"""
        html = '<table class="metadata-table">'
        for key, value in self.metadata.items():
            html += f'<tr><td><strong>{key.replace("_", " ").title()}:</strong></td><td>{value}</td></tr>'
        html += '</table>'
        return html

    def _generate_detailed_html(self) -> str:
        """Generate detailed results HTML - to be overridden"""
        return '<p>Detailed results not implemented for base class</p>'

    def _generate_plots_html(self, plot_format: str = 'png', **plot_kwargs) -> str:
        """Generate plots HTML - to be overridden"""
        return '<p>Plots not implemented for base class</p>'

    def _get_default_css(self) -> str:
        """Get default CSS for HTML output"""
        return """
        body { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }
        .analysis-results { max-width: 1200px; margin: 0 auto; }
        .analysis-title { color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }
        .analysis-date { color: #7f8c8d; font-style: italic; }
        .summary-section, .metadata-section, .details-section, .plots-section {
            margin: 30px 0; padding: 20px; background-color: #f8f9fa; border-radius: 5px;
        }
        .summary-table, .metadata-table, .results-table {
            width: 100%; border-collapse: collapse; margin: 10px 0;
        }
        .summary-table td, .metadata-table td, .results-table td, .results-table th {
            padding: 8px 12px; border: 1px solid #dee2e6;
        }
        .results-table th { background-color: #e9ecef; font-weight: bold; }
        .plot-container { margin: 20px 0; text-align: center; }
        .plot-title { font-weight: bold; margin: 10px 0; color: #2c3e50; }
        .metric-good { color: #27ae60; font-weight: bold; }
        .metric-warning { color: #f39c12; font-weight: bold; }
        .metric-poor { color: #e74c3c; font-weight: bold; }
        .config-section { background-color: #f1f2f6; padding: 15px; border-radius: 5px; }
        .config-section h3 { margin-top: 0; color: #2c3e50; }
        """

    def _make_json_serializable(self, obj):
        """Convert numpy arrays and other objects to JSON-serializable format"""
        if isinstance(obj, dict):
            return {key: self._make_json_serializable(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [self._make_json_serializable(item) for item in obj]
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, (np.integer, np.floating)):
            return obj.item()
        elif isinstance(obj, pd.DataFrame):
            return obj.to_dict()
        elif hasattr(obj, '__dict__'):
            return str(obj)  # For complex objects, convert to string
        else:
            return obj
