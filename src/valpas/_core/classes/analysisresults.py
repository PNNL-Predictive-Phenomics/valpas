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

class WeightedCorrelationAnalysisResults(AnalysisResults):
    """
    Specialized class for weighted correlation analysis results
    """

    def __init__(self, results_dict: Dict, original_data: pd.DataFrame = None,
                 interactions: List[Tuple[str, str]] = None):
        """
        Initialize weighted correlation analysis results

        Args:
            results_dict: Results from learn_correlation_weights function
            original_data: Original proteomics data used in analysis
            interactions: Original interaction list used in analysis
        """
        super().__init__(
            results_dict=results_dict,
            analysis_type="Weighted Correlation Analysis",
            metadata=results_dict.get('config', {})
        )

        self.original_data = original_data
        self.interactions = interactions

        # Extract key components for easy access
        self.model = results_dict.get('model')
        self.learned_weights = results_dict.get('learned_weights')
        self.weights_dataframe = results_dict.get('weights_dataframe')
        self.correlation_matrix = results_dict.get('weighted_correlation_matrix')
        self.training_metrics = results_dict.get('training_metrics', {})
        self.validation_metrics = results_dict.get('validation_metrics', {})
        self.training_history = results_dict.get('training_history', {})
        self.config = results_dict.get('config', {})

    def get_summary_stats(self) -> Dict:
        """Get comprehensive summary statistics"""
        base_stats = super().get_summary_stats()

        # Performance metrics
        train_auc = self.training_metrics.get('auc', 0)
        val_auc = self.validation_metrics.get('auc', 0)
        train_ap = self.training_metrics.get('average_precision', 0)
        val_ap = self.validation_metrics.get('average_precision', 0)

        # Weight statistics
        if self.weights_dataframe is not None:
            weight_stats = {
                'max_weight': self.weights_dataframe['weight'].max(),
                'min_weight': self.weights_dataframe['weight'].min(),
                'weight_std': self.weights_dataframe['weight'].std(),
                'weight_entropy': self._calculate_weight_entropy(),
                'top_condition': self.weights_dataframe.iloc[0]['condition']
            }
        else:
            weight_stats = {}

        # Data information
        data_info = {}
        if 'original_data_shape' in self.results:
            data_info['original_proteins'] = self.results['original_data_shape'][0]
            data_info['original_conditions'] = self.results['original_data_shape'][1]
        if 'processed_data_shape' in self.results:
            data_info['processed_proteins'] = self.results['processed_data_shape'][0]
            data_info['processed_conditions'] = self.results['processed_data_shape'][1]

        return {
            **base_stats,
            'learning_method': self.config.get('learning_method', 'unknown'),
            'training_auc': train_auc,
            'validation_auc': val_auc,
            'training_ap': train_ap,
            'validation_ap': val_ap,
            'performance_gap': abs(train_auc - val_auc),
            'n_interactions_train': len(self.results.get('train_interactions', [])),
            'n_interactions_val': len(self.results.get('val_interactions', [])),
            **weight_stats,
            **data_info
        }

    def get_performance_assessment(self) -> str:
        """Assess model performance quality"""
        val_auc = self.validation_metrics.get('auc', 0)

        if val_auc >= 0.9:
            return "Excellent"
        elif val_auc >= 0.8:
            return "Good"
        elif val_auc >= 0.7:
            return "Fair"
        elif val_auc >= 0.6:
            return "Poor"
        else:
            return "Very Poor"

    def get_top_conditions(self, n: int = 10) -> pd.DataFrame:
        """Get top N weighted conditions"""
        if self.weights_dataframe is None:
            return pd.DataFrame()
        return self.weights_dataframe.head(n)

    def get_weight_concentration_stats(self) -> Dict:
        """Calculate weight concentration statistics"""
        if self.weights_dataframe is None:
            return {}

        weights = self.weights_dataframe['weight'].values
        n_conditions = len(weights)

        return {
            'top_10_percent_weight': weights[:n_conditions//10].sum(),
            'top_25_percent_weight': weights[:n_conditions//4].sum(),
            'gini_coefficient': self._calculate_gini_coefficient(weights),
            'effective_conditions': 1 / np.sum(weights**2)  # Inverse Simpson diversity
        }

    def _calculate_weight_entropy(self) -> float:
        """Calculate entropy of weight distribution"""
        if self.weights_dataframe is None:
            return 0

        weights = self.weights_dataframe['weight'].values
        weights = weights / np.sum(weights)  # Normalize
        return -np.sum(weights * np.log(weights + 1e-10))

    def _calculate_gini_coefficient(self, weights: np.ndarray) -> float:
        """Calculate Gini coefficient for weight inequality"""
        sorted_weights = np.sort(weights)
        n = len(weights)
        cumsum = np.cumsum(sorted_weights)
        return (n + 1 - 2 * np.sum(cumsum) / cumsum[-1]) / n

    def _generate_detailed_text(self) -> List[str]:
        """Generate detailed text representation"""
        lines = []

        # Performance Section
        lines.append("PERFORMANCE METRICS:")
        lines.append(f"  Training AUC: {self.training_metrics.get('auc', 0):.4f}")
        lines.append(f"  Validation AUC: {self.validation_metrics.get('auc', 0):.4f}")
        lines.append(f"  Training AP: {self.training_metrics.get('average_precision', 0):.4f}")
        lines.append(f"  Validation AP: {self.validation_metrics.get('average_precision', 0):.4f}")
        lines.append(f"  Performance Assessment: {self.get_performance_assessment()}")
        lines.append("")

        # Weight Analysis
        if self.weights_dataframe is not None:
            lines.append("WEIGHT ANALYSIS:")
            concentration_stats = self.get_weight_concentration_stats()
            lines.append(f"  Entropy: {self._calculate_weight_entropy():.4f}")
            lines.append(f"  Gini Coefficient: {concentration_stats.get('gini_coefficient', 0):.4f}")
            lines.append(f"  Effective Conditions: {concentration_stats.get('effective_conditions', 0):.1f}")
            lines.append(f"  Top 10% Conditions Weight: {concentration_stats.get('top_10_percent_weight', 0):.2%}")
            lines.append("")

            lines.append("TOP 10 WEIGHTED CONDITIONS:")
            top_conditions = self.get_top_conditions(10)
            for idx, row in top_conditions.iterrows():
                lines.append(f"  {row['condition']}: {row['weight']:.6f}")
            lines.append("")

        # Configuration
        lines.append("CONFIGURATION:")
        for key, value in self.config.items():
            lines.append(f"  {key}: {value}")
        lines.append("")

        # Data Information
        if 'missing_data_info' in self.results:
            missing_info = self.results['missing_data_info']
            lines.append("MISSING DATA HANDLING:")
            lines.append(f"  Strategy: {missing_info.get('strategy_used', 'N/A')}")
            lines.append(f"  Original Missing: {missing_info.get('missing_percentage', 0):.2f}%")
            if 'after_processing' in missing_info:
                lines.append(f"  After Processing: {missing_info['after_processing'].get('missing_percentage', 0):.2f}%")
            lines.append("")

        return lines

    def _generate_detailed_html(self) -> str:
        """Generate detailed HTML representation"""
        html_parts = []

        # Performance metrics table
        html_parts.append('<h3>Performance Metrics</h3>')
        html_parts.append('<table class="results-table">')
        html_parts.append('<tr><th>Metric</th><th>Training</th><th>Validation</th><th>Assessment</th></tr>')

        train_auc = self.training_metrics.get('auc', 0)
        val_auc = self.validation_metrics.get('auc', 0)
        train_ap = self.training_metrics.get('average_precision', 0)
        val_ap = self.validation_metrics.get('average_precision', 0)

        auc_class = self._get_metric_class(val_auc, 0.8, 0.7)
        ap_class = self._get_metric_class(val_ap, 0.8, 0.7)

        html_parts.append(f'<tr><td>AUC</td><td>{train_auc:.4f}</td><td class="{auc_class}">{val_auc:.4f}</td><td>{self.get_performance_assessment()}</td></tr>')
        html_parts.append(f'<tr><td>Average Precision</td><td>{train_ap:.4f}</td><td class="{ap_class}">{val_ap:.4f}</td><td>-</td></tr>')
        html_parts.append('</table>')

        # Weight analysis
        if self.weights_dataframe is not None:
            html_parts.append('<h3>Weight Analysis</h3>')
            concentration_stats = self.get_weight_concentration_stats()

            html_parts.append('<table class="results-table">')
            html_parts.append('<tr><th>Statistic</th><th>Value</th><th>Interpretation</th></tr>')

            entropy = self._calculate_weight_entropy()
            gini = concentration_stats.get('gini_coefficient', 0)
            effective_cond = concentration_stats.get('effective_conditions', 0)

            html_parts.append(f'<tr><td>Weight Entropy</td><td>{entropy:.4f}</td><td>{"High diversity" if entropy > 2.5 else "Moderate diversity" if entropy > 1.5 else "Low diversity"}</td></tr>')
            html_parts.append(f'<tr><td>Gini Coefficient</td><td>{gini:.4f}</td><td>{"High inequality" if gini > 0.7 else "Moderate inequality" if gini > 0.4 else "Low inequality"}</td></tr>')
            html_parts.append(f'<tr><td>Effective Conditions</td><td>{effective_cond:.1f}</td><td>Equivalent to {effective_cond:.1f} equally-weighted conditions</td></tr>')
            html_parts.append('</table>')

            # Top conditions table
            html_parts.append('<h3>Top Weighted Conditions</h3>')
            top_conditions = self.get_top_conditions(15)

            html_parts.append('<table class="results-table">')
            html_parts.append('<tr><th>Rank</th><th>Condition</th><th>Weight</th><th>Percentage</th></tr>')

            for idx, (_, row) in enumerate(top_conditions.iterrows(), 1):
                percentage = row['weight'] * 100
                html_parts.append(f'<tr><td>{idx}</td><td>{row["condition"]}</td><td>{row["weight"]:.6f}</td><td>{percentage:.3f}%</td></tr>')

            html_parts.append('</table>')

        # Configuration section
        html_parts.append('<div class="config-section">')
        html_parts.append('<h3>Analysis Configuration</h3>')
        html_parts.append('<table class="results-table">')
        html_parts.append('<tr><th>Parameter</th><th>Value</th></tr>')

        for key, value in self.config.items():
            display_key = key.replace('_', ' ').title()
            html_parts.append(f'<tr><td>{display_key}</td><td>{value}</td></tr>')

        html_parts.append('</table>')
        html_parts.append('</div>')

        return '\n'.join(html_parts)

    def _generate_plots_html(self, plot_format: str = 'png', **plot_kwargs) -> str:
        """Generate plots HTML with embedded images"""
        html_parts = []

        try:
            # Create plots
            plots = self.create_plots(**plot_kwargs)

            for plot_name, fig in plots.items():
                if fig is not None:
                    # Convert plot to base64 string
                    img_str = self._fig_to_base64(fig, format=plot_format)

                    html_parts.append(f'<div class="plot-container">')
                    html_parts.append(f'<div class="plot-title">{plot_name.replace("_", " ").title()}</div>')
                    html_parts.append(f'<img src="data:image/{plot_format};base64,{img_str}" alt="{plot_name}" style="max-width: 100%; height: auto;">')
                    html_parts.append('</div>')

                    plt.close(fig)  # Clean up

        except Exception as e:
            html_parts.append(f'<p class="error">Error generating plots: {str(e)}</p>')

        return '\n'.join(html_parts)

    def _get_metric_class(self, value: float, good_threshold: float, fair_threshold: float) -> str:
        """Get CSS class for metric value"""
        if value >= good_threshold:
            return "metric-good"
        elif value >= fair_threshold:
            return "metric-warning"
        else:
            return "metric-poor"

    def _fig_to_base64(self, fig, format: str = 'png') -> str:
        """Convert matplotlib figure to base64 string"""
        buffer = BytesIO()
        fig.savefig(buffer, format=format, bbox_inches='tight', dpi=150)
        buffer.seek(0)
        img_str = base64.b64encode(buffer.getvalue()).decode()
        buffer.close()
        return img_str

    def create_plots(self, figsize: Tuple[int, int] = (15, 12), **kwargs) -> Dict:
        """
        Create visualization plots

        Args:
            figsize: Figure size for plots
            **kwargs: Additional plotting parameters

        Returns:
            Dictionary of plot names to figure objects
        """
        plots = {}

        try:
            # 1. Weight distribution plot
            if self.weights_dataframe is not None:
                fig1 = plt.figure(figsize=(12, 8))

                # Weight bar plot
                ax1 = plt.subplot(2, 2, 1)
                top_weights = self.weights_dataframe.head(20)
                bars = ax1.bar(range(len(top_weights)), top_weights['weight'])
                ax1.set_xlabel('Condition Rank')
                ax1.set_ylabel('Weight')
                ax1.set_title('Top 20 Condition Weights')
                ax1.grid(True, alpha=0.3)

                # Weight histogram
                ax2 = plt.subplot(2, 2, 2)
                ax2.hist(self.weights_dataframe['weight'], bins=30, alpha=0.7, edgecolor='black')
                ax2.axvline(self.weights_dataframe['weight'].mean(), color='red', linestyle='--',
                           label=f'Mean: {self.weights_dataframe["weight"].mean():.4f}')
                ax2.set_xlabel('Weight Value')
                ax2.set_ylabel('Frequency')
                ax2.set_title('Weight Distribution')
                ax2.legend()
                ax2.grid(True, alpha=0.3)

                # Training progress (if available)
                ax3 = plt.subplot(2, 2, 3)
                if len(self.training_history.get('iteration', [])) > 1:
                    ax3.plot(self.training_history['iteration'], self.training_history['train_objective'], 'b-', linewidth=2)
                    ax3.set_xlabel('Iteration')
                    ax3.set_ylabel('Objective (AUC)')
                    ax3.set_title('Training Progress')
                    ax3.grid(True, alpha=0.3)
                else:
                    ax3.text(0.5, 0.5, 'Single iteration training\n(e.g., Ridge Regression)',
                            ha='center', va='center', transform=ax3.transAxes)
                    ax3.set_title('Training Progress')

                # Performance comparison
                ax4 = plt.subplot(2, 2, 4)
                metrics = ['AUC', 'Average Precision']
                train_vals = [self.training_metrics.get('auc', 0), self.training_metrics.get('average_precision', 0)]
                val_vals = [self.validation_metrics.get('auc', 0), self.validation_metrics.get('average_precision', 0)]

                x = np.arange(len(metrics))
                width = 0.35

                bars1 = ax4.bar(x - width/2, train_vals, width, label='Training', alpha=0.7)
                bars2 = ax4.bar(x + width/2, val_vals, width, label='Validation', alpha=0.7)

                ax4.set_ylabel('Score')
                ax4.set_title('Performance Comparison')
                ax4.set_xticks(x)
                ax4.set_xticklabels(metrics)
                ax4.legend()
                ax4.grid(True, alpha=0.3)

                # Add value labels
                for bars in [bars1, bars2]:
                    for bar in bars:
                        height = bar.get_height()
                        ax4.text(bar.get_x() + bar.get_width()/2., height + 0.01,
                                f'{height:.3f}', ha='center', va='bottom', fontsize=8)

                plt.tight_layout()
                plots['weight_analysis'] = fig1

            # 2. Correlation matrix heatmap (if available and not too large)
            if self.correlation_matrix is not None and len(self.correlation_matrix) <= 100:
                fig2 = plt.figure(figsize=(10, 8))

                # Sample subset if still too large for visualization
                if len(self.correlation_matrix) > 50:
                    sample_indices = np.random.choice(len(self.correlation_matrix), 50, replace=False)
                    plot_matrix = self.correlation_matrix.iloc[sample_indices, sample_indices]
                    title_suffix = " (50 random proteins)"
                else:
                    plot_matrix = self.correlation_matrix
                    title_suffix = ""

                sns.heatmap(plot_matrix, cmap='RdBu_r', center=0, square=True,
                           cbar_kws={'label': 'Weighted Correlation'})
                plt.title(f'Weighted Correlation Matrix{title_suffix}')
                plt.tight_layout()
                plots['correlation_matrix'] = fig2

            # 3. ROC curves (if available)
            if ('fpr' in self.training_metrics and 'tpr' in self.training_metrics and
                'fpr' in self.validation_metrics and 'tpr' in self.validation_metrics):

                fig3 = plt.figure(figsize=(10, 6))

                # ROC curve
                ax1 =plt.subplot(1, 2, 1)
                ax1.plot(self.training_metrics['fpr'], self.training_metrics['tpr'],
                        label=f'Training (AUC = {self.training_metrics["auc"]:.3f})', linewidth=2)
                ax1.plot(self.validation_metrics['fpr'], self.validation_metrics['tpr'],
                        label=f'Validation (AUC = {self.validation_metrics["auc"]:.3f})', linewidth=2)
                ax1.plot([0, 1], [0, 1], 'k--', alpha=0.5, label='Random')
                ax1.set_xlabel('False Positive Rate')
                ax1.set_ylabel('True Positive Rate')
                ax1.set_title('ROC Curves')
                ax1.legend()
                ax1.grid(True, alpha=0.3)

                # Precision-Recall curve (if available)
                if ('precision' in self.training_metrics and 'recall' in self.training_metrics and
                    'precision' in self.validation_metrics and 'recall' in self.validation_metrics):

                    ax2 = plt.subplot(1, 2, 2)
                    ax2.plot(self.training_metrics['recall'], self.training_metrics['precision'],
                            label=f'Training (AP = {self.training_metrics["average_precision"]:.3f})', linewidth=2)
                    ax2.plot(self.validation_metrics['recall'], self.validation_metrics['precision'],
                            label=f'Validation (AP = {self.validation_metrics["average_precision"]:.3f})', linewidth=2)
                    ax2.set_xlabel('Recall')
                    ax2.set_ylabel('Precision')
                    ax2.set_title('Precision-Recall Curves')
                    ax2.legend()
                    ax2.grid(True, alpha=0.3)

                plt.tight_layout()
                plots['performance_curves'] = fig3

        except Exception as e:
            print(f"Warning: Error creating plots: {e}")

        return plots

    def compare_with_baseline(self, baseline_results: 'WeightedCorrelationAnalysisResults') -> Dict:
        """
        Compare this analysis with baseline results

        Args:
            baseline_results: Another WeightedCorrelationAnalysisResults to compare against

        Returns:
            Dictionary with comparison metrics
        """
        comparison = {}

        # Performance comparison
        comparison['performance'] = {
            'auc_improvement': self.validation_metrics.get('auc', 0) - baseline_results.validation_metrics.get('auc', 0),
            'ap_improvement': self.validation_metrics.get('average_precision', 0) - baseline_results.validation_metrics.get('average_precision', 0)
        }

        # Weight analysis comparison
        if self.weights_dataframe is not None and baseline_results.weights_dataframe is not None:
            # Weight correlation
            common_conditions = set(self.weights_dataframe['condition']) & set(baseline_results.weights_dataframe['condition'])
            if common_conditions:
                self_weights = self.weights_dataframe.set_index('condition').loc[list(common_conditions), 'weight']
                baseline_weights = baseline_results.weights_dataframe.set_index('condition').loc[list(common_conditions), 'weight']
                weight_correlation = np.corrcoef(self_weights, baseline_weights)[0, 1]
                comparison['weight_correlation'] = weight_correlation

            # Entropy comparison
            comparison['entropy_difference'] = self._calculate_weight_entropy() - baseline_results._calculate_weight_entropy()

        return comparison

class ProteomicsAutoencoderResults(AnalysisResults):
    """
    Specialized class for bidirectional autoencoder analysis results
    """

    def __init__(self, results_dict: Dict, original_data: pd.DataFrame = None,
                 model: torch.nn.Module = None, dataset = None):
        """
        Initialize proteomics autoencoder analysis results

        Args:
            results_dict: Results from analyze_proteomics_data function
            original_data: Original proteomics data used in analysis
            model: Trained autoencoder model
            dataset: ProteomicsDataset used for training
        """
        super().__init__(
            results_dict=results_dict,
            analysis_type="Proteomics Bidirectional Autoencoder Analysis",
            metadata=results_dict.get('config', {})
        )

        self.original_data = original_data
        self.trained_model = model or results_dict.get('model')
        self.dataset = dataset or results_dict.get('dataset')

        # Extract key components for easy access
        self.training_history = results_dict.get('training_history', {})
        self.similarity_matrix = results_dict.get('similarity_matrix')
        self.relationship_analysis = results_dict.get('relationship_analysis', {})
        self.embeddings = results_dict.get('embeddings')
        self.reconstruction_results = results_dict.get('reconstruction_results', {})
        self.config = results_dict.get('config', {})

        # Model architecture info
        self.architecture_info = self._extract_architecture_info()

        # Performance metrics
        self.performance_metrics = self._calculate_performance_metrics()

    def _extract_architecture_info(self) -> Dict:
        """Extract architecture information from model"""
        if self.trained_model is None:
            return {}

        try:
            arch_info = {}

            if hasattr(self.trained_model, 'n_proteins'):
                arch_info['n_proteins'] = self.trained_model.n_proteins
            if hasattr(self.trained_model, 'n_samples'):
                arch_info['n_samples'] = self.trained_model.n_samples
            if hasattr(self.trained_model, 'protein_embedding_dim'):
                arch_info['protein_embedding_dim'] = self.trained_model.protein_embedding_dim
            if hasattr(self.trained_model, 'sample_embedding_dim'):
                arch_info['sample_embedding_dim'] = self.trained_model.sample_embedding_dim

            # Count parameters
            if hasattr(self.trained_model, 'parameters'):
                total_params = sum(p.numel() for p in self.trained_model.parameters())
                trainable_params = sum(p.numel() for p in self.trained_model.parameters() if p.requires_grad)
                arch_info['total_parameters'] = total_params
                arch_info['trainable_parameters'] = trainable_params

            return arch_info

        except Exception as e:
            return {'error': f'Could not extract architecture info: {e}'}

    def _calculate_performance_metrics(self) -> Dict:
        """Calculate comprehensive performance metrics"""
        metrics = {}

        # Training metrics
        if self.training_history:
            train_losses = self.training_history.get('train_losses', [])
            if train_losses:
                metrics['final_train_loss'] = train_losses[-1]
                metrics['initial_train_loss'] = train_losses[0]
                metrics['loss_reduction'] = train_losses[0] - train_losses[-1]
                metrics['loss_reduction_percent'] = ((train_losses[0] - train_losses[-1]) / train_losses[0]) * 100
                metrics['training_epochs'] = len(train_losses)

                # Training stability
                if len(train_losses) > 10:
                    recent_losses = train_losses[-10:]
                    metrics['training_stability'] = np.std(recent_losses) / np.mean(recent_losses)

        # Reconstruction metrics
        if self.reconstruction_results:
            if 'reconstruction_error' in self.reconstruction_results:
                recon_error = self.reconstruction_results['reconstruction_error']
                metrics['reconstruction_mse'] = recon_error.get('mse', 0)
                metrics['reconstruction_mae'] = recon_error.get('mae', 0)

        # Similarity analysis metrics
        if self.relationship_analysis:
            stats = self.relationship_analysis.get('statistics', {})
            metrics['n_similar_pairs'] = stats.get('n_similar_pairs', 0)
            metrics['mean_similarity'] = stats.get('mean_similarity', 0)
            metrics['similarity_threshold'] = stats.get('threshold_used', 0)

        # Data coverage
        if self.original_data is not None and self.dataset is not None:
            if hasattr(self.dataset, 'n_proteins') and hasattr(self.dataset, 'n_samples'):
                metrics['data_proteins'] = self.dataset.n_proteins
                metrics['data_samples'] = self.dataset.n_samples
                metrics['data_completeness'] = (self.dataset.n_proteins * self.dataset.n_samples) / self.original_data.size

        return metrics

    def get_summary_stats(self) -> Dict:
        """Get comprehensive summary statistics"""
        base_stats = super().get_summary_stats()

        # Architecture information
        arch_stats = {}
        if self.architecture_info:
            arch_stats = {
                'protein_embedding_dim': self.architecture_info.get('protein_embedding_dim', 'N/A'),
                'sample_embedding_dim': self.architecture_info.get('sample_embedding_dim', 'N/A'),
                'total_parameters': self.architecture_info.get('total_parameters', 'N/A'),
                'n_proteins': self.architecture_info.get('n_proteins', 'N/A'),
                'n_samples': self.architecture_info.get('n_samples', 'N/A')
            }

        # Performance statistics
        perf_stats = {}
        if self.performance_metrics:
            perf_stats = {
                'final_loss': self.performance_metrics.get('final_train_loss', 'N/A'),
                'loss_reduction_percent': f"{self.performance_metrics.get('loss_reduction_percent', 0):.1f}%",
                'training_epochs': self.performance_metrics.get('training_epochs', 'N/A'),
                'reconstruction_quality': self._assess_reconstruction_quality(),
                'embedding_quality': self._assess_embedding_quality()
            }

        return {
            **base_stats,
            **arch_stats,
            **perf_stats
        }

    def _assess_reconstruction_quality(self) -> str:
        """Assess reconstruction quality based on error metrics"""
        if 'reconstruction_mse' not in self.performance_metrics:
            return "Unknown"

        mse = self.performance_metrics['reconstruction_mse']

        # These thresholds would need to be calibrated based on your data scale
        if mse < 0.01:
            return "Excellent"
        elif mse < 0.05:
            return "Good"
        elif mse < 0.1:
            return "Fair"
        elif mse < 0.2:
            return "Poor"
        else:
            return "Very Poor"

    def _assess_embedding_quality(self) -> str:
        """Assess embedding quality based on similarity analysis"""
        if not self.relationship_analysis or 'statistics' not in self.relationship_analysis:
            return "Unknown"

        n_similar = self.relationship_analysis['statistics'].get('n_similar_pairs', 0)
        mean_sim = self.relationship_analysis['statistics'].get('mean_similarity', 0)

        if n_similar > 50 and mean_sim > 0.7:
            return "Excellent"
        elif n_similar > 20 and mean_sim > 0.6:
            return "Good"
        elif n_similar > 10 and mean_sim > 0.5:
            return "Fair"
        elif n_similar > 5:
            return "Poor"
        else:
            return "Very Poor"

    def get_training_convergence_analysis(self) -> Dict:
        """Analyze training convergence patterns"""
        if not self.training_history or 'train_losses' not in self.training_history:
            return {}

        losses = self.training_history['train_losses']
        if len(losses) < 10:
            return {'status': 'Insufficient training data'}

        analysis = {}

        # Convergence detection
        recent_window = min(20, len(losses) // 4)
        recent_losses = losses[-recent_window:]
        early_losses = losses[:recent_window]

        # Calculate convergence metrics
        recent_trend = np.polyfit(range(len(recent_losses)), recent_losses, 1)[0]
        recent_variance = np.var(recent_losses)

        analysis['converged'] = abs(recent_trend) < 0.001 and recent_variance < 0.001
        analysis['trend_slope'] = recent_trend
        analysis['recent_variance'] = recent_variance
        analysis['improvement_rate'] = (early_losses[0] - recent_losses[-1]) / len(losses)

        # Identify potential issues
        issues = []
        if recent_trend > 0.001:
            issues.append("Loss still decreasing - may need more training")
        if recent_variance > 0.01:
            issues.append("High variance in recent losses - unstable training")
        if len(losses) > 100 and analysis['improvement_rate'] < 0.001:
            issues.append("Slow improvement rate - may be overfitting or poor initialization")

        analysis['potential_issues'] = issues

        return analysis

    def get_embedding_statistics(self) -> Dict:
        """Get statistics about learned embeddings"""
        if self.embeddings is None:
            return {}

        stats = {}

        try:
            # Convert to numpy if tensor
            if hasattr(self.embeddings, 'numpy'):
                emb_array = self.embeddings.numpy()
            elif isinstance(self.embeddings, np.ndarray):
                emb_array = self.embeddings
            else:
                return {'error': 'Unknown embedding format'}

            # Basic statistics
            stats['embedding_shape'] = emb_array.shape
            stats['mean_embedding_norm'] = np.mean(np.linalg.norm(emb_array, axis=1))
            stats['std_embedding_norm'] = np.std(np.linalg.norm(emb_array, axis=1))
            stats['max_embedding_value'] = np.max(emb_array)
            stats['min_embedding_value'] = np.min(emb_array)

            # Dimensionality analysis
            if emb_array.shape[1] > 1:
                # PCA to estimate effective dimensionality
                from sklearn.decomposition import PCA
                pca = PCA()
                pca.fit(emb_array)

                # Find number of components explaining 95% variance
                cumvar = np.cumsum(pca.explained_variance_ratio_)
                effective_dim = np.argmax(cumvar >= 0.95) + 1

                stats['effective_dimensionality'] = effective_dim
                stats['explained_variance_95'] = cumvar[effective_dim-1]
                stats['top_3_pc_variance'] = np.sum(pca.explained_variance_ratio_[:3])

        except Exception as e:
            stats['error'] = f'Error calculating embedding statistics: {e}'

        return stats

    def get_top_similar_proteins(self, n: int = 10) -> pd.DataFrame:
        """Get top N most similar protein pairs"""
        if not self.relationship_analysis or 'top_similar_pairs' not in self.relationship_analysis:
            return pd.DataFrame()

        similar_pairs = self.relationship_analysis['top_similar_pairs'][:n]

        df_data = []
        for pair in similar_pairs:
            df_data.append({
                'protein1': pair['protein1'],
                'protein2': pair['protein2'],
                'similarity': pair['similarity']
            })

        return pd.DataFrame(df_data)

    def _generate_detailed_text(self) -> List[str]:
        """Generate detailed text representation"""
        lines = []

        # Architecture Section
        lines.append("MODEL ARCHITECTURE:")
        if self.architecture_info:
            for key, value in self.architecture_info.items():
                if key != 'error':
                    display_key = key.replace('_', ' ').title()
                    lines.append(f"  {display_key}: {value}")
        lines.append("")

        # Training Performance
        lines.append("TRAINING PERFORMANCE:")
        if self.performance_metrics:
            lines.append(f"  Final Training Loss: {self.performance_metrics.get('final_train_loss', 'N/A'):.6f}")
            lines.append(f"  Loss Reduction: {self.performance_metrics.get('loss_reduction_percent', 0):.2f}%")
            lines.append(f"  Training Epochs: {self.performance_metrics.get('training_epochs', 'N/A')}")
            lines.append(f"  Reconstruction Quality: {self._assess_reconstruction_quality()}")

            if 'reconstruction_mse' in self.performance_metrics:
                lines.append(f"  Reconstruction MSE: {self.performance_metrics['reconstruction_mse']:.6f}")
            if 'reconstruction_mae' in self.performance_metrics:
                lines.append(f"  Reconstruction MAE: {self.performance_metrics['reconstruction_mae']:.6f}")
        lines.append("")

        # Convergence Analysis
        convergence = self.get_training_convergence_analysis()
        if convergence:
            lines.append("TRAINING CONVERGENCE:")
            lines.append(f"  Converged: {convergence.get('converged', 'Unknown')}")
            lines.append(f"  Recent Trend: {convergence.get('trend_slope', 0):.6f}")
            lines.append(f"  Recent Variance: {convergence.get('recent_variance', 0):.6f}")

            issues = convergence.get('potential_issues', [])
            if issues:
                lines.append("  Potential Issues:")
                for issue in issues:
                    lines.append(f"    - {issue}")
            lines.append("")

        # Embedding Analysis
        emb_stats = self.get_embedding_statistics()
        if emb_stats and 'error' not in emb_stats:
            lines.append("EMBEDDING ANALYSIS:")
            lines.append(f"  Embedding Shape: {emb_stats.get('embedding_shape', 'N/A')}")
            lines.append(f"  Mean Norm: {emb_stats.get('mean_embedding_norm', 0):.4f}")
            lines.append(f"  Effective Dimensionality: {emb_stats.get('effective_dimensionality', 'N/A')}")
            lines.append(f"  Top 3 PC Variance: {emb_stats.get('top_3_pc_variance', 0):.2%}")
            lines.append("")

        # Similarity Analysis
        if self.relationship_analysis and 'statistics' in self.relationship_analysis:
            stats = self.relationship_analysis['statistics']
            lines.append("PROTEIN SIMILARITY ANALYSIS:")
            lines.append(f"  Similar Pairs Found: {stats.get('n_similar_pairs', 0)}")
            lines.append(f"  Mean Similarity: {stats.get('mean_similarity', 0):.4f}")
            lines.append(f"  Similarity Threshold: {stats.get('threshold_used', 0):.4f}")
            lines.append(f"  Embedding Quality: {self._assess_embedding_quality()}")
            lines.append("")

            # Top similar pairs
            top_pairs = self.get_top_similar_proteins(5)
            if not top_pairs.empty:
                lines.append("TOP 5 SIMILAR PROTEIN PAIRS:")
                for idx, row in top_pairs.iterrows():
                    lines.append(f"  {row['protein1']} - {row['protein2']}: {row['similarity']:.4f}")
                lines.append("")

        # Configuration
        lines.append("CONFIGURATION:")
        for key, value in self.config.items():
            display_key = key.replace('_', ' ').title()
            lines.append(f"  {display_key}: {value}")
        lines.append("")

        return lines

    def _generate_detailed_html(self) -> str:
        """Generate detailed HTML representation"""
        html_parts = []

        # Architecture Information
        if self.architecture_info:
            html_parts.append('<h3>Model Architecture</h3>')
            html_parts.append('<table class="results-table">')
            html_parts.append('<tr><th>Component</th><th>Value</th><th>Description</th></tr>')

            arch_descriptions = {
                'n_proteins': 'Number of proteins in dataset',
                'n_samples': 'Number of experimental conditions',
                'protein_embedding_dim': 'Dimensionality of protein embeddings',
                'sample_embedding_dim': 'Dimensionality of sample embeddings',
                'total_parameters': 'Total model parameters',
                'trainable_parameters': 'Trainable model parameters'
            }

            for key, value in self.architecture_info.items():
                if key != 'error':
                    description = arch_descriptions.get(key, '')
                    display_key = key.replace('_', ' ').title()
                    html_parts.append(f'<tr><td>{display_key}</td><td>{value}</td><td>{description}</td></tr>')

            html_parts.append('</table>')

        # Training Performance
        html_parts.append('<h3>Training Performance</h3>')
        html_parts.append('<table class="results-table">')
        html_parts.append('<tr><th>Metric</th><th>Value</th><th>Assessment</th></tr>')

        if self.performance_metrics:
            final_loss = self.performance_metrics.get('final_train_loss', 0)
            loss_reduction = self.performance_metrics.get('loss_reduction_percent', 0)
            reconstruction_quality = self._assess_reconstruction_quality()
            embedding_quality = self._assess_embedding_quality()

            # Determine CSS classes for assessments
            recon_class = self._get_quality_css_class(reconstruction_quality)
            emb_class = self._get_quality_css_class(embedding_quality)

            html_parts.append(f'<tr><td>Final Training Loss</td><td>{final_loss:.6f}</td><td>-</td></tr>')
            html_parts.append(f'<tr><td>Loss Reduction</td><td>{loss_reduction:.2f}%</td><td>{"Good" if loss_reduction > 50 else "Poor"}</td></tr>')
            html_parts.append(f'<tr><td>Reconstruction Quality</td><td>-</td><td class="{recon_class}">{reconstruction_quality}</td></tr>')
            html_parts.append(f'<tr><td>Embedding Quality</td><td>-</td><td class="{emb_class}">{embedding_quality}</td></tr>')

            if 'reconstruction_mse' in self.performance_metrics:
                mse = self.performance_metrics['reconstruction_mse']
                html_parts.append(f'<tr><td>Reconstruction MSE</td><td>{mse:.6f}</td><td>-</td></tr>')

        html_parts.append('</table>')

        # Convergence Analysis
        convergence = self.get_training_convergence_analysis()
        if convergence and 'status' not in convergence:
            html_parts.append('<h3>Training Convergence Analysis</h3>')
            html_parts.append('<table class="results-table">')
            html_parts.append('<tr><th>Metric</th><th>Value</th><th>Interpretation</th></tr>')

            converged = convergence.get('converged', False)
            converged_class = "metric-good" if converged else "metric-warning"

            html_parts.append(f'<tr><td>Converged</td><td class="{converged_class}">{converged}</td><td>{"Training has stabilized" if converged else "May need more training"}</td></tr>')
            html_parts.append(f'<tr><td>Recent Trend</td><td>{convergence.get("trend_slope", 0):.6f}</td><td>{"Still improving" if convergence.get("trend_slope", 0) < -0.001 else "Plateaued"}</td></tr>')
            html_parts.append(f'<tr><td>Recent Variance</td><td>{convergence.get("recent_variance", 0):.6f}</td><td>{"Stable" if convergence.get("recent_variance", 0) < 0.01 else "Unstable"}</td></tr>')

            html_parts.append('</table>')

            # Issues
            issues = convergence.get('potential_issues', [])
            if issues:
                html_parts.append('<h4>Potential Issues</h4>')
                html_parts.append('<ul>')
                for issue in issues:
                    html_parts.append(f'<li>{issue}</li>')
                html_parts.append('</ul>')

        # Embedding Statistics
        emb_stats = self.get_embedding_statistics()
        if emb_stats and 'error' not in emb_stats:
            html_parts.append('<h3>Embedding Analysis</h3>')
            html_parts.append('<table class="results-table">')
            html_parts.append('<tr><th>Statistic</th><th>Value</th><th>Interpretation</th></tr>')

            shape = emb_stats.get('embedding_shape', (0, 0))
            effective_dim = emb_stats.get('effective_dimensionality', 0)
            variance_3pc = emb_stats.get('top_3_pc_variance', 0)

            html_parts.append(f'<tr><td>Embedding Shape</td><td>{shape}</td><td>{shape[0]} proteins, {shape[1]} dimensions</td></tr>')
            html_parts.append(f'<tr><td>Mean Norm</td><td>{emb_stats.get("mean_embedding_norm", 0):.4f}</td><td>Average embedding magnitude</td></tr>')
            html_parts.append(f'<tr><td>Effective Dimensionality</td><td>{effective_dim}</td><td>Dimensions explaining 95% variance</td></tr>')
            html_parts.append(f'<tr><td>Top 3 PC Variance</td><td>{variance_3pc:.2%}</td><td>Variance in top 3 components</td></tr>')

            html_parts.append('</table>')

        # Top Similar Proteins
        top_pairs = self.get_top_similar_proteins(10)
        if not top_pairs.empty:
            html_parts.append('<h3>Top Similar Protein Pairs</h3>')
            html_parts.append('<table class="results-table">')
            html_parts.append('<tr><th>Rank</th><th>Protein 1</th><th>Protein 2</th><th>Similarity</th></tr>')

            for idx, row in top_pairs.iterrows():
                html_parts.append(f'<tr><td>{idx + 1}</td><td>{row["protein1"]}</td><td>{row["protein2"]}</td><td>{row["similarity"]:.4f}</td></tr>')

            html_parts.append('</table>')

        # Configuration
        html_parts.append('<div class="config-section">')
        html_parts.append('<h3>Configuration</h3>')
        html_parts.append('<table class="results-table">')
        html_parts.append('<tr><th>Parameter</th><th>Value</th></tr>')

        for key, value in self.config.items():
            display_key = key.replace('_', ' ').title()
            html_parts.append(f'<tr><td>{display_key}</td><td>{value}</td></tr>')

        html_parts.append('</table>')
        html_parts.append('</div>')

        return '\n'.join(html_parts)

    def _get_quality_css_class(self, quality_str: str) -> str:
        """Get CSS class based on quality assessment"""
        quality_lower = quality_str.lower()
        if quality_lower in ['excellent', 'good']:
            return 'metric-good'
        elif quality_lower in ['fair']:
            return 'metric-warning'
        else:
            return 'metric-poor'

    def _generate_plots_html(self, plot_format: str = 'png', **plot_kwargs) -> str:
        """Generate plots HTML with embedded images"""
        html_parts = []

        try:
            plots = self.create_plots(**plot_kwargs)

            for plot_name, fig in plots.items():
                if fig is not None:
                    img_str = self._fig_to_base64(fig, format=plot_format)

                    html_parts.append(f'<div class="plot-container">')
                    html_parts.append(f'<div class="plot-title">{plot_name.replace("_", " ").title()}</div>')
                    html_parts.append(f'<img src="data:image/{plot_format};base64,{img_str}" alt="{plot_name}" style="max-width: 100%; height: auto;">')
                    html_parts.append('</div>')

                    plt.close(fig)

        except Exception as e:
            html_parts.append(f'<p class="error">Error generating plots: {str(e)}</p>')

        return '\n'.join(html_parts)

    def create_plots(self, figsize: Tuple[int, int] = (16, 12), **kwargs) -> Dict:
        """
        Create visualization plots for autoencoder analysis

        Args:
            figsize: Figure size for plots
            **kwargs: Additional plotting parameters

        Returns:
            Dictionary of plot names to figure objects
        """
        plots = {}

        try:
            # 1. Training Progress
            if self.training_history and 'train_losses' in self.training_history:
                fig1 = plt.figure(figsize=(14, 10))

                train_losses = self.training_history['train_losses']
                val_losses = self.training_history.get('val_losses', [])

                # Loss curves
                ax1 = plt.subplot(2, 3, 1)
                ax1.plot(train_losses, label='Training Loss', linewidth=2)
                if val_losses:
                    ax1.plot(val_losses, label='Validation Loss', linewidth=2)
                ax1.set_xlabel('Epoch')
                ax1.set_ylabel('Loss')
                ax1.set_title('Training Progress')
                ax1.legend()
                ax1.grid(True, alpha=0.3)

                # Loss distribution (recent epochs)
                ax2 = plt.subplot(2, 3, 2)
                recent_losses = train_losses[-20:] if len(train_losses) >= 20 else train_losses
                ax2.hist(recent_losses, bins=15, alpha=0.7, edgecolor='black')
                ax2.set_xlabel('Loss Value')
                ax2.set_ylabel('Frequency')
                ax2.set_title('Recent Loss Distribution')
                ax2.grid(True, alpha=0.3)

                # Loss improvement rate
                ax3 = plt.subplot(2, 3, 3)
                if len(train_losses) > 10:
                    # Calculate moving average of improvement
                    window = min(10, len(train_losses) // 4)
                    improvements = []
                    for i in range(window, len(train_losses)):
                        recent_avg = np.mean(train_losses[i-window:i])
                        prev_avg = np.mean(train_losses[i-2*window:i-window]) if i >= 2*window else train_losses[0]
                        improvement = prev_avg - recent_avg
                        improvements.append(improvement)

                    ax3.plot(range(window, len(train_losses)), improvements, linewidth=2)
                    ax3.set_xlabel('Epoch')
                    ax3.set_ylabel('Loss Improvement Rate')
                    ax3.set_title('Training Improvement Rate')
                    ax3.grid(True, alpha=0.3)
                    ax3.axhline(y=0, color='r', linestyle='--', alpha=0.5)

                # Convergence analysis
                ax4 = plt.subplot(2, 3, 4)
                convergence = self.get_training_convergence_analysis()
                if convergence and 'converged' in convergence:
                    # Plot recent variance
                    if len(train_losses) > 20:
                        window_size = 10
                        variances = []
                        epochs = []
                        for i in range(window_size, len(train_losses)):
                            window_losses = train_losses[i-window_size:i]
                            variances.append(np.var(window_losses))
                            epochs.append(i)

                        ax4.plot(epochs, variances, linewidth=2, color='orange')
                        ax4.set_xlabel('Epoch')
                        ax4.set_ylabel('Windowed Loss Variance')
                        ax4.set_title('Training Stability')
                        ax4.grid(True, alpha=0.3)

                # Training summary
                ax5 = plt.subplot(2, 3, 5)
                ax5.axis('off')

                # Create summary text
                summary_text = f"""Training Summary:

Final Loss: {train_losses[-1]:.6f}
Initial Loss: {train_losses[0]:.6f}
Improvement: {((train_losses[0] - train_losses[-1]) / train_losses[0] * 100):.1f}%
Epochs: {len(train_losses)}

Convergence: {convergence.get('converged', 'Unknown') if convergence else 'Unknown'}
Assessment: {self._assess_reconstruction_quality()}
                """

                ax5.text(0.1, 0.9, summary_text, transform=ax5.transAxes, fontsize=10,
                        verticalalignment='top',
                        bbox=dict(boxstyle='round', facecolor='lightblue', alpha=0.8))

                plt.tight_layout()
                plots['training_analysis'] = fig1

            # 2. Similarity Analysis
            if self.similarity_matrix is not None:
                fig2 = plt.figure(figsize=(14, 10))

                # Similarity matrix heatmap
                ax1 = plt.subplot(2, 3, 1)

                # Sample for visualization if too large
                if len(self.similarity_matrix) > 100:
                    sample_indices = np.random.choice(len(self.similarity_matrix), 100, replace=False)
                    plot_matrix = self.similarity_matrix.iloc[sample_indices, sample_indices]
                    title_suffix = " (100 random proteins)"
                else:
                    plot_matrix = self.similarity_matrix
                    title_suffix = ""

                sns.heatmap(plot_matrix, cmap='viridis', square=True,
                           cbar_kws={'label': 'Similarity'}, ax=ax1)
                ax1.set_title(f'Protein Similarity Matrix{title_suffix}')

                # Similarity distribution
                ax2 = plt.subplot(2, 3, 2)
                similarity_values = self.similarity_matrix.values
                # Remove diagonal and get upper triangle
                mask = np.triu(np.ones_like(similarity_values, dtype=bool), k=1)
                sim_values = similarity_values[mask]

                ax2.hist(sim_values, bins=50, alpha=0.7, edgecolor='black')
                ax2.axvline(np.mean(sim_values), color='red', linestyle='--',
                           label=f'Mean: {np.mean(sim_values):.3f}')
                ax2.set_xlabel('Similarity')
                ax2.set_ylabel('Frequency')
                ax2.set_title('Similarity Distribution')
                ax2.legend()
                ax2.grid(True, alpha=0.3)

                # Top similarities
                ax3 = plt.subplot(2, 3, 3)
                top_pairs = self.get_top_similar_proteins(15)
                if not top_pairs.empty:
                    y_pos = range(len(top_pairs))
                    similarities = top_pairs['similarity'].values

                    bars = ax3.barh(y_pos, similarities, alpha=0.7)
                    ax3.set_yticks(y_pos)
                    ax3.set_yticklabels([f"{row['protein1']}-{row['protein2']}"[:20] for _, row in top_pairs.iterrows()],
                                      fontsize=8)
                    ax3.set_xlabel('Similarity')
                    ax3.set_title('Top Similar Protein Pairs')
                    ax3.grid(True, alpha=0.3, axis='x')

                # Clustering visualization (if possible)
                ax4 = plt.subplot(2, 3, 4)
                try:
                    from sklearn.cluster import KMeans
                    from sklearn.manifold import TSNE

                    # Use embeddings if available, otherwise similarity matrix
                    if self.embeddings is not None:
                        if hasattr(self.embeddings, 'numpy'):
                            emb_data = self.embeddings.numpy()
                        else:
                            emb_data = self.embeddings

                        if len(emb_data) <= 500:  # Only for manageable sizes
                            # Cluster embeddings
                            n_clusters = min(8, len(emb_data) // 10)
                            if n_clusters >= 2:
                                kmeans = KMeans(n_clusters=n_clusters, random_state=42)
                                clusters = kmeans.fit_predict(emb_data)

                                # Use t-SNE for 2D visualization
                                if emb_data.shape[1] > 2:
                                    tsne = TSNE(n_components=2, random_state=42)
                                    emb_2d = tsne.fit_transform(emb_data[:200])  # Limit for t-SNE
                                    clusters_2d = clusters[:200]
                                else:
                                    emb_2d = emb_data
                                    clusters_2d = clusters

                                scatter = ax4.scatter(emb_2d[:, 0], emb_2d[:, 1],
                                                    c=clusters_2d, cmap='tab10', alpha=0.6)
                                ax4.set_title('Protein Clustering (t-SNE)')
                                ax4.set_xlabel('t-SNE 1')
                                ax4.set_ylabel('t-SNE 2')

                except ImportError:
                    ax4.text(0.5, 0.5, 'Clustering visualization\nrequires scikit-learn',
                            ha='center', va='center', transform=ax4.transAxes)
                except Exception:
                    ax4.text(0.5, 0.5, 'Clustering visualization\nnot available',
                            ha='center', va='center', transform=ax4.transAxes)

                ax4.set_title('Protein Clustering')

                plt.tight_layout()
                plots['similarity_analysis'] = fig2

            # 3. Embedding Analysis
            if self.embeddings is not None:
                fig3 = plt.figure(figsize=(12, 8))

                # Convert to numpy
                if hasattr(self.embeddings, 'numpy'):
                    emb_array = self.embeddings.numpy()
                else:
                    emb_array = self.embeddings

                # Embedding norms distribution
                ax1 = plt.subplot(2, 3, 1)
                norms = np.linalg.norm(emb_array, axis=1)
                ax1.hist(norms, bins=30, alpha=0.7, edgecolor='black')
                ax1.axvline(np.mean(norms), color='red', linestyle='--',
                           label=f'Mean: {np.mean(norms):.3f}')
                ax1.set_xlabel('Embedding Norm')
                ax1.set_ylabel('Frequency')
                ax1.set_title('Embedding Magnitude Distribution')
                ax1.legend()
                ax1.grid(True, alpha=0.3)

                # Dimension-wise statistics
                ax2 = plt.subplot(2, 3, 2)
                dim_means = np.mean(emb_array, axis=0)
                dim_stds = np.std(emb_array, axis=0)

                ax2.errorbar(range(len(dim_means)), dim_means, yerr=dim_stds,
                           capsize=3, alpha=0.7)
                ax2.set_xlabel('Embedding Dimension')
                ax2.set_ylabel('Mean ± Std')
                ax2.set_title('Per-Dimension Statistics')
                ax2.grid(True, alpha=0.3)

                # PCA analysis
                ax3 = plt.subplot(2, 3, 3)
                try:
                    from sklearn.decomposition import PCA
                    pca = PCA()
                    pca.fit(emb_array)

                    # Plot explained variance
                    cumvar = np.cumsum(pca.explained_variance_ratio_)
                    ax3.plot(range(1, len(cumvar) + 1), cumvar, 'bo-', linewidth=2)
                    ax3.axhline(y=0.95, color='red', linestyle='--', alpha=0.7, label='95% variance')
                    ax3.set_xlabel('Number of Components')
                    ax3.set_ylabel('Cumulative Explained Variance')
                    ax3.set_title('PCA Analysis')
                    ax3.legend()
                    ax3.grid(True, alpha=0.3)

                except ImportError:
                    ax3.text(0.5, 0.5, 'PCA analysis requires\nscikit-learn',
                            ha='center', va='center', transform=ax3.transAxes)

                # Embedding statistics summary
                ax4 = plt.subplot(2, 3, (4, 6))
                ax4.axis('off')

                emb_stats = self.get_embedding_statistics()
                stats_text = f"""Embedding Statistics:

Shape: {emb_stats.get('embedding_shape', 'N/A')}
Mean Norm: {emb_stats.get('mean_embedding_norm', 0):.4f}
Std Norm: {emb_stats.get('std_embedding_norm', 0):.4f}
Value Range: [{emb_stats.get('min_embedding_value', 0):.3f}, {emb_stats.get('max_embedding_value', 0):.3f}]

Effective Dimensionality: {emb_stats.get('effective_dimensionality', 'N/A')}
Top 3 PC Variance: {emb_stats.get('top_3_pc_variance', 0):.2%}

Quality Assessment: {self._assess_embedding_quality()}
                """

                ax4.text(0.05, 0.95, stats_text, transform=ax4.transAxes, fontsize=11,
                        verticalalignment='top',
                        bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.8))

                plt.tight_layout()
                plots['embedding_analysis'] = fig3

        except Exception as e:
            print(f"Warning: Error creating plots: {e}")

        return plots

    def export_embeddings(self, filepath: str, format: str = 'csv'):
        """
        Export learned embeddings to file

        Args:
            filepath: Path to save embeddings
            format: Format to save ('csv', 'npy', 'pkl')
        """
        if self.embeddings is None:
            raise ValueError("No embeddings available to export")

        # Convert to numpy if needed
        if hasattr(self.embeddings, 'numpy'):
            emb_array = self.embeddings.numpy()
        else:
            emb_array = self.embeddings

        if format == 'csv':
            # Create DataFrame with protein names if available
            if self.original_data is not None:
                protein_names = self.original_data.index.tolist()[:len(emb_array)]
            else:
                protein_names = [f'Protein_{i}' for i in range(len(emb_array))]

            columns = [f'dim_{i}' for i in range(emb_array.shape[1])]
            emb_df = pd.DataFrame(emb_array, index=protein_names, columns=columns)
            emb_df.to_csv(filepath)

        elif format == 'npy':
            np.save(filepath, emb_array)

        elif format == 'pkl':
            import pickle
            with open(filepath, 'wb') as f:
                pickle.dump(emb_array, f)

        else:
            raise ValueError(f"Unsupported format: {format}")

# Example usage and testing
if __name__ == "__main__":
    # Create sample autoencoder results (mimicking output from analyze_proteomics_data)
    np.random.seed(42)

    # Sample embeddings
    n_proteins, embedding_dim = 150, 64
    sample_embeddings = np.random.randn(n_proteins, embedding_dim)

    # Sample similarity matrix
    similarity_matrix = np.random.rand(n_proteins, n_proteins)
    similarity_matrix = (similarity_matrix + similarity_matrix.T) / 2
    np.fill_diagonal(similarity_matrix, 1.0)

    protein_names = [f'Protein_{i:03d}' for i in range(n_proteins)]
    sim_df = pd.DataFrame(similarity_matrix, index=protein_names, columns=protein_names)

    # Create sample autoencoder results
    sample_results = {
        'model': {'type': 'BiDirectionalAutoencoder'},
        'embeddings': sample_embeddings,
        'similarity_matrix': sim_df,
        'training_history': {
            'train_losses': [1.5 * np.exp(-i/50) + 0.1 + 0.02*np.random.randn() for i in range(200)],
            'val_losses': [1.6 * np.exp(-i/45) + 0.12 + 0.02*np.random.randn() for i in range(0, 200, 10)]
        },
        'relationship_analysis': {
            'statistics': {
                'n_similar_pairs': 45,
                'mean_similarity': 0.72,
                'threshold_used': 0.6
            },
            'top_similar_pairs': [
                {'protein1': f'Protein_{i:03d}', 'protein2': f'Protein_{i+1:03d}', 'similarity': 0.9 - 0.1*i/10}
                for i in range(15)
            ]
        },
        'reconstruction_results': {
            'reconstruction_error': {
                'mse': 0.045,
                'mae': 0.012
            }
        },
        'config': {
            'protein_embedding_dim': embedding_dim,
            'sample_embedding_dim': 32,
            'hidden_dims': [256, 128],
            'epochs': 200,
            'learning_rate': 0.001,
            'correlation_method': 'pearson'
        }
    }

    # Sample original data
    sample_data = pd.DataFrame(
        np.random.randn(n_proteins, 30),
        index=protein_names,
        columns=[f'Condition_{i}' for i in range(30)]
    )

    print("Testing ProteomicsAutoencoderResults class...")

    # Create results object
    results = ProteomicsAutoencoderResults(
        results_dict=sample_results,
        original_data=sample_data
    )

    # Test summary stats
    print("\n" + "="*60)
    print("SUMMARY STATS:")
    print("="*60)
    summary = results.get_summary_stats()
    for key, value in summary.items():
        print(f"{key}: {value}")

    # Test text output
    print("\n" + "="*60)
    print("TEXT OUTPUT (first 1000 chars):")
    print("="*60)
    text_output = results.to_text()
    print(text_output[:1000] + "..." if len(text_output) > 1000 else text_output)

    # Test specific analysis methods
    print("\n" + "="*60)
    print("SPECIFIC ANALYSES:")
    print("="*60)

    convergence = results.get_training_convergence_analysis()
    print(f"Convergence analysis: {convergence}")

    emb_stats = results.get_embedding_statistics()
    print(f"Embedding stats keys: {list(emb_stats.keys())}")

    top_pairs = results.get_top_similar_proteins(5)
    print(f"Top similar pairs:\n{top_pairs}")

    # Test HTML output
    print("\n" + "="*60)
    print("HTML OUTPUT (first 500 chars):")
    print("="*60)
    html_output = results.to_html()
    print(html_output[:500] + "...")

    # Test plots
    print("\n" + "="*60)
    print("CREATING PLOTS:")
    print("="*60)
    plots = results.create_plots()
    print(f"Created {len(plots)} plots: {list(plots.keys())}")

    # Clean up
    for fig in plots.values():
        plt.close(fig)

    # Test export
    print("\n" + "="*60)
    print("TESTING EXPORT:")
    print("="*60)
    results.export_embeddings('test_embeddings.csv', format='csv')
    results.save_results('test_autoencoder_results.html', format='html')

    print("Exported embeddings and results")

    # Clean up test files
    import os
    for filename in ['test_embeddings.csv', 'test_autoencoder_results.html']:
        if os.path.exists(filename):
            os.remove(filename)

    print("\nTest completed successfully!")
