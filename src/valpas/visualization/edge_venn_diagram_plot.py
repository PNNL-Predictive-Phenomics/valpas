import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib_venn import venn3, venn3_circles, venn3_unweighted
import seaborn as sns
from typing import List, Tuple, Dict, Set, Optional, Union
import itertools
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')

def extract_edges_and_nodes(df: pd.DataFrame, protein1_col: str = 'protein_1', protein2_col: str = 'protein_2') -> Tuple[Set, Set]:
    """
    Extract edge and node sets from a dataframe

    Args:
        df: DataFrame containing edges
        protein1_col: Column name for first protein
        protein2_col: Column name for second protein

    Returns:
        Tuple of (edge_set, node_set)
    """
    if protein1_col not in df.columns or protein2_col not in df.columns:
        raise ValueError(f"Columns {protein1_col} and/or {protein2_col} not found in dataframe")

    # Create edge set (standardized - smaller protein first)
    edges = set()
    nodes = set()

    for _, row in df.iterrows():
        p1, p2 = str(row[protein1_col]), str(row[protein2_col])

        # Add nodes
        nodes.add(p1)
        nodes.add(p2)

        # Add edge (standardized order)
        edge = tuple(sorted([p1, p2]))
        edges.add(edge)

    return edges, nodes

def plot_network_venn_diagrams(
    dataframes: List[pd.DataFrame],
    labels: List[str],
    title: str = "Network Overlap Analysis",
    protein1_col: str = 'protein_1',
    protein2_col: str = 'protein_2',
    plot_edges: bool = True,
    plot_nodes: bool = True,
    figsize: Tuple[int, int] = (16, 8),
    colors: List[str] = None,
    alpha: float = 0.6,
    show_percentages: bool = True,
    save_path: Optional[str] = None,
    dpi: int = 300,
    include_summary: bool = True,
    subset_font_size: int = 12,
    title_font_size: int = 14
) -> Tuple[plt.Figure, Dict]:
    """
    Create Venn diagrams for edge and node overlaps between three networks

    Args:
        dataframes: List of 3 DataFrames containing network edges
        labels: List of 3 labels for the networks
        title: Overall title for the figure
        protein1_col: Column name for first protein
        protein2_col: Column name for second protein
        plot_edges: Whether to plot edge overlaps
        plot_nodes: Whether to plot node overlaps
        figsize: Figure size (width, height)
        colors: List of colors for the three sets
        alpha: Transparency for the circles
        show_percentages: Whether to show percentages in addition to counts
        save_path: Path to save the figure
        dpi: Resolution for saved figure
        include_summary: Whether to include summary statistics
        subset_font_size: Font size for subset labels
        title_font_size: Font size for subplot titles

    Returns:
        Tuple of (figure, analysis_results)
    """

    if len(dataframes) != 3 or len(labels) != 3:
        raise ValueError("Exactly 3 dataframes and 3 labels are required")

    # Set default colors
    if colors is None:
        colors = ['#ff9999', '#66b3ff', '#99ff99']  # Red, Blue, Green

    # Extract edges and nodes for each dataframe
    network_data = {}
    for i, (df, label) in enumerate(zip(dataframes, labels)):
        edges, nodes = extract_edges_and_nodes(df, protein1_col, protein2_col)
        network_data[label] = {
            'edges': edges,
            'nodes': nodes,
            'dataframe': df,
            'color': colors[i]
        }

    # Determine subplot configuration
    n_plots = sum([plot_edges, plot_nodes])
    if include_summary:
        n_plots += 1

    if n_plots == 1:
        fig, axes = plt.subplots(1, 1, figsize=figsize)
        axes = [axes]
    elif n_plots == 2:
        fig, axes = plt.subplots(1, 2, figsize=figsize)
    else:
        fig, axes = plt.subplots(1, 3, figsize=figsize)

    plot_idx = 0
    analysis_results = {}

    # Plot edge overlaps
    if plot_edges:
        ax_edges = axes[plot_idx]
        plot_idx += 1

        # Get edge sets
        edge_sets = [network_data[label]['edges'] for label in labels]

        # Calculate overlaps
        edge_analysis = calculate_venn_overlaps(edge_sets, labels, 'edges')
        analysis_results['edges'] = edge_analysis

        # Create Venn diagram
        venn_data = (
            len(edge_analysis['only_A']),
            len(edge_analysis['only_B']),
            len(edge_analysis['AB_not_C']),
            len(edge_analysis['only_C']),
            len(edge_analysis['AC_not_B']),
            len(edge_analysis['BC_not_A']),
            len(edge_analysis['ABC'])
        )

        v_edges = venn3(venn_data, set_labels=labels, ax=ax_edges,
                       set_colors=colors, alpha=alpha)

        # Add percentages if requested
        if show_percentages and v_edges:
            _add_percentages_to_venn(v_edges, venn_data, subset_font_size)

        # Styling
        if v_edges:
            for text in v_edges.set_labels:
                if text:
                    text.set_fontsize(subset_font_size)
                    text.set_fontweight('bold')

            for text in v_edges.subset_labels:
                if text:
                    text.set_fontsize(subset_font_size)

        ax_edges.set_title(f'Edge Overlaps\n({sum(len(s) for s in edge_sets)} total edges)',
                          fontsize=title_font_size, fontweight='bold')

    # Plot node overlaps
    if plot_nodes:
        ax_nodes = axes[plot_idx]
        plot_idx += 1

        # Get node sets
        node_sets = [network_data[label]['nodes'] for label in labels]

        # Calculate overlaps
        node_analysis = calculate_venn_overlaps(node_sets, labels, 'nodes')
        analysis_results['nodes'] = node_analysis

        # Create Venn diagram
        venn_data = (
            len(node_analysis['only_A']),
            len(node_analysis['only_B']),
            len(node_analysis['AB_not_C']),
            len(node_analysis['only_C']),
            len(node_analysis['AC_not_B']),
            len(node_analysis['BC_not_A']),
            len(node_analysis['ABC'])
        )

        v_nodes = venn3(venn_data, set_labels=labels, ax=ax_nodes,
                       set_colors=colors, alpha=alpha)

        # Add percentages if requested
        if show_percentages and v_nodes:
            _add_percentages_to_venn(v_nodes, venn_data, subset_font_size)

        # Styling
        if v_nodes:
            for text in v_nodes.set_labels:
                if text:
                    text.set_fontsize(subset_font_size)
                    text.set_fontweight('bold')

            for text in v_nodes.subset_labels:
                if text:
                    text.set_fontsize(subset_font_size)

        ax_nodes.set_title(f'Node Overlaps\n({sum(len(s) for s in node_sets)} total unique nodes)',
                          fontsize=title_font_size, fontweight='bold')

    # Add summary statistics
    if include_summary and plot_idx < len(axes):
        ax_summary = axes[plot_idx]
        _create_summary_plot(ax_summary, analysis_results, labels, title_font_size)

    # Overall title
    fig.suptitle(title, fontsize=title_font_size + 2, fontweight='bold')

    plt.tight_layout()

    # Save figure if requested
    if save_path:
        plt.savefig(save_path, dpi=dpi, bbox_inches='tight', facecolor='white')
        print(f"Figure saved to: {save_path}")

    return fig, analysis_results

