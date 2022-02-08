import networkx as nx
import pathlib
import re
from collections import UserDict
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Literal, Optional, Set, Union

from .archive_parser import ProvNode
from .parse import ProvDAG, UUID
from .util import FileName
from .yaml_constructors import MetadataInfo

from q2cli.core.usage import CLIUsage
from qiime2.plugins import ArtifactAPIUsage
from qiime2.sdk import PluginManager
from qiime2.sdk.usage import Usage, UsageVariable


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

    def init_metadata(self, name, factory):
        var = super().init_metadata(name, factory)
        self._update_imports(from_='qiime2', import_='Metadata')
        input_fp = var.to_interface_name()
        lines = [
            '# NOTE: You may substitute already-loaded Metadata for the '
            'following,\n# or cast a pandas.DataFrame to Metadata as needed.\n'
            f'{input_fp} = Metadata.load(<your metadata filepath>)',
            '',
        ]
        self._add(lines)
        return var


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
            line = self.INDENT + (
                "# TODO: The following parameter name was not found in "
                "your current\n  # QIIME 2 environment. This may occur "
                "when the plugin version you have\n  # installed does not "
                "match the version used in the original analysis.\n  # "
                "Please see the docs and correct the parameter name "
                "before running.\n")
            cli_name = re.sub('_', '-', param_name)
            line += self.INDENT + '--?-' + cli_name + ' ' + str(value)
            line += ' \\'
            self.recorder.append(line)


DRIVER_CHOICES = Literal['python3', 'cli']
SUPPORTED_USAGE_DRIVERS = {
    'python3': ReplayPythonUsage,
    'cli': ReplayCLIUsage,
}
DRIVER_NAMES = list(SUPPORTED_USAGE_DRIVERS.keys())


@dataclass(frozen=False)
class ReplayConfig():
    use: Usage
    use_recorded_metadata: bool
    pm: PluginManager = PluginManager()
    md_context_has_been_printed: bool = False
    no_provenance_context_has_been_printed: bool = False


@dataclass(frozen=False)
class ActionCollections():
    """
    std_actions are all normal, provenance-tracked q2 actions, arranged like:
    {<action_id>: {<output_node_uuid>: 'output_name',
                   <output_node_2_uuid:> 'output_name_2'},
     <action_2_id> : ...
     }

    no_provenance_nodes can't be organized by action, and in some cases we
    don't know anything but UUID for them, so we can fit what we need in a list
    """
    std_actions: Dict[UUID, Dict[UUID, str]] = field(default_factory=dict)
    no_provenance_nodes: List[UUID] = field(default_factory=list)


class UsageVarsDict(UserDict):
    """
    A dict where values are also unique. Used here as a UUID-queryable
    "namespace" of strings that will be evaluated into python variable names.
    Non-unique values would cause namespace collisions.

    For consistency and simplicity, all str values are suffixed with _n when
    added, such that n is some int. When potentially colliding values are
    added, n is incremented as needed until collision is avoided.
    UsageVarsDicts mutate ALL str values they receive.

    This dict explicitly supports the storage of variable-name strings,
    and of the UsageVariables that correspond to those strings.

    Best practice is generally to add the UUID: variable-name pair to the dict,
    create the usage variable using the name stored in the dict,
    then replace the variable-name with the related UsageVariable. This
    ensures that UsageVariable.name is unique, preventing namespace collisions.

    .get_key exists to support this use case, by enabling reverse lookup
    """
    def __setitem__(self, key: UUID, item: Union[str, UsageVariable]) -> None:
        unique_item = item
        if isinstance(item, str):
            unique_item = self._uniquify(item)
        return super().__setitem__(key, unique_item)

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

    def get_key(self, value: Union[str, UsageVariable]):
        """
        Given some value in the dict, returns its key
        Results are predictable due to the uniqueness of dict values.

        Raises KeyError if search value does not exist.

        NOTE: If this proves too slow at scale, we can pivot to storing a
        second (reversed) dict for hashed lookups
        """
        for key, val in self.items():
            if value == val:
                return key
        raise KeyError(f"passed value '{value}' does not exist in this dict.")


