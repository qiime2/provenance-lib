import networkx as nx
import pathlib
import re
from collections import UserDict
from typing import Dict, Iterator, Literal

from .archive_parser import ProvNode
from .parse import ProvDAG, UUID
from .yaml_constructors import MetadataInfo

from qiime2.sdk import PluginManager  # type: ignore
from qiime2.plugins import ArtifactAPIUsage  # type: ignore
from q2cli.core.usage import CLIUsage  # type: ignore

DRIVER_CHOICES = Literal['python3', 'cli']
SUPPORTED_USAGE_DRIVERS = {
    'python3': ArtifactAPIUsage,
    'cli': CLIUsage,
}


class UniqueValsDict(UserDict):
    """
    A dict where values are also unique. Used here as a UUID-queryable
    "namespace" of strings that will be evaluated into python variable names.
    Non-unique values would cause namespace collisions.

    For consistency and simplicity, all values are suffixed with _n, such that
    n is some int. When potentially colliding values are added, n is
    incremented as needed until collision is avoided.

    NOTE: In cases where a var_name string must be used locally AND added to a
    UniqueValsDict as a value, best practice is to add it to the Dict before
    using it locally. UniqueValsDicts mutate ALL dict values they receive.
    """
    def __setitem__(self, key: UUID, item: str) -> None:
        unique_val = self._uniquify(item)
        return super().__setitem__(key, unique_val)

    def _uniquify(self, var_name: str) -> str:
        """
        Appends _<some_int> to var_name, such that the returned name won't
        collide with any variable-name values that already exist in the dict.
        """
        some_int = 0
        unique_name = f"{var_name}_{some_int}"
        while unique_name in self.data.values():
            some_int += 1
            unique_name = f"{var_name}_{some_int}"
        return unique_name


def replay_provdag(dag: ProvDAG, out_fp: pathlib.Path,
                   usage_driver: DRIVER_CHOICES,
                   use_recorded_metadata: bool = False):
    """
    Renders usage examples describing a ProvDAG, producing an interface-
    specific executable.

    if use_recorded_metadata is True, TODO: DO SOMETHING

    TODO: Consider robust input sanitization.
    TODO: probably refactor build_usage_examples to build a structure
    containing the required data. This way we build the data once, and users
    can use it to generate multiple UI examples from it.
    for now, we'll just pass the use into our builders.
    """
    PluginManager()
    use = SUPPORTED_USAGE_DRIVERS[usage_driver]()  # type: ignore
    build_usage_examples(dag, use)
    output = use.render()
    with open(out_fp, mode='w') as out_fh:
        out_fh.write(output)


def camel_to_snake(name: str) -> str:
    """
    There are more comprehensive and faster ways of doing this (incl compiling)
    but it handles acronyms in semantic types nicely
    e.g. EMPSingleEndSequences -> emp_single_end_sequences
    c/o https://stackoverflow.com/a/1176023/9872253
    """
    name = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', name).lower()


def group_by_action(dag: ProvDAG, nodes: Iterator[UUID]) -> \
        Dict[UUID, Dict[UUID, str]]:
    """
    Provenance is organized around outputs, but replay cares about actions.
    This groups the nodes from a DAG by action, returning a dict of dicts
    aggregating the outputs related to each action:

    {<action_id>: {<output_node_uuid>: 'output_name',
                   <output_node_2_uuid:> 'output_name_2'},
     <action_2_id> : ...
     }

    In cases where a captured output_name is unavailable, we substitute the
    output data's Semantic Type, snake-cased because it will be used as
    a variable name if this data is rendered by ArtifactAPIUsage.
    """
    actions = {}  # type: Dict[UUID, Dict[UUID, str]]
    for node in nodes:
        if dag.node_has_provenance(node):
            data = dag.get_node_data(node)
            action_id = data.action._execution_details['uuid']
            # neither imports nor older archive versions track output-names
            if (o_n := data.action.output_name) is not None:
                output_name = o_n
            else:
                output_name = camel_to_snake(data.type)

            try:
                actions[action_id].update({node: output_name})
            except KeyError:
                actions[action_id] = {node: output_name}
        else:
            # TODO: For the sake of build_usage_examples, we should probably
            # continue to guarantee that no-prov nodes aren't added to actions
            raise NotImplementedError("Replay does not support no-prov nodes")
    return actions


