from dash import Dash, html
import networkx as nx
import dash_cytoscape as cyto
import pandas as pd
from pyvis.network import Network

def make_graphML(file_path, index_name, output_path):
    #read in data
    df = pd.read_csv(file_path)
    #set row names
    df = df.set_index(index_name)
    df.index.names = [None]
    #define lists for data
    graph = {}
    #collect data for nodes, only grab edges over a given threshold
    for column in df:
        for row in df.index:
            value = df.loc[row, column]
            if abs(value) > 0.3:
                if column in graph:
                    graph[column].update({row: {"weight": value}})
                else:
                    graph.update({column:{row: {"weight": value}}})
    G = nx.Graph(graph)
    nx.write_graphml(G, output_path)

def df_to_cyto(file_path, index_name, threshold):
    #read in data
    df = pd.read_csv(file_path)
    #set row names
    df = df.set_index(index_name)
    df.index.names = [None]
    #define lists for data
    nodes = []
    edges = []
    #collect data for nodes, only grab edges over a given threshold
    for column in df:
        nodes.append({'data':{'id':column, 'label':column}})
        for row in df.index:
            nodes.append({'data':{'id':row, 'label':row}})
            value = df.loc[row, column]
            if abs(value) > threshold:
                edges.append({'data': {'source': column, 'target': row}})

    #combine lists
    nodes = nodes + edges
    return nodes

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