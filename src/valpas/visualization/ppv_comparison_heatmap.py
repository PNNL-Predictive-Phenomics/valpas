import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patches import Rectangle
import matplotlib.patches as mpatches
from typing import Optional, Tuple, Dict, List, Union
import warnings
warnings.filterwarnings('ignore')

def create_ppv_heatmap(
    data: pd.DataFrame,
    title: str = "Mean Positive Predictive Value for Top 1000 Predictions",
    figsize: Tuple[int, int] = (12, 8),
    colormap: str = 'custom',
    annotate: bool = True,
    annotation_format: str = '.3f',
    value_range: Tuple[float, float] = None,
    highlight_best: bool = True,
    highlight_threshold: float = None,
    save_path: Optional[str] = None,
    dpi: int = 300,
    show_colorbar: bool = True,
    font_sizes: Dict[str, int] = None,
    border_color: str = 'white',
    border_width: float = 0.5,
    round_corners: bool = False,
    add_significance_markers: bool = False,
    significance_data: pd.DataFrame = None,
    custom_colors: Dict[str, str] = None
) -> Tuple[plt.Figure, plt.Axes]:
    """
    Create a publication-quality heatmap for PPV results

    Args:
        data: DataFrame with input types as rows, association metrics as columns
        title: Title for the heatmap
        figsize: Figure size (width, height)
        colormap: Colormap to use ('custom', 'viridis', 'plasma', 'RdYlBu_r', etc.)
        annotate: Whether to show values in cells
        annotation_format: Format string for cell annotations
        value_range: Tuple of (min, max) for color scale
        highlight_best: Whether to highlight best performing cells
        highlight_threshold: Threshold above which to highlight cells
        save_path: Path to save the figure
        dpi: Resolution for saved figure
        show_colorbar: Whether to show the colorbar
        font_sizes: Dictionary with font sizes for different elements
        border_color: Color of cell borders
        border_width: Width of cell borders
        round_corners: Whether to use rounded corners (experimental)
        add_significance_markers: Whether to add significance markers
        significance_data: DataFrame with significance values (p-values)
        custom_colors: Dictionary for custom color scheme

    Returns:
        Tuple of (figure, axes) objects
    """

    # Set default font sizes
    if font_sizes is None:
        font_sizes = {
            'title': 16,
            'labels': 12,
            'ticks': 10,
            'annotations': 9,
            'colorbar': 11
        }

    # Create figure and axis
    fig, ax = plt.subplots(figsize=figsize, facecolor='white')

    # Define color scheme
    if colormap == 'custom':
        if custom_colors is None:
            # Create custom colormap (white -> light blue -> dark blue -> red)
            colors = ['#ffffff', '#e3f2fd', '#1976d2', '#0d47a1', '#b71c1c']
            n_bins = 256
            custom_cmap = LinearSegmentedColormap.from_list('custom', colors, N=n_bins)
        else:
            custom_cmap = LinearSegmentedColormap.from_list('custom', list(custom_colors.values()))
    else:
        custom_cmap = plt.cm.get_cmap(colormap)

    # Determine value range for color scaling
    if value_range is None:
        vmin, vmax = data.min().min(), data.max().max()
        # Add small padding
        range_padding = (vmax - vmin) * 0.05
        vmin = max(0, vmin - range_padding)
        vmax = vmax + range_padding
    else:
        vmin, vmax = value_range

    # Create the heatmap
    im = ax.imshow(data.values, cmap=custom_cmap, aspect='auto',
                   vmin=vmin, vmax=vmax, interpolation='nearest')

    # Add cell borders
    if border_width > 0:
        for i in range(data.shape[0] + 1):
            ax.axhline(y=i-0.5, color=border_color, linewidth=border_width)
        for j in range(data.shape[1] + 1):
            ax.axvline(x=j-0.5, color=border_color, linewidth=border_width)

    # Set ticks and labels
    ax.set_xticks(range(len(data.columns)))
    ax.set_yticks(range(len(data.index)))

    # Format labels for better readability
    x_labels = [label.replace('_', ' ').title() for label in data.columns]
    y_labels = [label.replace('_', ' ').title() for label in data.index]

    ax.set_xticklabels(x_labels, fontsize=font_sizes['ticks'], rotation=45, ha='right')
    ax.set_yticklabels(y_labels, fontsize=font_sizes['ticks'])

    # Add annotations
    if annotate:
        for i in range(data.shape[0]):
            for j in range(data.shape[1]):
                value = data.iloc[i, j]

                # Choose text color based on background
                if value > (vmin + vmax) / 2:
                    text_color = 'white'
                else:
                    text_color = 'black'

                # Format annotation
                if pd.isna(value):
                    text = 'N/A'
                else:
                    text = f'{value:{annotation_format}}'

                # Add significance markers if requested
                if add_significance_markers and significance_data is not None:
                    if not pd.isna(significance_data.iloc[i, j]):
                        p_val = significance_data.iloc[i, j]
                        if p_val < 0.001:
                            text += '***'
                        elif p_val < 0.01:
                            text += '**'
                        elif p_val < 0.05:
                            text += '*'

                ax.text(j, i, text, ha='center', va='center',
                       color=text_color, fontsize=font_sizes['annotations'],
                       fontweight='bold' if text_color == 'white' else 'normal')

    # Highlight best performing cells
    if highlight_best:
        if highlight_threshold is None:
            # Use 90th percentile as threshold
            highlight_threshold = np.percentile(data.values[~pd.isna(data.values)], 90)

        for i in range(data.shape[0]):
            for j in range(data.shape[1]):
                if data.iloc[i, j] >= highlight_threshold:
                    # Add a golden border for best performers
                    rect = Rectangle((j-0.5, i-0.5), 1, 1, linewidth=3,
                                   edgecolor='gold', facecolor='none', zorder=10)
                    ax.add_patch(rect)

    # Add colorbar
    if show_colorbar:
        cbar = plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.set_label('Mean Positive Predictive Value',
                      fontsize=font_sizes['colorbar'], rotation=270, labelpad=20)
        cbar.ax.tick_params(labelsize=font_sizes['ticks'])

        # Add performance level labels on colorbar
        cbar_ticks = np.linspace(vmin, vmax, 5)
        cbar.set_ticks(cbar_ticks)

        # Add interpretative labels
        performance_levels = []
        for tick in cbar_ticks:
            if tick >= 0.8:
                performance_levels.append(f'{tick:.2f}\n(Excellent)')
            elif tick >= 0.6:
                performance_levels.append(f'{tick:.2f}\n(Good)')
            elif tick >= 0.4:
                performance_levels.append(f'{tick:.2f}\n(Fair)')
            elif tick >= 0.2:
                performance_levels.append(f'{tick:.2f}\n(Poor)')
            else:
                performance_levels.append(f'{tick:.2f}\n(Very Poor)')

        cbar.set_ticklabels(performance_levels)

    # Set title with enhanced formatting
    ax.set_title(title, fontsize=font_sizes['title'], fontweight='bold', pad=20)

    # Add axis labels
    ax.set_xlabel('Association Metrics', fontsize=font_sizes['labels'], fontweight='bold')
    ax.set_ylabel('Input Data Types', fontsize=font_sizes['labels'], fontweight='bold')

    # Fine-tune layout
    plt.tight_layout()

    # Add summary statistics box
    #_add_summary_box(fig, data, highlight_threshold if highlight_best else None)

    # Save figure if path provided
    if save_path:
        plt.savefig(save_path, dpi=dpi, bbox_inches='tight',
                   facecolor='white', edgecolor='none')
        print(f"Figure saved to: {save_path}")

    return fig, ax