def replay_fp(in_fp: FileName, out_fp: FileName,
              usage_driver_name: DRIVER_CHOICES,
              validate_checksums: bool = True,
              parse_metadata: bool = True,
              use_recorded_metadata: bool = False):
    """
    One-shot replay from a filepath string, through a ProvDAG to a written
    executable
    """
    if use_recorded_metadata and not parse_metadata:
        raise ValueError(
            "Metadata not parsed for replay. Re-run with parse_metadata = "
            "True or use_recorded_metadata = False")
    dag = ProvDAG(in_fp, validate_checksums, parse_metadata)
    replay_provdag(dag, out_fp, usage_driver_name, use_recorded_metadata)


def replay_provdag(dag: ProvDAG, out_fp: FileName,
                   usage_driver: DRIVER_CHOICES,
                   use_recorded_metadata: bool = False):
    """
    Renders usage examples describing a ProvDAG, producing an interface-
    specific executable.
    """
    if use_recorded_metadata and not dag.cfg.parse_study_metadata:
        raise ValueError(
            "Metadata not captured for replay. Re-parse metadata, or set "
            "use_recorded_metadata to False")

    cfg = ReplayConfig(use=SUPPORTED_USAGE_DRIVERS[usage_driver](),
                       use_recorded_metadata=use_recorded_metadata)
    build_usage_examples(dag, cfg)
    output = cfg.use.render()
    with open(out_fp, mode='w') as out_fh:
        out_fh.write(output)


def group_by_action(dag: ProvDAG, nodes: Iterator[UUID]) -> ActionCollections:
    """
    Provenance is organized around outputs, but replay cares about actions.
    This groups the nodes from a DAG by action, returning a dict of dicts
    aggregating the outputs related to each action:

    In cases where a captured output_name is unavailable, we substitute the
    output data's Semantic Type, snake-cased because it will be used as
    a variable name if this data is rendered by ArtifactAPIUsage.
    """
    actions = ActionCollections()
    for node_id in nodes:
        if dag.node_has_provenance(node_id):
            data = dag.get_node_data(node_id)
            action_id = data.action._execution_details['uuid']
            # neither imports nor older archive versions track output-names
            if (o_n := data.action.output_name) is not None:
                output_name = o_n
            else:
                output_name = camel_to_snake(data.type)

            try:
                actions.std_actions[action_id].update({node_id: output_name})
            except KeyError:
                actions.std_actions[action_id] = {node_id: output_name}
        else:
            actions.no_provenance_nodes.append(node_id)
    return actions


def build_usage_examples(dag: ProvDAG, cfg: ReplayConfig):
    """
    Builds a chained usage example representing the analysis `dag`.
    """
    actions_namespace = set()  # type: Set[str]
    usg_var_namespace = UsageVarsDict()

    sorted_nodes = nx.topological_sort(dag.collapsed_view)
    actions = group_by_action(dag, sorted_nodes)

    for node_id in actions.no_provenance_nodes:
        n_data = dag.get_node_data(node_id)
        build_no_provenance_node_usage(
            n_data, node_id, usg_var_namespace, cfg)

    for action_id in (std_actions := actions.std_actions):
        some_node_id_from_this_action = next(iter(std_actions[action_id]))
        n_data = dag.get_node_data(some_node_id_from_this_action)
        if n_data.action.action_type == 'import':
            build_import_usage(n_data, usg_var_namespace, cfg)
        else:
            build_action_usage(n_data, usg_var_namespace, actions_namespace,
                               std_actions, action_id, cfg)


def build_no_provenance_node_usage(node: Optional[ProvNode],
                                   uuid: UUID,
                                   usg_var_namespace: UsageVarsDict,
                                   cfg: ReplayConfig):
    """
    Given a ProvNode (with no provenance), does something useful with it.
    Returns nothing, modifying the passed usage instance in place.

    # Basically:
    use.comment("Some context")
    use.comment("no-provenance nodes and descriptions")

    TODO: This function's signature is messy because it may receive a ProvNode
    or None (the result of dag.get_node_data). None is used, because some dag
    nodes don't actually have underlying ProvNodes. Consider refactoring
    ProvNode so that the minimal node has only a UUID. This would probably
    require properties with Optional returns and more if not None checks,
    but the semantics feel pretty good. A node is, at least, a UUID, after all.
    """
    if not cfg.no_provenance_context_has_been_printed:
        cfg.no_provenance_context_has_been_printed = True
        cfg.use.comment(
            "One or more nodes have no provenance, so full replay is "
            "impossible. Any\ncommands we were able to reconstruct have been "
            "rendered, with the string\ndescriptions below replacing actual "
            "inputs.")
        cfg.use.comment(
            "Original Node ID                       String Description")
    if node is None:
        # This occurs when the node is known only from a child node's prov,
        # and we have no information beyond UUID
        usg_var_namespace.update({uuid: 'no-provenance-node'})
    else:
        usg_var_namespace.update({uuid: camel_to_snake(node.type)})
    cfg.use.comment(f"{uuid}   {usg_var_namespace[uuid]}")


