import bibtexparser as bp
from bibtexparser.bwriter import BibTexWriter
import networkx as nx
import os
import pathlib
import pkg_resources
import re
from collections import UserDict
from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Set

from ._archive_parser import ProvNode
from .parse import ProvDAG, UUID
from .usage_drivers import DRIVER_CHOICES, SUPPORTED_USAGE_DRIVERS, Usage
from .util import FileName, camel_to_snake
from .yaml_constructors import MetadataInfo

from qiime2.sdk import PluginManager
from qiime2.sdk.usage import UsageVariable


# TODO: NEXT DOIs for common things

@dataclass(frozen=False)
class ReplayConfig():
    use: Usage
    use_recorded_metadata: bool
    pm: PluginManager = PluginManager()
    md_context_has_been_printed: bool = False
    no_provenance_context_has_been_printed: bool = False
    verbose: bool = False


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

    Best practice is generally to add the UUID: variable-name pair to this,
    create the usage variable using the stored name,
    then store the usage variable in a separate {UUID: UsagVar}. This
    ensures that UsageVariable.name is unique, preventing namespace collisions.
    NamespaceCollections (below) exist to group these related structures.

    Note: it's not necessary (and may break the mechanism of uniqueness here)
    to maintain parity between variable names in this namespace and in the
    usage variable store. The keys in both stores, however, must match.
    """
    def __setitem__(self, key: UUID, item: str) -> None:
        unique_item = self._uniquify(item)
        return super().__setitem__(key, unique_item)

    def _uniquify(self, var_name: str) -> str:
        """
        Appends _<some_int> to var_name, such that the returned name won't
        collide with any variable-name values that already exist in the dict.
        """
        some_int = 0
        unique_name = f"{var_name}_{some_int}"
        values = self.data.values()
        # no-prov nodes are stored with angle brackets around them, but
        # those brackets shouldn't be considered on uniqueness check
        while unique_name in values or f'<{unique_name}>' in values:
            some_int += 1
            unique_name = f"{var_name}_{some_int}"
        return unique_name

    def get_key(self, value: str):
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

    def wrap_val_in_angle_brackets(self, key: UUID):
        super().__setitem__(key, f'<{self.data[key]}>')


@dataclass(frozen=False)
class NamespaceCollections:
    usg_var_namespace: UsageVarsDict = field(default_factory=UsageVarsDict)
    usg_vars: Dict[UUID, UsageVariable] = field(default_factory=dict)
    action_namespace: Set[str] = field(default_factory=set)


def replay_fp(in_fp: FileName, out_fp: FileName,
              usage_driver_name: DRIVER_CHOICES,
              validate_checksums: bool = True,
              parse_metadata: bool = True,
              use_recorded_metadata: bool = False,
              verbose: bool = False):
    """
    One-shot replay from a filepath string, through a ProvDAG to a written
    executable
    """
    if use_recorded_metadata and not parse_metadata:
        raise ValueError(
            "Metadata not parsed for replay. Re-run with parse_metadata = "
            "True or use_recorded_metadata = False")
    dag = ProvDAG(in_fp, validate_checksums, parse_metadata, verbose)
    replay_provdag(dag, out_fp, usage_driver_name, use_recorded_metadata,
                   verbose)


def replay_provdag(dag: ProvDAG, out_fp: FileName,
                   usage_driver: DRIVER_CHOICES,
                   use_recorded_metadata: bool = False,
                   verbose: bool = False):
    """
    Renders usage examples describing a ProvDAG, producing an interface-
    specific executable.
    """
    if use_recorded_metadata and not dag.cfg.parse_study_metadata:
        raise ValueError(
            "Metadata not captured for replay. Re-parse metadata, or set "
            "use_recorded_metadata to False")

    cfg = ReplayConfig(use=SUPPORTED_USAGE_DRIVERS[usage_driver](),
                       use_recorded_metadata=use_recorded_metadata,
                       verbose=verbose)
    build_usage_examples(dag, cfg)
    output = cfg.use.render()
    with open(out_fp, mode='w') as out_fh:
        out_fh.write(output)


def group_by_action(dag: ProvDAG, nodes: Iterator[UUID]) -> ActionCollections:
    """
    Provenance is organized around outputs, but replay cares about actions.
    This groups the nodes from a DAG by action, returning an ActionCollections
    aggregating the outputs related to each action.

    Takes an iterator of UUIDs, allowing us to influence the ordering of the
    grouping. TODO: We should probably just lock in the topological sort here?

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
    usg_ns = NamespaceCollections()

    # TODO: This could probably be added to the dag as a property or method
    # to enable memoization. Possible inside group_by_action? The only shift
    # will be that group_by_action would have to take the collapsed view as arg
    sorted_nodes = nx.topological_sort(dag.collapsed_view)
    actions = group_by_action(dag, sorted_nodes)

    for node_id in actions.no_provenance_nodes:
        n_data = dag.get_node_data(node_id)
        build_no_provenance_node_usage(n_data, node_id, usg_ns, cfg)

    for action_id in (std_actions := actions.std_actions):
        some_node_id_from_this_action = next(iter(std_actions[action_id]))
        n_data = dag.get_node_data(some_node_id_from_this_action)
        if n_data.action.action_type == 'import':
            build_import_usage(n_data, usg_ns, cfg)
        else:
            build_action_usage(n_data, usg_ns, std_actions, action_id, cfg)