def _add_summary_box(fig: plt.Figure, data: pd.DataFrame, highlight_threshold: Optional[float] = None):
    """Add a summary statistics box to the figure"""

    # Calculate summary statistics
    valid_data = data.values[~pd.isna(data.values)]

    if len(valid_data) == 0:
        return

    mean_ppv = np.mean(valid_data)
    std_ppv = np.std(valid_data)
    max_ppv = np.max(valid_data)
    min_ppv = np.min(valid_data)

    # Find best performing combination
    max_idx = np.unravel_index(np.nanargmax(data.values), data.shape)
    best_input = data.index[max_idx[0]]
    best_metric = data.columns[max_idx[1]]

    # Create summary text
    summary_text = f"""Summary Statistics:
Mean PPV: {mean_ppv:.3f} ± {std_ppv:.3f}
Range: [{min_ppv:.3f}, {max_ppv:.3f}]
Best: {best_input} + {best_metric}
Best PPV: {max_ppv:.3f}"""

    if highlight_threshold is not None:
        n_excellent = np.sum(valid_data >= highlight_threshold)
        summary_text += f"\nExcellent (≥{highlight_threshold:.3f}): {n_excellent}/{len(valid_data)}"

    # Add text box
    fig.text(0.02, 0.98, summary_text, transform=fig.transFigure,
             fontsize=9, verticalalignment='top',
             bbox=dict(boxstyle='round,pad=0.5', facecolor='lightgray', alpha=0.8))
