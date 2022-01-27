import networkx as nx
import pathlib
import re
from collections import UserDict
from dataclasses import dataclass
from typing import Dict, Iterator, Literal

from .archive_parser import ProvNode
from .parse import ProvDAG, UUID
from .yaml_constructors import MetadataInfo

from q2cli.core.usage import CLIUsage  # type: ignore
from qiime2.plugins import ArtifactAPIUsage  # type: ignore
from qiime2.sdk import PluginManager  # type: ignore
from qiime2.sdk.usage import Usage, UsageVariable  # type: ignore


class ReplayPythonUsage(ArtifactAPIUsage):
    def _template_outputs(self, action, variables):
        """
        Monkeypatch allowing us to replay an action even when our provenance
        DAG doesn't have a record of all outputs from that action.
        """
        output_vars = []
        action_f = action.get_action()

        # need to coax the outputs into the correct order for unpacking
        for output in action_f.signature.outputs:
            try:
                variable = getattr(variables, output)
                output_vars.append(str(variable.to_interface_name()))
            except AttributeError:
                # if the args to UsageOutputNames skip an output name,
                # can we assume the user doesn't care about that output?
                # These assumptions are OK here, but not in the framework.
                # I'm guessing this could break chaining, so maybe
                # this behavior should warn?
                output_vars.append('_')

        if len(output_vars) == 1:
            output_vars.append('')

        return ', '.join(output_vars).strip()


class ReplayCLIUsage(CLIUsage):
    def _append_action_line(self, signature, param_name, value):
        """
        Monkeypatch allowing us to replay when recorded parameter names
        are not present in the registered function signatures in the active
        QIIME 2 environment
        """
        param_state = signature.get(param_name)
        if param_state is not None:
            for opt, val in self._make_param(value, param_state):
                line = self.INDENT + opt
                if val is not None:
                    line += ' ' + val
                line += ' \\'
                self.recorder.append(line)
        else:  # no matching param name
            # TODO: This case is not be caught by the ArtifactAPIDriver
            # Does that matter?
            line = self.INDENT + (
                "# TODO: The following parameter name was not found in "
                "your current\n  # QIIME 2 environment. This may occur "
                "when the plugin version you have\n  # installed does not "
                "match the version used in the original analysis.\n  # "
                "Please see the docs and correct the parameter name "
                "before running.\n")
            line += self.INDENT + '--?-' + param_name + ' ' + str(value)
            line += ' \\'
            self.recorder.append(line)


DRIVER_CHOICES = Literal['python3', 'cli']
SUPPORTED_USAGE_DRIVERS = {
    'python3': ReplayPythonUsage,
    'cli': ReplayCLIUsage,
}


@dataclass(frozen=False)
class ReplayConfig():
    use: Usage
    use_recorded_metadata: bool
    pm: PluginManager = PluginManager()
    md_context_has_been_printed: bool = False


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
    cfg = ReplayConfig(use=SUPPORTED_USAGE_DRIVERS[usage_driver](),
                       use_recorded_metadata=use_recorded_metadata)
    if cfg.use_recorded_metadata and not dag.cfg.parse_study_metadata:
        raise ValueError(
            "Metadata not captured for replay.  Re-parse metadata, or set "
            "use_recorded_metadata to False")
    build_usage_examples(dag, cfg)
    output = cfg.use.render()
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


def build_usage_examples(dag: ProvDAG, cfg: ReplayConfig):
    """
    Builds a chained usage example representing the analysis `dag`.
    TODO: Handle disconnected graphs
    """
    sorted_nodes = nx.topological_sort(dag.collapsed_view)
    actions = group_by_action(dag, sorted_nodes)
    results_namespace = UniqueValsDict()
    for action in actions:
        # group_by_action guarantees only nodes with provenance are in actions
        # all nodes from one action should have the same action_type etc, so:
        some_node_id_from_this_action = next(iter(actions[action]))
        n_data = dag.get_node_data(some_node_id_from_this_action)
        if n_data.action.action_type == 'import':
            build_import_usage(n_data, results_namespace, cfg)
        else:
            build_action_usage(n_data, results_namespace, actions, action, cfg)


def build_import_usage(node: ProvNode,
                       results_namespace: UniqueValsDict,
                       cfg: ReplayConfig):
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
    results_namespace.update({node._uuid: camel_to_snake(node.type)})
    format_for_import = cfg.use.init_format('<your data here>', lambda: None)
    cfg.use.import_from_format(results_namespace[node._uuid],
                               node.type, format_for_import)


