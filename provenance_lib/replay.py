import networkx as nx
import pathlib
from typing import Any, Dict, Iterator, Literal

from .archive_parser import ProvNode
from .parse import ProvDAG, UUID

from qiime2.sdk import PluginManager
from qiime2.plugins import ArtifactAPIUsage
from q2cli.core.usage import CLIUsage

DRIVER_CHOICES = Literal['python3', 'cli']
SUPPORTED_USAGE_DRIVERS = {
    'python3': ArtifactAPIUsage,
    'cli': CLIUsage,
}

# TODO Sanitization: Make user opt in to exec code, offering them a view of the
# genereated usage example text by default. Consider explicit sanitization.

def replay_provdag(dag: ProvDAG,
                   usage_driver: DRIVER_CHOICES,
                   out_fp: pathlib.Path):
    # Get sorted iterator of nodes
    node_gen = nx.topological_sort(dag.collapsed_view)
    usage_examples = build_usage_examples(dag, node_gen)

    # Join usage examples
    # TODO: Can we skip the dict-building and just use a list or str?
    # TODO: Drop this subscript and actually join all the examples
    usage_example_texts = list(usage_examples.values())[0:1]
    joined_text = "\n".join(usage_example_texts)
    print("Joined Text: \n" + joined_text)

    # inject usage_driver
    PluginManager()
    use = SUPPORTED_USAGE_DRIVERS[usage_driver]()
    exec(joined_text)

    # render usage and write to file
    rendered = use.render()
    print("\nRendered: \n" + rendered)
    with open(out_fp, mode='w') as fp:
        fp.write(rendered)


def build_usage_examples(dag: ProvDAG, node_gen: Iterator[ProvNode]) -> \
        Dict[UUID, str]:
    # TODO: Handle disconnected graphs
    examples = {}
    # TODO: add empty example_namespace dict here, and pass to example builders
    # type: Dict[UUID, str] # str here is the variable name holding the artif.
    for node in node_gen:
        if dag.node_has_provenance(node):
            data = dag.get_node_data(node)
            if data.action.action_type == 'import':
                example = build_import_usage(data)
            else:
                example = build_action_usage(data)
            print(node + ': \n', example, '\n')
            examples[node] = example
        else:
            # TODO
            raise NotImplementedError("Handle replay of nodes without prov")
    return examples


def build_import_usage(node: ProvNode) -> str:
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
    sem_type = node.type

    # TODO: Get these somewhere
    fmt_var_name = 'raw_seqs'
    usage_var_name = 'raw_seqs'
    file_ext = '.fastq.gz'
    imp_var_name = 'imported_seqs'
    imp_usage_var_name = 'emp_single_end_sequences'

    init_fmt_str = (
        f"{fmt_var_name} = use.init_format('{usage_var_name}', "
        f"lambda: None, ext='{file_ext}')\n")

    import_str = (
        f"{imp_var_name} = use.import_from_format('{imp_usage_var_name}', "
        f"'{sem_type}'"
        f", {fmt_var_name})"
    )

    return init_fmt_str + import_str


def build_action_usage(node: ProvNode) -> str:
    """
    # TODO: MYPY
    Maybe this actually returns a qiime2.sdk.usage.UsageOutputs?
    This would require us to import from framework

    Given a ProvNode, builds a command roughly resembling the following:
    use.action(
        use.UsageAction(plugin_id='diversity_lib',
                        action_id='pielou_evenness'),
        use.UsageInputs(table=ft),
        use.UsageOutputNames(vector='pielou_vector')
    )
    """
    plugin = node.action.plugin
    action = node.action.action_name
    if node.action.action_type == 'import':
        # TODO: Handle qiime imports
        inputs = None
    else:
        inputs = {key: value for key, value in node.action.inputs.items()}
        params = {key: value for key, value in node.action.parameters.items()}
        inputs.update(params)
    outputs = {key: value for key, value in node.action.outputs.items()}
    # TODO: Confirm I can pass these 'argument objects' dictionaries
    return ('use.action('
            f'use.UsageAction(plugin_id=\'{plugin}\', '
            f'action_id=\'{action}\'), '
            f'use.UsageInputs({inputs}), '
            f'use.UsageOutputNames({outputs}))'
            )
