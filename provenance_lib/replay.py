import networkx as nx
import pathlib
import re
from collections import UserDict
from string import Template
from typing import Dict, Iterator, List, Optional, Literal

from .archive_parser import ProvNode
from .parse import ProvDAG, UUID

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
                   unsafe_render: bool = False,
                   usage_driver: Optional[DRIVER_CHOICES] = None):
    """
    Generates usage example code for a single ProvDAG.
    Optionally executes and renders that code into an interface-specific script

    WARNING: This latter step, activated by passing unsafe_render=True,
    is unsafe, capable of executing arbitrary code, and should only be used
    with trusted ProvDAGs.

    Review the output of a run with the default settings first, and only use
    unsafe_render once you're confident that code is not malicious.

    TODO: Consider robust input sanitization.
    """
    if unsafe_render is True and usage_driver is None:
        raise ValueError(
            "A usage_driver is required when unsafe_render is True.")

    sorted_nodes = nx.topological_sort(dag.collapsed_view)
    # NOTE: input nodes must be sorted if returned actions are also to be
    actions = group_by_action(dag, sorted_nodes)
    usage_examples = build_usage_examples(dag, actions)

    # Join usage examples
    # TODO: Drop this subscript and actually join all the examples
    usage_example_texts = usage_examples[0:1]
    generated_code = "\n".join(usage_example_texts)

    if unsafe_render is True:
        PluginManager()
        # This position is only reachable if usage_driver is a string, but
        # mypy is nervous, so ignoring type.
        use = SUPPORTED_USAGE_DRIVERS[usage_driver]()  # type: ignore
        # execing generated usage examples makes use.render possible
        exec(generated_code)
        output = use.render()
        print("\nRendered: \n" + output)
    else:
        output = generated_code

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
            # For the sake of build_usage_examples, we should probably
            # continue to guarantee that no-prov nodes aren't added to actions
            raise NotImplementedError("Replay does not support no-prov nodes")
    return actions


def build_usage_examples(
        dag: ProvDAG, actions: Dict[UUID, Dict[UUID, str]]) -> List[str]:
    """
    TODO:
    """
    # TODO: Handle disconnected graphs
    examples = []
    results_namespace = UniqueValsDict()
    for action in actions:
        some_node_id_from_this_action = next(iter(actions[action]))
        # group_nodes_by_action guarantees only nodes with prov are in actions
        # all nodes from one action should have the same action_type etc, so:
        n_data = dag.get_node_data(some_node_id_from_this_action)
        if n_data.action.action_type == 'import':
            example = build_import_usage(n_data, results_namespace)
        else:
            example = build_action_usage(n_data,
                                         results_namespace,
                                         actions,
                                         action)
        print(action + ': \n', example, '\n')
        examples.append(example)
    return examples


# TODO: I THINK we need the UUID from the dag, not from the ProvNode.
# check on this before shit gets too complicated. Are we updating ProvNode.uuid
# when we update dag UUIDs? It's probably time for that.
# TODO: Should this take a dag and actions instead of a single node?
def build_import_usage(node: ProvNode,
                       results_namespace: UniqueValsDict) -> str:
    """
    Given a ProvNode, builds the import component of a usage example, roughly
    resembling the following:

    raw_seqs = use.init_format('raw_seqs', lambda: None, ext='fastq.gz')
    imported_seqs = use.import_from_format(
        'emp_single_end_sequences',
        'EMPSingleEndSequences',
        raw_seqs
    )

    The `lambda: None` is a placeholder for some actual data factory,
    and should not impact the rendered usage.
    """
    init_fmt_args = {
        'var_name': get_init_from_format_var_name(node, results_namespace),
        'usage_var_name':  '<your data here>'}

    results_namespace.update({node.uuid: camel_to_snake(node.type)})
    import_args = {
        'var_name': 'imported_data',
        'usage_var_name': results_namespace[node.uuid],
        'sem_type': node.type,
        'fmt_var_name': init_fmt_args['var_name']}

    # string.Template does not exec substitutions like fstrings do, so safer
    init_fmt_template = Template(
        "$var_name = use.init_format('$usage_var_name', "
        "lambda: None)\n")
    init_fmt_str = init_fmt_template.substitute(init_fmt_args)

    import_template = Template(
        "$var_name = use.import_from_format('$usage_var_name', "
        "'$sem_type'"
        ", $fmt_var_name)"
    )
    import_str = import_template.substitute(import_args)

    return init_fmt_str + import_str


def get_init_from_format_var_name(node: ProvNode,
                                  results_namespace: UniqueValsDict) -> str:
    """
    Attempts to return a meaningful format name from an import's action.yaml
    Failing that, returns 'filler_format_var'.

    These variables don't need to be unique, as they are intermediate objects
    (formats, not artifacts) and so not saved to our results_namespace dict.
    """
    var_name = None
    try:
        var_name = camel_to_snake(node.action._action_details['format'])
    except KeyError:
        pass

    if var_name is None:
        transformers = node.action.transformers
        if transformers is not None:  # Makes mypy happy
            try:
                var_name = camel_to_snake(transformers['output'][-1]['to'])
            except KeyError:
                pass

    if var_name is None:
        var_name = "filler_format_var"

    return var_name


def build_action_usage(node: ProvNode,
                       namespace: UniqueValsDict,
                       actions: Dict[UUID, Dict[UUID, str]],
                       action_id: UUID) -> str:
    """
    Builds an action usage example roughly resembling the following:
    use.action(
        use.UsageAction(plugin_id='diversity_lib',
                        action_id='pielou_evenness'),
        use.UsageInputs(table=ft),
        use.UsageOutputNames(vector='pielou_vector')
    )
    """
    inputs = {key: value for key, value in node.action.inputs.items()}
    params = {key: value for key, value in node.action.parameters.items()}
    # TODO: NEXT handle metadata garbage
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

    print(params)
    inputs.update(params)
    subst_args = {
        'plugin': node.action.plugin,
        'action': node.action.action_name,
        'inputs': inputs,
        'outputs': actions[action_id],
    }
    namespace.update(subst_args['outputs'])

    action_template = Template(
        'use.action('
        'use.UsageAction(plugin_id=\'$plugin\', '
        'action_id=\'$action\'), '
        # inputs and outputs dicts must be unpacked for use as kwargs
        'use.UsageInputs(**$inputs), '
        'use.UsageOutputNames(**$outputs))'
    )
    return action_template.substitute(subst_args)