def build_no_provenance_node_usage(node: Optional[ProvNode],
                                   uuid: UUID,
                                   ns: NamespaceCollections,
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
        # the node is a !no-provenance input and we have only UUID
        var_name = 'no-provenance-node'
    else:
        var_name = camel_to_snake(node.type)
    ns.usg_var_namespace.update({uuid: var_name})
    ns.usg_var_namespace.wrap_val_in_angle_brackets(uuid)

    # Make a usage variable for downstream consumption
    empty_var = cfg.use.usage_variable(
        ns.usg_var_namespace[uuid], lambda: None, 'artifact')
    ns.usg_vars.update({uuid: empty_var})

    # Log the no-prov node
    cfg.use.comment(f"{uuid}   {ns.usg_vars[uuid].to_interface_name()}")


def build_import_usage(node: ProvNode,
                       ns: NamespaceCollections,
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
    format_id = node._uuid + '_f'
    ns.usg_var_namespace.update({format_id: camel_to_snake(node.type) + '_f'})
    format_for_import = cfg.use.init_format(
        ns.usg_var_namespace[format_id], lambda: None)

    ns.usg_var_namespace.update({node._uuid: camel_to_snake(node.type)})
    use_var = cfg.use.import_from_format(
        ns.usg_var_namespace[node._uuid], node.type, format_for_import)
    ns.usg_vars.update({node._uuid: use_var})


def build_action_usage(node: ProvNode,
                       ns: NamespaceCollections,
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
    plg_action_name = uniquify_action_name(plugin, action, ns.action_namespace)

    inputs = {}
    for input_name, uuids in node.action.inputs.items():
        # Some optional inputs take None as a default
        if uuids is not None:
            # Some inputs take collections of input strings, so:
            if type(uuids) is str:
                inputs.update({input_name: ns.usg_vars[uuids]})
            else:  # it's a collection
                input_vars = []
                for uuid in uuids:
                    input_vars.append(ns.usg_vars[uuid])
                inputs.update({input_name: input_vars})

    # Process outputs before params so we can access the unique output name
    # from the namespace when dumping metadata to files below
    raw_outputs = std_actions[action_id].items()
    outputs = {}
    for uuid, output_name in raw_outputs:
        ns.usg_var_namespace.update({uuid: output_name})
        uniquified_output_name = ns.usg_var_namespace[uuid]
        outputs.update({output_name: uniquified_output_name})

    for param_name, param_val in node.action.parameters.items():
        # We can currently assume that None arguments are only passed to params
        # as default values, so we can skip these parameters entirely in replay
        if param_val is None:
            continue

        if isinstance(param_val, MetadataInfo):
            unique_md_id = ns.usg_var_namespace[node._uuid] + '_' + param_name
            ns.usg_var_namespace.update(
                {unique_md_id: camel_to_snake(param_name)})
            md_fn = ns.usg_var_namespace[unique_md_id] + '.tsv'
            dump_recorded_md_file(node, plg_action_name, param_name, md_fn)

            if cfg.use_recorded_metadata:
                md = init_md_from_recorded_md(
                    node, unique_md_id, ns.usg_var_namespace, cfg)
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

                if not param_val.input_artifact_uuids:
                    md = init_md_from_md_file(node, param_name, unique_md_id,
                                              ns.usg_var_namespace, cfg)
                else:
                    md = init_md_from_artifacts(param_val, ns, cfg)

            param_val = md
        inputs.update({param_name: param_val})

    usg_var = cfg.use.action(
        cfg.use.UsageAction(plugin_id=plugin, action_id=action),
        cfg.use.UsageInputs(**inputs),
        cfg.use.UsageOutputNames(**outputs))

    # write the usage vars into the UsageVars dict so we can use em downstream
    for res in usg_var:
        uuid_key = ns.usg_var_namespace.get_key(value=res.name)
        ns.usg_vars[uuid_key] = res


def init_md_from_recorded_md(node: ProvNode, unique_md_id: str,
                             namespace: UsageVarsDict, cfg: ReplayConfig) -> \
                                 UsageVariable:
    """
    initializes and returns a Metadata UsageVariable from a pandas.DataFrame
    scraped from provenance

    Raises a ValueError if the node has no metadata

    TODO: If we decide to "touchless" replay with recorded metadata, we needn't
    render, but if replay with recorded metadata isn't touchless (i.e. if it
    also writes a rendered executable), we'll need to render Python
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

    def factory():  # pragma: no cover
        from qiime2 import Metadata
        return Metadata(md_df)

    return cfg.use.init_metadata(namespace[unique_md_id], factory)


def init_md_from_md_file(node: ProvNode, param_name: str, md_id: str,
                         ns: UsageVarsDict, cfg: ReplayConfig) -> \
        UsageVariable:
    """
    initializes and returns a Metadata UsageVariable with no real data,
    mimicking a user passing md as a .tsv file
    """
    plugin = node.action.plugin
    action = node.action.action_name
    md = cfg.use.init_metadata(ns[md_id], lambda: None)
    if param_is_metadata_column(cfg, param_name, plugin, action):
        mdc_id = node._uuid + '_mdc'
        mdc_name = ns[md_id] + '_mdc'
        ns.update({mdc_id: mdc_name})
        md = cfg.use.get_metadata_column(ns[mdc_id], '<column_name>', md)
    return md


def init_md_from_artifacts(md_inf: MetadataInfo,
                           ns: NamespaceCollections,
                           cfg: ReplayConfig) -> UsageVariable:
    """
    initializes and returns a Metadata UsageVariable with no real data,
    mimicking a user passing one or more QIIME 2 Artifacts as metadata

    We expect these usage vars are already in the namespace as artifacts if
    we're reading them in as metadata.
    TODO: Test how no-prov nodes affect this - esp mixed.
    """
    if not md_inf.input_artifact_uuids:
        raise ValueError("This funtion should not be used if"
                         "MetadataInfo.input_artifact_uuids is empty.")
    md_files_in = []
    for artif_id in md_inf.input_artifact_uuids:
        amd_id = artif_id + '_a'
        var_name = ns.usg_vars[artif_id].name + '_a'
        if amd_id not in ns.usg_var_namespace:
            ns.usg_var_namespace.update({amd_id: var_name})
            art_as_md = cfg.use.view_as_metadata(ns.usg_var_namespace[amd_id],
                                                 ns.usg_vars[artif_id])
            ns.usg_vars.update({amd_id: art_as_md})
        else:
            art_as_md = ns.usg_vars[amd_id]
        md_files_in.append(art_as_md)
    if len(md_inf.input_artifact_uuids) > 1:
        # We can't uniquify this normally, because one uuid can be merged with
        # combinations of others. One UUID does not a unique merge-id make.
        merge_id = '-'.join(md_inf.input_artifact_uuids)
        ns.usg_var_namespace.update({merge_id: 'merged_artifacts'})
        merged_md = cfg.use.merge_metadata(ns.usg_var_namespace[merge_id],
                                           *md_files_in)
        ns.usg_vars.update({merge_id: merged_md})
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


def collect_citations(dag: ProvDAG, deduped: bool = True) -> \
        bp.bibdatabase.BibDatabase:
    """
    Returns a BibDatabase of all unique citations from a ProvDAG.

    If deduped, collect_citations will attempt more extensive deduplication
    of documents, e.g. by comparing DOI fields.
    """
    bdb = bp.bibdatabase.BibDatabase()
    cits = []
    for n_id in dag:
        p_node = dag.get_node_data(n_id)
        # Skip no-prov nodes, which never have citations anyway
        if p_node is not None:
            cit = list(p_node.citations.values())
            cits.extend(cit)
    if deduped:
        cits = dedupe_citations(cits)
    bdb.entries = cits
    return bdb


def dedupe_citations(citations: List[Dict]) -> List[Dict]:
    """
    Heuristic attempts to reduce duplication in citations lists.
    E.g. capturing only one citation per DOI, ensuring one framework citation
    """
    dd_cits = []
    fw_cited = False
    doi_set = set()
    for entry in citations:
        # Write a single hardcoded framework citation
        if 'framework|qiime2' in (id := entry['ID']):
            if not fw_cited:
                root = pkg_resources.resource_filename('provenance_lib', '.')
                root = os.path.abspath(root)
                path = os.path.join(root, 'q2_citation.bib')
                with open(path) as bibtex_file:
                    q2_entry = bp.load(bibtex_file).entries.pop()

                q2_entry['ID'] = id
                dd_cits.append(q2_entry)
                fw_cited = True
            continue

        # Keep every entry without a doi
        if (doi := entry.get('doi')) is None:
            dd_cits.append(entry)
        # Keep one entry per non-framework doi
        else:
            if doi not in doi_set:
                dd_cits.append(entry)
                doi_set.add(doi)

    return dd_cits


def write_citations(dag: ProvDAG, out_fp: FileName, deduped: bool = True):
    """
    Writes a .bib file representing all unique citations from a ProvDAG to disk

    If deduped, collect_citations will attempt some heuristic deduplication
    of documents, e.g. by comparing DOI fields, which may reduce manual
    curation of reference lists.
    """
    bib_db = collect_citations(dag, deduped=deduped)
    if bib_db.entries_dict == {}:
        bib_db = "No citations were recorded for this file."
        with open(out_fp, 'w') as bibfile:
            bibfile.write(bib_db)
    else:
        with open(out_fp, 'w') as bibfile:
            bibfile.write(BibTexWriter().write(bib_db))
