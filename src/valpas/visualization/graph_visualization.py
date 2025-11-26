import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
import networkx as nx
from ipywidgets import interact, FloatSlider, IntSlider, Dropdown
import warnings
warnings.filterwarnings('ignore')

class InteractiveGraphVisualizer:
    def __init__(self, data, source_col='source', target_col='target', weight_col='weight',
                 confidence_col='confidence', source_annotation_col='source_annotation',
                 target_annotation_col='target_annotation', edge_annotation_col=None):
        """
        Initialize the graph visualizer with flexible column specifications.

        Parameters:
        data (DataFrame or list): Edge data as pandas DataFrame or list of dictionaries
        source_col (str): Column name for source nodes
        target_col (str): Column name for target nodes
        weight_col (str): Column name for edge weights
        confidence_col (str): Column name for edge confidence values
        source_annotation_col (str): Column name for source node annotations
        target_annotation_col (str): Column name for target node annotations
        edge_annotation_col (str, optional): Column name for edge annotations
        """
        # Convert to DataFrame if needed
        if isinstance(data, list):
            self.edges_df = pd.DataFrame(data)
        else:
            self.edges_df = data.copy()

        # Store column mappings
        self.columns = {
            'source': source_col,
            'target': target_col,
            'weight': weight_col,
            'confidence': confidence_col,
            'source_annotation': source_annotation_col,
            'target_annotation': target_annotation_col,
            'edge_annotation': edge_annotation_col
        }

        # Validate required columns exist
        required_cols = [source_col, target_col, weight_col, confidence_col,
                        source_annotation_col, target_annotation_col]
        missing_cols = [col for col in required_cols if col not in self.edges_df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")

        self.graph = None
        self.pos = None
        self.node_annotations = {}
        self._prepare_graph()

    def _get_column_data(self, col_type):
        """Helper method to get data from specified columns."""
        col_name = self.columns[col_type]
        if col_name and col_name in self.edges_df.columns:
            return self.edges_df[col_name]
        return None

    def _prepare_graph(self):
        """Prepare the NetworkX graph and node positions."""
        self.graph = nx.Graph()

        # Add edges with attributes
        for _, row in self.edges_df.iterrows():
            source = row[self.columns['source']]
            target = row[self.columns['target']]
            weight = row[self.columns['weight']]
            confidence = row[self.columns['confidence']]

            # Create edge annotation
            if self.columns['edge_annotation'] and self.columns['edge_annotation'] in self.edges_df.columns:
                edge_annotation = row[self.columns['edge_annotation']]
            else:
                edge_annotation = f"Weight: {weight:.2f}, Confidence: {confidence:.2f}"

            self.graph.add_edge(
                source, target,
                weight=weight,
                confidence=confidence,
                edge_annotation=edge_annotation
            )

        # Store node annotations
        for _, row in self.edges_df.iterrows():
            source = row[self.columns['source']]
            target = row[self.columns['target']]
            source_annotation = row[self.columns['source_annotation']]
            target_annotation = row[self.columns['target_annotation']]

            # Store annotation, marking if it's meaningful or empty
            self.node_annotations[source] = {
                'text': source_annotation if pd.notna(source_annotation) and str(source_annotation).strip() else '',
                'has_annotation': pd.notna(source_annotation) and str(source_annotation).strip() != ''
            }
            self.node_annotations[target] = {
                'text': target_annotation if pd.notna(target_annotation) and str(target_annotation).strip() else '',
                'has_annotation': pd.notna(target_annotation) and str(target_annotation).strip() != ''
            }

        # Calculate layout
        self.pos = nx.spring_layout(self.graph, k=3, iterations=50)

    def _get_neighbor_annotation_info(self, node, filtered_graph, max_annotations=5):
        """
        Get detailed information about neighbor annotations for hover display.

        Parameters:
        node: The node to analyze
        filtered_graph: The current filtered graph
        max_annotations: Maximum number of annotations to show in detail

        Returns:
        dict: Information about neighbor annotations
        """
        neighbors = list(filtered_graph.neighbors(node))

        # Separate annotated and non-annotated neighbors
        annotated_neighbors = []
        non_annotated_neighbors = []

        for neighbor in neighbors:
            neighbor_info = self.node_annotations.get(neighbor, {'text': '', 'has_annotation': False})
            if neighbor_info['has_annotation']:
                annotated_neighbors.append({
                    'node': neighbor,
                    'annotation': neighbor_info['text']
                })
            else:
                non_annotated_neighbors.append(neighbor)

        # Create summary text for hover
        hover_parts = []

        if annotated_neighbors:
            hover_parts.append(f"📝 Annotated neighbors ({len(annotated_neighbors)}):")

            # Show detailed annotations for first few neighbors
            for i, neighbor_data in enumerate(annotated_neighbors[:max_annotations]):
                # Truncate long annotations for hover display
                annotation = neighbor_data['annotation']
                if len(annotation) > 50:
                    annotation = annotation[:47] + "..."
                hover_parts.append(f"  • {neighbor_data['node']}: {annotation}")

            # If there are more annotated neighbors, show count
            if len(annotated_neighbors) > max_annotations:
                remaining = len(annotated_neighbors) - max_annotations
                hover_parts.append(f"  ... and {remaining} more annotated neighbor(s)")

        if non_annotated_neighbors:
            hover_parts.append(f"📄 Non-annotated neighbors ({len(non_annotated_neighbors)}):")
            # Show first few non-annotated neighbors
            shown_non_annotated = non_annotated_neighbors[:max_annotations]
            hover_parts.append(f"  • {', '.join(map(str, shown_non_annotated))}")

            if len(non_annotated_neighbors) > max_annotations:
                remaining = len(non_annotated_neighbors) - max_annotations
                hover_parts.append(f"  ... and {remaining} more")

        if not neighbors:
            hover_parts.append("🔸 No neighbors")

        return {
            'annotated_count': len(annotated_neighbors),
            'non_annotated_count': len(non_annotated_neighbors),
            'total_count': len(neighbors),
            'hover_text': "<br>".join(hover_parts),
            'annotated_neighbors': annotated_neighbors,
            'non_annotated_neighbors': non_annotated_neighbors
        }

    def _get_annotated_neighbor_colors(self, filtered_graph):
        """
        Generate colors for nodes based on their annotated neighbors.
        Annotated nodes get one color, non-annotated nodes get colors based on
        number of annotated neighbors.
        """
        # Define color palette for different numbers of annotated neighbors
        neighbor_colors = [
            '#d62728',  # Red - 0 annotated neighbors
            '#ff7f0e',  # Orange - 1 annotated neighbor
            '#2ca02c',  # Green - 2 annotated neighbors
            '#1f77b4',  # Blue - 3 annotated neighbors
            '#9467bd',  # Purple - 4 annotated neighbors
            '#8c564b',  # Brown - 5 annotated neighbors
            '#e377c2',  # Pink - 6+ annotated neighbors
        ]

        annotated_color = '#17becf'  # Cyan for annotated nodes

        node_colors = []
        node_color_info = []
        max_annotated_neighbors = 0

        for node in filtered_graph.nodes():
            has_annotation = self.node_annotations.get(node, {}).get('has_annotation', False)

            if has_annotation:
                node_colors.append(annotated_color)
                node_color_info.append('Annotated')
            else:
                # Count annotated neighbors
                neighbors = list(filtered_graph.neighbors(node))
                annotated_neighbors = sum(1 for neighbor in neighbors
                                        if self.node_annotations.get(neighbor, {}).get('has_annotation', False))

                max_annotated_neighbors = max(max_annotated_neighbors, annotated_neighbors)

                # Select color based on number of annotated neighbors
                color_idx = min(annotated_neighbors, len(neighbor_colors) - 1)
                node_colors.append(neighbor_colors[color_idx])

                if annotated_neighbors == 0:
                    node_color_info.append('No annotated neighbors')
                elif annotated_neighbors == 1:
                    node_color_info.append('1 annotated neighbor')
                else:
                    node_color_info.append(f'{annotated_neighbors} annotated neighbors')

        return node_colors, node_color_info, max_annotated_neighbors

    def create_interactive_plot(self, weight_threshold=None, confidence_threshold=None,
                              layout_type='spring', node_size_factor=1.0, show_edge_labels=True,
                              color_by='annotation', annotated_color='#1f77b4',
                              non_annotated_color='#ff7f0e', max_hover_annotations=3):
        """
        Create an interactive plot with filtering capabilities.

        Parameters:
        weight_threshold (float): Minimum weight threshold
        confidence_threshold (float): Minimum confidence threshold
        layout_type (str): Layout algorithm ('spring', 'circular', 'random', 'kamada_kawai')
        node_size_factor (float): Factor to adjust node sizes
        show_edge_labels (bool): Whether to show edge labels
        color_by (str): Coloring scheme ('annotation', 'annotated_neighbors', 'degree', 'weight')
        annotated_color (str): Color for nodes with annotations
        non_annotated_color (str): Color for nodes without annotations
        max_hover_annotations (int): Maximum number of neighbor annotations to show in hover
        """
        # Set default thresholds if not provided
        if weight_threshold is None:
            weight_threshold = self.edges_df[self.columns['weight']].min()
        if confidence_threshold is None:
            confidence_threshold = self.edges_df[self.columns['confidence']].min()

        # Filter edges based on thresholds
        filtered_edges = self.edges_df[
            (self.edges_df[self.columns['weight']] >= weight_threshold) &
            (self.edges_df[self.columns['confidence']] >= confidence_threshold)
        ]

        if filtered_edges.empty:
            print("No edges meet the specified criteria.")
            return None

        # Create filtered graph
        filtered_graph = nx.Graph()
        for _, row in filtered_edges.iterrows():
            source = row[self.columns['source']]
            target = row[self.columns['target']]
            weight = row[self.columns['weight']]
            confidence = row[self.columns['confidence']]

            if self.columns['edge_annotation'] and self.columns['edge_annotation'] in filtered_edges.columns:
                edge_annotation = row[self.columns['edge_annotation']]
            else:
                edge_annotation = f"Weight: {weight:.2f}, Confidence: {confidence:.2f}"

            filtered_graph.add_edge(
                source, target,
                weight=weight,
                confidence=confidence,
                edge_annotation=edge_annotation
            )

        # Choose layout
        layout_functions = {
            'spring': lambda g: nx.spring_layout(g, k=3, iterations=50),
            'circular': lambda g: nx.circular_layout(g),
            'random': lambda g: nx.random_layout(g),
            'kamada_kawai': lambda g: nx.kamada_kawai_layout(g) if len(g.nodes()) > 1 else nx.spring_layout(g)
        }

        pos = layout_functions.get(layout_type, layout_functions['spring'])(filtered_graph)

        # Prepare edge traces
        edge_x = []
        edge_y = []
        edge_weights = []
        edge_hover_text = []

        for edge in filtered_graph.edges():
            x0, y0 = pos[edge[0]]
            x1, y1 = pos[edge[1]]
            edge_x.extend([x0, x1, None])
            edge_y.extend([y0, y1, None])

            edge_data = filtered_graph[edge[0]][edge[1]]
            edge_weights.append(edge_data['weight'])
            edge_hover_text.append(
                f"<b>{edge[0]} → {edge[1]}</b><br>"
                f"{edge_data['edge_annotation']}<br>"
                f"Weight: {edge_data['weight']:.3f}<br>"
                f"Confidence: {edge_data['confidence']:.3f}"
            )

        # Create edge trace
        edge_trace = go.Scatter(
            x=edge_x, y=edge_y,
            line=dict(width=2, color='rgba(125,125,125,0.5)'),
            hoverinfo='none',
            mode='lines',
            name='Edges',
            showlegend=False
        )

        # Prepare node data with enhanced neighbor information
        node_x = []
        node_y = []
        node_text = []
        node_info = []
        node_degrees = []
        node_has_annotation = []

        for node in filtered_graph.nodes():
            x, y = pos[node]
            node_x.append(x)
            node_y.append(y)
            node_text.append(str(node))

            # Get annotation info for this node
            annotation_info = self.node_annotations.get(node, {'text': '', 'has_annotation': False})
            has_annotation = annotation_info['has_annotation']
            annotation_text = annotation_info['text']
            node_has_annotation.append(has_annotation)

            # Get detailed neighbor information
            neighbor_info = self._get_neighbor_annotation_info(node, filtered_graph, max_hover_annotations)
            node_degrees.append(neighbor_info['total_count'])

            # Create comprehensive hover info
            hover_info_parts = [f"<b>🔷 {node}</b>"]

            # Add node's own annotation
            if has_annotation:
                # Truncate long annotations
                display_annotation = annotation_text
                if len(display_annotation) > 80:
                    display_annotation = display_annotation[:77] + "..."
                hover_info_parts.append(f"📋 Annotation: {display_annotation}")
            else:
                hover_info_parts.append("📋 No annotation")

            # Add connection summary
            hover_info_parts.append(
                f"🔗 Connections: {neighbor_info['total_count']} "
                f"({neighbor_info['annotated_count']} annotated, {neighbor_info['non_annotated_count']} not)"
            )

            # Add detailed neighbor information
            if neighbor_info['total_count'] > 0:
                hover_info_parts.append("") # Empty line for spacing
                hover_info_parts.append(neighbor_info['hover_text'])

            node_info.append("<br>".join(hover_info_parts))

        # Determine node colors based on coloring scheme
        color_discrete = True
        colorbar_title = ""
        legend_text = ""

        if color_by == 'annotation':
            node_colors = [annotated_color if has_ann else non_annotated_color
                          for has_ann in node_has_annotation]
            legend_text = f"Blue=annotated, Orange=not annotated"

        elif color_by == 'annotated_neighbors':
            node_colors, node_color_info, max_neighbors = self._get_annotated_neighbor_colors(filtered_graph)
            legend_text = f"Cyan=annotated, Red→Purple=0→{max_neighbors}+ annotated neighbors"

        elif color_by == 'degree':
            node_colors = node_degrees
            color_discrete = False
            colorbar_title = "Node<br>Degree"
            legend_text = "Color by total connections"

        elif color_by == 'weight':
            # Color by average weight of connected edges
            avg_weights = []
            for node in filtered_graph.nodes():
                connected_weights = [filtered_graph[node][neighbor]['weight']
                                   for neighbor in filtered_graph.neighbors(node)]
                avg_weight = np.mean(connected_weights) if connected_weights else 0
                avg_weights.append(avg_weight)
            node_colors = avg_weights
            color_discrete = False
            colorbar_title = "Average<br>Weight"
            legend_text = "Color by average edge weight"
        else:
            # Default to annotation coloring
            node_colors = [annotated_color if has_ann else non_annotated_color
                          for has_ann in node_has_annotation]
            legend_text = f"Blue=annotated, Orange=not annotated"

        # Normalize node sizes based on degree
        max_degree = max(node_degrees) if node_degrees else 1
        min_size = 15
        max_size = 40
        node_sizes = [min_size + (degree/max_degree) * (max_size - min_size) * node_size_factor
                     for degree in node_degrees]

        # Create node trace
        if color_discrete:
            marker_dict = dict(
                size=node_sizes,
                color=node_colors,
                line=dict(width=2, color='white'),
                opacity=0.8
            )
        else:
            marker_dict = dict(
                size=node_sizes,
                color=node_colors,
                colorscale='Viridis',
                showscale=True,
                colorbar=dict(
                    thickness=15,
                    len=0.5,
                    x=1.02,
                    title=dict(
                        text=colorbar_title,
                        side="right"
                    )
                ),
                line=dict(width=2, color='white'),
                opacity=0.8
            )

        node_trace = go.Scatter(
            x=node_x, y=node_y,
            mode='markers+text',
            hoverinfo='text',
            hovertext=node_info,
            text=node_text,
            textposition="middle center",
            textfont=dict(size=10, color='white'),
            marker=marker_dict,
            name='Nodes',
            showlegend=False
        )

        # Create the figure
        title_text = (f'Interactive Graph Network - Color by {color_by}<br>'
                     f'{self.columns["weight"]} ≥ {weight_threshold:.2f}, '
                     f'{self.columns["confidence"]} ≥ {confidence_threshold:.2f}<br>'
                     f'Nodes: {len(filtered_graph.nodes())}, Edges: {len(filtered_graph.edges())}')

        fig = go.Figure(data=[edge_trace, node_trace])

        fig.update_layout(
            title=dict(
                text=title_text,
                font=dict(size=16)
            ),
            showlegend=False,
            hovermode='closest',
            margin=dict(b=40, l=5, r=5, t=100),
            annotations=[
                dict(
                    text=f"Hover over nodes for detailed neighbor annotations. {legend_text}",
                    showarrow=False,
                    xref="paper", yref="paper",
                    x=0.005, y=-0.002,
                    xanchor="left", yanchor="bottom",
                    font=dict(color="gray", size=10)
                )
            ],
            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            width=900,
            height=700,
            plot_bgcolor='white'
        )

        # Add edge annotations if requested
        if show_edge_labels and len(filtered_graph.edges()) < 15:
            for edge in filtered_graph.edges():
                x0, y0 = pos[edge[0]]
                x1, y1 = pos[edge[1]]

                # Calculate midpoint
                mid_x = (x0 + x1) / 2
                mid_y = (y0 + y1) / 2

                edge_data = filtered_graph[edge[0]][edge[1]]

                fig.add_annotation(
                    x=mid_x, y=mid_y,
                    text=f"W:{edge_data['weight']:.1f}<br>C:{edge_data['confidence']:.1f}",
                    showarrow=False,
                    font=dict(size=8, color="blue"),
                    bgcolor="rgba(255,255,255,0.8)",
                    bordercolor="blue",
                    borderwidth=1
                )

        return fig

    def interactive_widget(self):
        """Create interactive widgets for real-time filtering."""
        weight_col = self.columns['weight']
        confidence_col = self.columns['confidence']

        weight_range = (self.edges_df[weight_col].min(), self.edges_df[weight_col].max())
        confidence_range = (self.edges_df[confidence_col].min(), self.edges_df[confidence_col].max())

        @interact(
            weight_threshold=FloatSlider(
                value=weight_range[0],
                min=weight_range[0],
                max=weight_range[1],
                step=(weight_range[1]-weight_range[0])/50 if weight_range[1] > weight_range[0] else 0.01,
                description=f'Min {weight_col}:'
            ),
            confidence_threshold=FloatSlider(
                value=confidence_range[0],
                min=confidence_range[0],
                max=confidence_range[1],
                step=(confidence_range[1]-confidence_range[0])/50 if confidence_range[1] > confidence_range[0] else 0.01,
                description=f'Min {confidence_col}:'
            ),
            layout_type=Dropdown(
                options=['spring', 'circular', 'random', 'kamada_kawai'],
                value='spring',
                description='Layout:'
            ),
            node_size_factor=FloatSlider(
                value=1.0,
                min=0.5,
                max=2.0,
                step=0.1,
                description='Node Size:'
            ),
            color_by=Dropdown(
                options=['annotation', 'annotated_neighbors', 'degree', 'weight'],
                value='annotated_neighbors',
                description='Color by:'
            ),
            show_edge_labels=[True, False],
            max_hover_annotations=IntSlider(
                value=3,
                min=1,
                max=10,
                step=1,
                description='Max annotations:'
            )
        )
        def update_plot(weight_threshold, confidence_threshold, layout_type,
                       node_size_factor, color_by, show_edge_labels, max_hover_annotations):
            fig = self.create_interactive_plot(
                weight_threshold=weight_threshold,
                confidence_threshold=confidence_threshold,
                layout_type=layout_type,
                node_size_factor=node_size_factor,
                show_edge_labels=show_edge_labels,
                color_by=color_by,
                max_hover_annotations=max_hover_annotations
            )
            if fig:
                fig.show()

    def get_summary(self):
        """Get summary statistics of the graph data."""
        weight_col = self.columns['weight']
        confidence_col = self.columns['confidence']

        # Count nodes with/without annotations
        annotated_count = sum(1 for node_info in self.node_annotations.values()
                            if node_info['has_annotation'])
        total_nodes = len(self.node_annotations)

        # Analyze annotated neighbor distribution
        neighbor_stats = {}
        for node, ann_info in self.node_annotations.items():
            if not ann_info['has_annotation']:  # Only for non-annotated nodes
                if node in self.graph:
                    neighbors = list(self.graph.neighbors(node))
                    annotated_neighbors = sum(1 for neighbor in neighbors
                                            if self.node_annotations.get(neighbor, {}).get('has_annotation', False))
                    neighbor_stats[node] = annotated_neighbors

        summary = {
            'total_edges': len(self.edges_df),
            'unique_nodes': total_nodes,
            'annotated_nodes': annotated_count,
            'non_annotated_nodes': total_nodes - annotated_count,
            'annotated_neighbor_distribution': neighbor_stats,
            'weight_stats': {
                'min': self.edges_df[weight_col].min(),
                'max': self.edges_df[weight_col].max(),
                'mean': self.edges_df[weight_col].mean(),
                'std': self.edges_df[weight_col].std()
            },
            'confidence_stats': {
                'min': self.edges_df[confidence_col].min(),
                'max': self.edges_df[confidence_col].max(),
                'mean': self.edges_df[confidence_col].mean(),
                'std': self.edges_df[confidence_col].std()
            }
        }
        return summary

    def print_color_legend(self):
        """Print a legend explaining the annotated_neighbors coloring scheme."""
        print("Annotated Neighbors Color Scheme:")
        print("=" * 40)
        print("🔵 Cyan: Nodes with annotations")
        print("🔴 Red: Non-annotated nodes with 0 annotated neighbors")
        print("🟠 Orange: Non-annotated nodes with 1 annotated neighbor")
        print("🟢 Green: Non-annotated nodes with 2 annotated neighbors")
        print("🔵 Blue: Non-annotated nodes with 3 annotated neighbors")
        print("🟣 Purple: Non-annotated nodes with 4 annotated neighbors")
        print("🟤 Brown: Non-annotated nodes with 5 annotated neighbors")
        print("🩷 Pink: Non-annotated nodes with 6+ annotated neighbors")
        print("\nHover Tips:")
        print("📋 = Node's own annotation")
        print("📝 = Annotated neighbors with their annotations")
        print("📄 = Non-annotated neighbors (names only)")
        print("🔗 = Connection summary")