def calculate_venn_overlaps(sets: List[Set], labels: List[str], element_type: str) -> Dict:
    """
    Calculate all Venn diagram overlaps for three sets

    Args:
        sets: List of three sets to analyze
        labels: Labels for the sets
        element_type: Type of elements ('edges' or 'nodes')

    Returns:
        Dictionary with overlap analysis
    """

    set_A, set_B, set_C = sets
    label_A, label_B, label_C = labels

    # Calculate all overlaps
    overlap_analysis = {
        'element_type': element_type,
        'labels': labels,
        'set_sizes': [len(set_A), len(set_B), len(set_C)],

        # Individual sets
        'A': set_A,
        'B': set_B,
        'C': set_C,

        # Intersections
        'AB': set_A & set_B,
        'AC': set_A & set_C,
        'BC': set_B & set_C,
        'ABC': set_A & set_B & set_C,

        # Exclusive regions
        'only_A': set_A - set_B - set_C,
        'only_B': set_B - set_A - set_C,
        'only_C': set_C - set_A - set_B,
        'AB_not_C': (set_A & set_B) - set_C,
        'AC_not_B': (set_A & set_C) - set_B,
        'BC_not_A': (set_B & set_C) - set_A,

        # Unions
        'A_or_B': set_A | set_B,
        'A_or_C': set_A | set_C,
        'B_or_C': set_B | set_C,
        'all_union': set_A | set_B | set_C
    }

    # Calculate statistics
    total_unique = len(overlap_analysis['all_union'])
    overlap_analysis['statistics'] = {
        'total_unique': total_unique,
        'jaccard_AB': len(overlap_analysis['AB']) / len(overlap_analysis['A_or_B']) if len(overlap_analysis['A_or_B']) > 0 else 0,
        'jaccard_AC': len(overlap_analysis['AC']) / len(overlap_analysis['A_or_C']) if len(overlap_analysis['A_or_C']) > 0 else 0,
        'jaccard_BC': len(overlap_analysis['BC']) / len(overlap_analysis['B_or_C']) if len(overlap_analysis['B_or_C']) > 0 else 0,
        'jaccard_ABC': len(overlap_analysis['ABC']) / total_unique if total_unique > 0 else 0,
        'overlap_coefficient_AB': len(overlap_analysis['AB']) / min(len(set_A), len(set_B)) if min(len(set_A), len(set_B)) > 0 else 0,
        'overlap_coefficient_AC': len(overlap_analysis['AC']) / min(len(set_A), len(set_C)) if min(len(set_A), len(set_C)) > 0 else 0,
        'overlap_coefficient_BC': len(overlap_analysis['BC']) / min(len(set_B), len(set_C)) if min(len(set_B), len(set_C)) > 0 else 0,
    }

    return overlap_analysis