def build_usage_examples(dag: ProvDAG, use):
    """
    Builds a chained usage example representing the analysis `dag`.
    TODO: import Usage for typing?
    """
    # TODO: Handle disconnected graphs
    sorted_nodes = nx.topological_sort(dag.collapsed_view)
    actions = group_by_action(dag, sorted_nodes)
    results_namespace = UniqueValsDict()
    for action in actions:
        some_node_id_from_this_action = next(iter(actions[action]))
        # group_by_action guarantees only nodes with prov are in actions
        # all nodes from one action should have the same action_type etc, so:
        n_data = dag.get_node_data(some_node_id_from_this_action)
        if n_data.action.action_type == 'import':
            build_import_usage(n_data, results_namespace, use)
        else:
            build_action_usage(n_data, results_namespace, actions, action, use)


# TODO: I THINK we need the UUID from the dag, not from the ProvNode.
# check on this before shit gets too complicated. Are we updating ProvNode.uuid
# when we update dag UUIDs? It's probably time for that.
# TODO: Should this take a dag and actions instead of a single node?
def build_import_usage(node: ProvNode, results_namespace: UniqueValsDict, use):
    """
    Given a ProvNode, adds an import usage example for it, roughly
    resembling the following.

    Returns nothing, modifying the passed usage instance in place.

    raw_seqs = use.init_format('raw_seqs', lambda: None, ext='fastq.gz')
    imported_seqs = use.import_from_format(
        'emp_single_end_sequences',
        'EMPSingleEndSequences',
        raw_seqs
    )

    The `lambda: None` is a placeholder for some actual data factory,
    and should not impact the rendered usage.
    """
    results_namespace.update({node.uuid: camel_to_snake(node.type)})
    format_for_import = use.init_format('<your data here>', lambda: None)
    use.import_from_format(results_namespace[node.uuid],
                           node.type, format_for_import)


def build_action_usage(node: ProvNode,
                       namespace: UniqueValsDict,
                       actions: Dict[UUID, Dict[UUID, str]],
                       action_id: UUID,
                       use):
    """
    Adds an action usage example to use for some ProvNode, roughly resembling
    the following.

    Returns nothing, modifying the passed usage instance in place.

    use.action(
        use.UsageAction(plugin_id='diversity_lib',
                        action_id='pielou_evenness'),
        use.UsageInputs(table=ft),
        use.UsageOutputNames(vector='pielou_vector')
    )

    # TODO: clean up or remove
    actions looks like: {action_id: {node_id: node_name, ...}, ...}
    """
    inputs = {}
    for k, v in node.action.inputs.items():
        # TODO: namespace[v] is a string and renders as such - it should render
        # without single-quotes for the artifact API.
        # This guy could be useful: https://github.com/qiime2/qiime2/blob/
        # 6ef6df712f2f14be1baa5551368a41c3e9f8e340/qiime2/plugins.py#L31
        print(k, namespace[v])
        inputs.update({k: namespace[v]})

    print("PARAMS BE LIKE")
    # params = {key: value for key, value in node.action.parameters.items()}
    for k, v in node.action.parameters.items():
        print(k, v)
        if isinstance(v, MetadataInfo):
            print("JACKPOT!")
            # TODO NEXT: handle metadata
            # Look at raw examples with one metadata input and multiple
            # metadata inputs to the same parameter name. Capture the data we
            # need to duplicate that.
    # if there is metadata in any of our parameter values:
    #   if we are re-running with baked-in metadata, use the md files in prov
    #   else:
    #     dump the md files for user review
    #     use.comment("Context on reviewing dumped md sheets for structure")
    #     if no input_artifacts:
    #       mock: <your sample metadata here>
    #     else (input_artifact_uuids):
    #       pass variable names from namespace
    #     (both cases) <This command may have received additional metadata>
    # How does this look for MetadataColumns?
        inputs.update({k: v})

    raw_outputs = actions[action_id].items()
    outputs = {}
    for (k, v) in raw_outputs:
        namespace.update({k: v})
        uniquified_val = namespace[k]
        outputs.update({v: uniquified_val})

    plugin = node.action.plugin
    action = node.action.action_name

    use.action(
        use.UsageAction(plugin_id=plugin, action_id=action),
        use.UsageInputs(**inputs),
        use.UsageOutputNames(**outputs))