def build_action_usage(node: ProvNode,
                       namespace: UniqueValsDict,
                       actions: Dict[UUID, Dict[UUID, str]],
                       action_id: UUID,
                       cfg: ReplayConfig):
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
    plugin = node.action.plugin
    action = node.action.action_name
    inputs = {}
    for k, v in node.action.inputs.items():
        # TODO: namespace[v] is a string and renders as such - it should render
        # without single-quotes for the artifact API.
        # This guy could be useful: https://github.com/qiime2/qiime2/blob/
        # 6ef6df712f2f14be1baa5551368a41c3e9f8e340/qiime2/plugins.py#L31
        inputs.update({k: namespace[v]})

    # Process outputs before params so we can access the unique output name
    # from the namespace when dumping metadata to files below
    raw_outputs = actions[action_id].items()
    outputs = {}
    for (k, v) in raw_outputs:
        namespace.update({k: v})
        uniquified_val = namespace[k]
        outputs.update({v: uniquified_val})

    for k, v in node.action.parameters.items():
        if isinstance(v, MetadataInfo):
            unique_md_id = namespace[node._uuid] + '_' + k
            namespace.update({unique_md_id: camel_to_snake(k)})
            dump_recorded_md_files(node, k)

            if cfg.use_recorded_metadata:
                init_md_from_recorded_md(node, unique_md_id, namespace, cfg)
            else:
                if not cfg.md_context_has_been_printed:
                    cfg.md_context_has_been_printed = True
                    cfg.use.comment(
                        "Replay attempts to represent metadata inputs "
                        "accurately, but metadata .tsv\nfiles are merged "
                        "automatically by some interfaces, rendering "
                        "distinctions\nbetween file inputs invisible in "
                        "provenance. We output the recorded metadata\nto disk "
                        "to enable visual inspection.\n")
                if not v.input_artifact_uuids:
                    md = init_md_from_md(node, k, unique_md_id, namespace, cfg)
                else:
                    md = init_md_from_artifacts(v, namespace, cfg)

                # TODO: Fix this fp getter once we're actually dumping md files
                fp = f'recorded_metadata/{plugin}_{action}/{k}.tsv'
                # TODO: Clean this up so we comment once per action, not once
                # per md file
                cfg.use.comment(
                    "The following command may have received additional "
                    "metadata .tsv files.\nTo confirm you have covered your "
                    "metadata needs adequately, review the original\nmetadata,"
                    f" saved at:\n{fp}\n")
            v = md
        inputs.update({k: v})

    cfg.use.action(
        cfg.use.UsageAction(plugin_id=plugin, action_id=action),
        cfg.use.UsageInputs(**inputs),
        cfg.use.UsageOutputNames(**outputs))


def init_md_from_recorded_md(node: ProvNode, unique_md_id: str,
                             namespace: UniqueValsDict, cfg: ReplayConfig) -> \
                                 UsageVariable:
    """
    initializes and returns a Metadata UsageVariable from a pd.df scraped from
    provenance
    """
    from qiime2 import Metadata
    md_df = node.metadata[unique_md_id]

    def factory():
        return Metadata(md_df)

    return cfg.use.init_metadata(namespace[unique_md_id], factory)


def init_md_from_md(node: ProvNode, param_name: str, md_id: str,
                    namespace: UniqueValsDict, cfg: ReplayConfig) -> \
                        UsageVariable:
    """
    initializes and returns a Metadata UsageVariable with no real data,
    mimicking a user passing md as a .tsv file
    """
    plugin = node.action.plugin
    action = node.action.action_name
    md = cfg.use.init_metadata(namespace[md_id], lambda: None)
    if param_is_metadata_column(cfg, param_name, plugin, action):
        md = cfg.use.get_metadata_column('some', '<column_name>', md)
    return md


def init_md_from_artifacts(md_inf: MetadataInfo, namespace: UniqueValsDict,
                           cfg: ReplayConfig) -> UsageVariable:
    """
    initializes and returns a Metadata UsageVariable with no real data,
    mimicking a user passing md as one or more QIIME 2 Artifacts
    """
    md_files_in = []
    # TODO: confirm this represented correctly w/many art-as-md
    for artif in md_inf.input_artifact_uuids:
        art_as_md = cfg.use.view_as_metadata(artif,
                                             namespace[artif])
        md_files_in.append(art_as_md)
    return cfg.use.merge_metadata('md_from_artifacts', *md_files_in)


def dump_recorded_md_files(node: ProvNode, md_id: str):
    """
    Writes all of the metadata DataFrames recorded for an action to .tsv
    Each action gets its own directory containing relevant md files.
    """
    plugin = node.action.plugin
    action = node.action.action_name
    cwd = pathlib.Path.cwd()
    md_out_fp_base = cwd / 'recorded_metadata'
    action_dir = md_out_fp_base / (plugin + '_' + action)
    try:
        action_dir.mkdir(parents=True)
    except FileExistsError:
        pass

    for md in node.metadata:
        md_df = node.metadata[md]
        out_fp = action_dir / (md_id + '.tsv')
        md_df.to_csv(out_fp, sep='\t')


def param_is_metadata_column(
        cfg: ReplayConfig, param: str, plg: str, action: str) -> bool:
    """
    Returns True if the param name `param` is registered as a MetadataColumn

    TODO: Should we make a tool that can do a simple diff of qiime 2 plugins
    present vs those required?
    """
    plugin = cfg.pm.get_plugin(id=plg)
    try:
        action_f = plugin.actions[action]
    except KeyError:
        raise KeyError('No action currently registered with '
                       'id: "%s".' % (action))
    # HACK, but it works without relying on Q2's type system
    return ('MetadataColumn' in
            str(action_f.signature.parameters[param].qiime_type))