def _add_percentages_to_venn(venn_diagram, venn_data: Tuple, font_size: int):
    """Add percentage labels to Venn diagram subsets"""
    total = sum(venn_data)

    if total == 0:
        return

    # Update subset labels to include percentages
    for i, (subset_label, count) in enumerate(zip(venn_diagram.subset_labels, venn_data)):
        if subset_label and count > 0:
            percentage = (count / total) * 100
            subset_label.set_text(f'{count}\n({percentage:.1f}%)')
            subset_label.set_fontsize(font_size)

def _create_summary_plot(ax, analysis_results: Dict, labels: List[str], font_size: int):
    """Create summary statistics plot"""

    ax.axis('off')

    # Prepare summary text
    summary_lines = ['OVERLAP ANALYSIS SUMMARY\n']

    for element_type in ['edges', 'nodes']:
        if element_type in analysis_results:
            data = analysis_results[element_type]
            stats = data['statistics']

            summary_lines.append(f'{element_type.upper()} ANALYSIS:')
            summary_lines.append(f'  Total unique: {stats["total_unique"]}')
            summary_lines.append(f'  Individual counts: {data["set_sizes"]}')
            summary_lines.append(f'  Three-way overlap: {len(data["ABC"])}')

            # Jaccard similarities
            summary_lines.append('  Jaccard Similarities:')
            summary_lines.append(f'    {labels[0]}-{labels[1]}: {stats["jaccard_AB"]:.3f}')
            summary_lines.append(f'    {labels[0]}-{labels[2]}: {stats["jaccard_AC"]:.3f}')
            summary_lines.append(f'    {labels[1]}-{labels[2]}: {stats["jaccard_BC"]:.3f}')
            summary_lines.append('')

    # Add text to plot
    summary_text = '\n'.join(summary_lines)
    ax.text(0.05, 0.95, summary_text, transform=ax.transAxes, fontsize=font_size-1,
            verticalalignment='top', fontfamily='monospace',
            bbox=dict(boxstyle='round,pad=0.5', facecolor='lightgray', alpha=0.8))

