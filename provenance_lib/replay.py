import networkx as nx
import pathlib
import re
from string import Template
from typing import Dict, Iterator, List, Literal

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


def replay_provdag(dag: ProvDAG,
                   usage_driver: DRIVER_CHOICES,
                   out_fp: pathlib.Path):
    sorted_nodes = nx.topological_sort(dag.collapsed_view)
    # NOTE: input nodes must be sorted if returned actions are also to be
    actions = group_by_action(dag, sorted_nodes)
    usage_examples = build_usage_examples(dag, actions)

    # Join usage examples
    # TODO: Drop this subscript and actually join all the examples
    usage_example_texts = usage_examples[0:1]
    joined_text = "\n".join(usage_example_texts)
    print("Joined Text: \n" + joined_text)

    # inject usage_driver
    PluginManager()
    use = SUPPORTED_USAGE_DRIVERS[usage_driver]()

    # TODO Make user opt in to exec code, offering them a view of the generated
    # usage example text by default. Consider explicit sanitization.
    exec(joined_text)

    # render usage and write to file
    rendered = use.render()
    print("\nRendered: \n" + rendered)
    with open(out_fp, mode='w') as fp:
        fp.write(rendered)


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
    # TODO: Deal with namespace collisions gracefully
    example_namespace = {}  # type: Dict[UUID, str]
    for action in actions:
        some_node_id_from_this_action = next(iter(actions[action]))
        # group_nodes_by_action guarantees only nodes with prov are in actions
        # all nodes from one action should have the same action_type etc, so:
        n_data = dag.get_node_data(some_node_id_from_this_action)
        # print(n_data.action.action_type)
        if n_data.action.action_type == 'import':
            example = build_import_usage(n_data, example_namespace)
        else:
            example = build_action_usage(n_data,
                                         example_namespace,
                                         actions,
                                         action)
        print(action + ': \n', example, '\n')
        examples.append(example)
        # print("EXAMPLE NAMESPACE:\n" + str(example_namespace))
    return examples


# TODO: I THINK we need the UUID from the dag, not from the ProvNode.
# check on this before shit gets too complicated. Are we updating ProvNode.uuid
# when we update dag UUIDs? It's probably time for that.
# TODO: Should this take a dag and actions instead of a single node?
def build_import_usage(node: ProvNode, namespace: Dict[UUID, str]) -> str:
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
    # TODO: Get these somewhere
    init_fmt_args = {
        'var_name': 'raw_seqs',
        'usage_var_name': 'raw_seqs',
        'file_ext': '.fastq.gz'}

    import_args = {
        'var_name': 'imported_seqs',
        'usage_var_name': 'emp_single_end_sequences',
        'sem_type': node.type,
        'fmt_var_name': init_fmt_args['var_name']}

    # string.Template does not exec substitutions like fstrings do, so safer
    init_fmt_template = Template(
        "$var_name = use.init_format('$usage_var_name', "
        "lambda: None, ext='$file_ext')\n")
    init_fmt_str = init_fmt_template.substitute(init_fmt_args)

    import_template = Template(
        "$var_name = use.import_from_format('$usage_var_name', "
        "'$sem_type'"
        ", $fmt_var_name)"
    )
    import_str = import_template.substitute(import_args)
    namespace.update({node.uuid: import_args['var_name']})

    return init_fmt_str + import_str


def build_action_usage(node: ProvNode,
                       namespace: Dict[UUID, str],
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
    inputs.update(params)
    subst_args = {
        'plugin': node.action.plugin,
        'action': node.action.action_name,
        'inputs': inputs,
        'outputs': actions[action_id],
    }
    namespace.update(subst_args['outputs'])

    # TODO: Confirm I can pass dictionaires to inputs/outputs argument objects
    action_template = Template(
        'use.action('
        'use.UsageAction(plugin_id=\'$plugin\', '
        'action_id=\'$action\'), '
        'use.UsageInputs($inputs), '
        'use.UsageOutputNames($outputs))'
    )
    return action_template.substitute(subst_args)
