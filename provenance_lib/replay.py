import networkx as nx

from .parse import ProvDAG

# Mk 1
# Take a provdag
# print an ordered list of commands

# Mk 2
# Take a provdag
# print an ordered list of usage examples

# Mk 3
# Take a provdag, choice of interface driver
# create an ordered list of usage examples
# Apply interface driver to them and .render()
# pipe rendered text into a text file of ordered commands


def replay_provdag(dag: ProvDAG):
    node_gen = nx.topological_sort(dag.collapsed_view)
    for node in node_gen:
        if dag.node_has_provenance(node):
            data = dag.get_node_data(node)
            plugin = data.action.plugin
            action = data.action.action_name
            print(node, plugin, action)