def create_detailed_overlap_analysis(
    analysis_results: Dict,
    labels: List[str],
    show_examples: bool = True,
    n_examples: int = 5
) -> str:
    """
    Create detailed text analysis of overlaps

    Args:
        analysis_results: Results from plot_network_venn_diagrams
        labels: Network labels
        show_examples: Whether to show example elements
        n_examples: Number of examples to show

    Returns:
        Formatted analysis string
    """

    analysis_text = []
    analysis_text.append("="*80)
    analysis_text.append("DETAILED NETWORK OVERLAP ANALYSIS")
    analysis_text.append("="*80)

    for element_type in ['edges', 'nodes']:
        if element_type not in analysis_results:
            continue

        data = analysis_results[element_type]
        stats = data['statistics']

        analysis_text.append(f"\n{element_type.upper()} ANALYSIS:")
        analysis_text.append("-" * 40)

        # Overall statistics
        analysis_text.append(f"Total unique {element_type}: {stats['total_unique']}")
        analysis_text.append(f"Individual set sizes: {dict(zip(labels, data['set_sizes']))}")

        # Overlap details
        analysis_text.append(f"\nOverlap Details:")
        analysis_text.append(f"  All three networks: {len(data['ABC'])} {element_type}")
        analysis_text.append(f"  {labels[0]} & {labels[1]} only: {len(data['AB_not_C'])} {element_type}")
        analysis_text.append(f"  {labels[0]} & {labels[2]} only: {len(data['AC_not_B'])} {element_type}")
        analysis_text.append(f"  {labels[1]} & {labels[2]} only: {len(data['BC_not_A'])} {element_type}")
        analysis_text.append(f"  {labels[0]} only: {len(data['only_A'])} {element_type}")
        analysis_text.append(f"  {labels[1]} only: {len(data['only_B'])} {element_type}")
        analysis_text.append(f"  {labels[2]} only: {len(data['only_C'])} {element_type}")

        # Similarity metrics
        analysis_text.append(f"\nSimilarity Metrics:")
        analysis_text.append(f"  Jaccard {labels[0]}-{labels[1]}: {stats['jaccard_AB']:.4f}")
        analysis_text.append(f"  Jaccard {labels[0]}-{labels[2]}: {stats['jaccard_AC']:.4f}")
        analysis_text.append(f"  Jaccard {labels[1]}-{labels[2]}: {stats['jaccard_BC']:.4f}")
        analysis_text.append(f"  Overlap Coeff {labels[0]}-{labels[1]}: {stats['overlap_coefficient_AB']:.4f}")
        analysis_text.append(f"  Overlap Coeff {labels[0]}-{labels[2]}: {stats['overlap_coefficient_AC']:.4f}")
        analysis_text.append(f"  Overlap Coeff {labels[1]}-{labels[2]}: {stats['overlap_coefficient_BC']:.4f}")

        # Examples
        if show_examples:
            analysis_text.append(f"\nExamples:")

            # Three-way overlap examples
            if len(data['ABC']) > 0:
                examples = list(data['ABC'])[:n_examples]
                analysis_text.append(f"  Common to all three ({len(examples)} of {len(data['ABC'])}):")
                for example in examples:
                    if element_type == 'edges':
                        analysis_text.append(f"    {example[0]} - {example[1]}")
                    else:
                        analysis_text.append(f"    {example}")

            # Unique to each network
            for i, label in enumerate(labels):
                unique_key = ['only_A', 'only_B', 'only_C'][i]
                if len(data[unique_key]) > 0:
                    examples = list(data[unique_key])[:n_examples]
                    analysis_text.append(f"  Unique to {label} ({len(examples)} of {len(data[unique_key])}):")
                    for example in examples:
                        if element_type == 'edges':
                            analysis_text.append(f"    {example[0]} - {example[1]}")
                        else:
                            analysis_text.append(f"    {example}")

    return '\n'.join(analysis_text)

def export_overlap_data(
    analysis_results: Dict,
    labels: List[str],
    output_dir: str = '.',
    file_prefix: str = 'network_overlap'
):
    """
    Export overlap data to CSV files

    Args:
        analysis_results: Results from plot_network_venn_diagrams
        labels: Network labels
        output_dir: Directory to save files
        file_prefix: Prefix for output files
    """

    import os

    for element_type in ['edges', 'nodes']:
        if element_type not in analysis_results:
            continue

        data = analysis_results[element_type]

        # Create summary DataFrame
        summary_data = {
            'Region': [
                'All three', f'{labels[0]} & {labels[1]} only', f'{labels[0]} & {labels[2]} only',
                f'{labels[1]} & {labels[2]} only', f'{labels[0]} only', f'{labels[1]} only', f'{labels[2]} only'
            ],
            'Count': [
                len(data['ABC']), len(data['AB_not_C']), len(data['AC_not_B']),
                len(data['BC_not_A']), len(data['only_A']), len(data['only_B']), len(data['only_C'])
            ]
        }

        summary_df = pd.DataFrame(summary_data)
        summary_file = os.path.join(output_dir, f'{file_prefix}_{element_type}_summary.csv')
        summary_df.to_csv(summary_file, index=False)

        # Export detailed lists for each region
        regions = {
            'all_three': data['ABC'],
            f'{labels[0]}_only': data['only_A'],
            f'{labels[1]}_only': data['only_B'],
            f'{labels[2]}_only': data['only_C'],
            f'{labels[0]}_{labels[1]}_only': data['AB_not_C'],
            f'{labels[0]}_{labels[2]}_only': data['AC_not_B'],
            f'{labels[1]}_{labels[2]}_only': data['BC_not_A']
        }

        for region_name, region_data in regions.items():
            if len(region_data) > 0:
                if element_type == 'edges':
                    region_df = pd.DataFrame(list(region_data), columns=['protein_1', 'protein_2'])
                else:
                    region_df = pd.DataFrame(list(region_data), columns=['protein'])

                region_file = os.path.join(output_dir, f'{file_prefix}_{element_type}_{region_name}.csv')
                region_df.to_csv(region_file, index=False)

        print(f"Exported {element_type} overlap data to {output_dir}")