def build_import_usage(node: ProvNode,
                       usg_var_namespce: UsageVarsDict,
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
    usg_var_namespce.update({node._uuid: camel_to_snake(node.type)})
    format_for_import = cfg.use.init_format('<your data here>', lambda: None)
    use_var = cfg.use.import_from_format(
        usg_var_namespce[node._uuid], node.type, format_for_import)
    usg_var_namespce.update({node._uuid: use_var})


def build_action_usage(node: ProvNode,
                       namespace: UsageVarsDict,
                       action_namespace: set,
                       std_actions: Dict[UUID, Dict[UUID, str]],
                       action_id: UUID,
                       cfg: ReplayConfig):
    """
    Adds an action usage example to use for some ProvNode.
    Returns nothing, modifying the passed usage instance in place.

    use.action(
        use.UsageAction(plugin_id='diversity_lib',
                        action_id='pielou_evenness'),
        use.UsageInputs(table=ft),
        use.UsageOutputNames(vector='pielou_vector')
    )
    """
    command_specific_md_context_has_been_printed = False
    plugin = node.action.plugin
    action = node.action.action_name
    plg_action_name = uniquify_action_name(plugin, action, action_namespace)

    inputs = {}
    for k, v in node.action.inputs.items():
        # Some optional params take None as a default
        if v is not None:
            inputs.update({k: namespace[v]})

    # Process outputs before params so we can access the unique output name
    # from the namespace when dumping metadata to files below
    raw_outputs = std_actions[action_id].items()
    outputs = {}
    for k, v in raw_outputs:
        namespace.update({k: v})
        uniquified_v = namespace[k]
        outputs.update({v: uniquified_v})

    for k, v in node.action.parameters.items():
        if isinstance(v, MetadataInfo):
            unique_md_id = namespace[node._uuid] + '_' + k
            namespace.update({unique_md_id: camel_to_snake(k)})
            md_fn = namespace[unique_md_id] + '.tsv'
            dump_recorded_md_file(node, plg_action_name, k, md_fn)

            if cfg.use_recorded_metadata:
                md = init_md_from_recorded_md(
                    node, unique_md_id, namespace, cfg)
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

                if not command_specific_md_context_has_been_printed:
                    fp = f'recorded_metadata/{plg_action_name}/'
                    cfg.use.comment(
                        "The following command may have received additional "
                        "metadata .tsv files.\nTo confirm you have covered "
                        "your metadata needs adequately, review the original\n"
                        f"metadata, saved at '{fp}'\n")

                if not v.input_artifact_uuids:
                    md = init_md_from_md_file(
                        node, k, unique_md_id, namespace, cfg)
                else:
                    md = init_md_from_artifacts(v, namespace, cfg)

            v = md
        inputs.update({k: v})

    usg_var = cfg.use.action(
        cfg.use.UsageAction(plugin_id=plugin, action_id=action),
        cfg.use.UsageInputs(**inputs),
        cfg.use.UsageOutputNames(**outputs))

    # Replace variable names with built UsageVariables to allow chaining
    for res in usg_var:
        uuid_key = namespace.get_key(value=res.name)
        namespace[uuid_key] = res


def init_md_from_recorded_md(node: ProvNode, unique_md_id: str,
                             namespace: UsageVarsDict, cfg: ReplayConfig) -> \
                                 UsageVariable:
    """
    initializes and returns a Metadata UsageVariable from a pandas.DataFrame
    scraped from provenance

    Raises a ValueError if the node has no metadata

    TODO: If we decide to "touchless" replay with recorded metadata, we needn't
    render, but if replay with recorded metadat isn't touchless (i.e. if it
    also writes a rendered executable), we we'll need to render Python
    differently (e.g. with an actual filepath, not the current "you have
    options" comment). This is probably easiest with another variant driver
    """
    if not node.metadata:
        raise ValueError(
            'This function should only be called if the node has metadata.')
    # TODO: If this convention is real, we should probably implement it as a
    # method on the UsageVarsDict (for metadata at least)
    parameter_name = namespace[unique_md_id][:-2]
    md_df = node.metadata[parameter_name]

    def factory():
        from qiime2 import Metadata
        return Metadata(md_df)

    return cfg.use.init_metadata(namespace[unique_md_id], factory)


def init_md_from_md_file(node: ProvNode, param_name: str, md_id: str,
                         namespace: UsageVarsDict, cfg: ReplayConfig) -> \
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


def init_md_from_artifacts(md_inf: MetadataInfo, namespace: UsageVarsDict,
                           cfg: ReplayConfig) -> UsageVariable:
    """
    initializes and returns a Metadata UsageVariable with no real data,
    mimicking a user passing one or more QIIME 2 Artifacts as metadata

    We expect these usage vars are already in the namespace, if we're reading
    them in as metadata.
    TODO: Test how no-prov nodes affect this - esp mixed.
    """
    if not md_inf.input_artifact_uuids:
        raise ValueError("This funtion should not be used if"
                         "MetadataInfo.input_artifact_uuids is empty.")
    md_files_in = []
    for artif in md_inf.input_artifact_uuids:
        art_as_md = cfg.use.view_as_metadata(namespace[artif].name,
                                             namespace[artif])
        md_files_in.append(art_as_md)
    if len(md_inf.input_artifact_uuids) > 1:
        art_as_md = cfg.use.merge_metadata('merged_artifacts', *md_files_in)
    return art_as_md


def dump_recorded_md_file(
        node: ProvNode, action_name: str, md_id: str, fn: str):
    """
    Writes one metadata DataFrame passed to an action to .tsv
    Each action gets its own directory containing relevant md files.

    Raises a ValueError if the node has no metadata
    """
    if node.metadata is None:
        raise ValueError(
            'This function should only be called if the node has metadata.')

    cwd = pathlib.Path.cwd()
    md_out_fp_base = cwd / 'recorded_metadata'
    action_dir = md_out_fp_base / action_name
    action_dir.mkdir(parents=True, exist_ok=True)

    md_df = node.metadata[md_id]
    out_fp = action_dir / (fn)
    md_df.to_csv(out_fp, sep='\t', index=False)


def param_is_metadata_column(
        cfg: ReplayConfig, param: str, plg: str, action: str) -> bool:
    """
    Returns True if the param name `param` is registered as a MetadataColumn
    """
    try:
        plugin = cfg.pm.get_plugin(id=plg)
    except KeyError as e:
        msg = (re.sub("'", "", str(e)) +
               ' Visit library.qiime2.org to find plugins.')
        raise KeyError(msg)

    try:
        action_f = plugin.actions[action]
    except KeyError:
        raise KeyError(f'No action currently registered with id: {action}.')

    try:
        param_spec = action_f.signature.parameters[param]
    except KeyError:
        raise KeyError(f'No parameter currently registered with id: {param}')

    # HACK, but it works without relying on Q2's type system
    return ('MetadataColumn' in str(param_spec.qiime_type))


def uniquify_action_name(plugin: str, action: str, action_nmspace: set) -> str:
    """
    Creates a unique name by concatenating plugin_action_<counter>,
    and adds the name to action_namespace before returning it
    """
    counter = 0
    plg_action_name = f'{plugin}_{action}_{counter}'
    while plg_action_name in action_nmspace:
        counter += 1
        plg_action_name = f'{plugin}_{action}_{counter}'
    action_nmspace.add(plg_action_name)
    return plg_action_name


def camel_to_snake(name: str) -> str:
    """
    There are more comprehensive and faster ways of doing this (incl compiling)
    but it handles acronyms in semantic types nicely
    e.g. EMPSingleEndSequences -> emp_single_end_sequences
    c/o https://stackoverflow.com/a/1176023/9872253
    """
    # this will frequently be called on QIIME type expressions, so drop [ and ]
    name = re.sub(r'[\[\]]', '', name)
    # camel to snake
    name = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1_\2', name).lower()