# Example usage and testing
if __name__ == "__main__":
    # Create sample network dataframes
    np.random.seed(42)

    # Generate sample protein names
    all_proteins = [f'PROT_{i:04d}' for i in range(200)]

    # Create three networks with some overlap
    def create_sample_network(proteins, n_edges, network_id):
        edges = []
        for _ in range(n_edges):
            p1, p2 = np.random.choice(proteins, 2, replace=False)
            edges.append({'protein_1': p1, 'protein_2': p2, 'network': network_id})
        return pd.DataFrame(edges)

    # Network 1: Uses proteins 0-99, has 150 edges
    network1_proteins = all_proteins[:100]
    df1 = create_sample_network(network1_proteins, 150, 'Network_A')

    # Network 2: Uses proteins 50-149, has 120 edges
    network2_proteins = all_proteins[50:150]
    df2 = create_sample_network(network2_proteins, 120, 'Network_B')

    # Network 3: Uses proteins 75-174, has 100 edges
    network3_proteins = all_proteins[75:175]
    df3 = create_sample_network(network3_proteins, 100, 'Network_C')

    # Add some common edges across networks for overlap
    common_edges = [
        ('PROT_0060', 'PROT_0070'),
        ('PROT_0080', 'PROT_0090'),
        ('PROT_0085', 'PROT_0095')
    ]

    for p1, p2 in common_edges:
        df1 = pd.concat([df1, pd.DataFrame({'protein_1': [p1], 'protein_2': [p2], 'network': ['Network_A']})], ignore_index=True)
        df2 = pd.concat([df2, pd.DataFrame({'protein_1': [p1], 'protein_2': [p2], 'network': ['Network_B']})], ignore_index=True)
        df3 = pd.concat([df3, pd.DataFrame({'protein_1': [p1], 'protein_2': [p2], 'network': ['Network_C']})], ignore_index=True)

    print("Sample Network Statistics:")
    print(f"Network 1: {len(df1)} edges")
    print(f"Network 2: {len(df2)} edges")
    print(f"Network 3: {len(df3)} edges")

    # Test the main plotting function
    print("\n" + "="*60)
    print("Creating Venn diagram analysis...")
    print("="*60)

    fig, results = plot_network_venn_diagrams(
        dataframes=[df1, df2, df3],
        labels=['Network A', 'Network B', 'Network C'],
        title='Network Overlap Analysis',
        plot_edges=True,
        plot_nodes=True,
        figsize=(18, 6),
        show_percentages=True,
        include_summary=True,
        save_path='network_venn_analysis.png'
    )

    plt.show()

    # Test detailed analysis
    print("\n" + "="*60)
    print("Creating detailed analysis...")
    print("="*60)

    detailed_analysis = create_detailed_overlap_analysis(
        results,
        ['Network A', 'Network B', 'Network C'],
        show_examples=True,
        n_examples=3
    )

    print(detailed_analysis)

    # Test data export
    print("\n" + "="*60)
    print("Exporting overlap data...")
    print("="*60)

    export_overlap_data(
        results,
        ['Network A', 'Network B', 'Network C'],
        output_dir='.',
        file_prefix='test_network_overlap'
    )

    # Test edge-only and node-only plots
    print("\n" + "="*60)
    print("Creating specialized plots...")
    print("="*60)

    # Edge-only plot
    fig_edges, _ = plot_network_venn_diagrams(
        [df1, df2, df3],
        ['Network A', 'Network B', 'Network C'],
        title='Edge Overlap Analysis Only',
        plot_edges=True,
        plot_nodes=False,
        figsize=(10, 8),
        include_summary=False
    )
    plt.savefig('edge_overlap_only.png', dpi=300, bbox_inches='tight')
    plt.show()

    # Node-only plot
    fig_nodes, _ = plot_network_venn_diagrams(
        [df1, df2, df3],
        ['Network A', 'Network B', 'Network C'],
        title='Node Overlap Analysis Only',
        plot_edges=False,
        plot_nodes=True,
        figsize=(10, 8),
        include_summary=False
    )
    plt.savefig('node_overlap_only.png', dpi=300, bbox_inches='tight')
    plt.show()

    print("\n" + "="*60)
    print("Analysis complete!")
    print("Files created:")
    print("- network_venn_analysis.png")
    print("- edge_overlap_only.png")
    print("- node_overlap_only.png")
    print("- Various CSV files with overlap data")
    print("="*60)

    # Clean up test files
    import os
    test_files = [
        'network_venn_analysis.png', 'edge_overlap_only.png', 'node_overlap_only.png'
    ] + [f for f in os.listdir('.') if f.startswith('test_network_overlap') and f.endswith('.csv')]

    for file in test_files:
        if os.path.exists(file):
            os.remove(file)

    print("Test files cleaned up.")
