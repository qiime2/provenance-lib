from __future__ import annotations
import pathlib
from datetime import timedelta
from typing import List, Dict, Tuple, Optional, TypedDict, Union
import warnings
import zipfile

import bibtexparser as bp
from networkx import DiGraph
import yaml

from .checksum_validator import ChecksumDiff, validate_checksums
from .version_parser import get_version

# Alias string as UUID so we can specify types more clearly
UUID = str


def citation_key_constructor(loader, node) -> str:
    """
    A constructor for !cite yaml tags, returning a bibtex key as a str.
    All we need for now is a key string we can match in citations.bib,
    so _we're not parsing these into component substrings_.

    If that need arises in future, these are spec'ed in provenance.py as:
    <domain>|<package>:<version>|[<identifier>|]<index>

    and frequently look like this (note no identifier):
    framework|qiime2:2020.6.0.dev0|0
    """
    value = loader.construct_scalar(node)
    return value


def color_constructor(loader, node) -> str:
    """
    Constructor for !color tags, returning an str.
    Color was a primitive type representing a 3 or 6 digit color hex code,
    matching ^#(?:[0-9a-fA-F]{3}){1,2}$

    Per E. Bolyen,these were unused by any plugins. They were removed in
    e58ed5f8ba453035169d560e0223e6a37774ae08, released in 2019.4
    """
    return loader.construct_scalar(node)


class MetadataInfo(TypedDict):
    """ A static type def for metadata_path_constructor's return value """
    input_artifact_uuids: List[UUID]
    relative_fp: str


def metadata_path_constructor(loader, node) -> MetadataInfo:
    """
    A constructor for !metadata yaml tags, which come in the form
    [<uuid_ref>[,<uuid_ref>][...]:]<relative_filepath>

    Most commonly, we see:
    !metadata 'sample_metadata.tsv'

    In cases where Artifacts are used as metadata, we see:
    !metadata '415409a4-371d-4c69-9433-e3eaba5301b4:feature_metadata.tsv'

    In cases where multiple Artifacts as metadata were merged,
    it is possible for multiple comma-separated uuids to precede the ':'
    !metadata '<uuid1>,<uuid2>,...,<uuidn>:feature_metadata.tsv'

    The metadata files (including "Artifact metadata") are saved in the same
    dir as `action.yaml`. The UUIDs listed must be incorporated into our
    provenance graph as parents, so are returned in list form.
    """
    raw = loader.construct_scalar(node)
    if ':' in raw:
        artifact_uuids, rel_fp = raw.split(':')
        artifact_uuids = artifact_uuids.split(',')
    else:
        artifact_uuids = []
        rel_fp = raw
    return {'input_artifact_uuids': artifact_uuids, 'relative_fp': rel_fp}


def no_provenance_constructor(loader, node) -> MetadataInfo:
    """
    Constructor for !no-provenance tags. These tags are produced when an input
    has no /provenance dir, as is the case with v0 archives that have been
    used in analyses in QIIME2 V1+. They look like this:

    action:
       inputs:
       -   table: !no-provenance '34b07e56-27a5-4f03-ae57-ff427b50aaa1'

    TODO: Add an attribute to this node indicating it is problematic, so it can
    be colored when drawing. Also, to the ProvDAG?
    """
    uuid = loader.construct_scalar(node)
    warnings.warn(f"Artifact {uuid} was created prior to provenance tracking. "
                  + "Provenance data will be incomplete.", UserWarning)
    return uuid


def ref_constructor(loader, node) -> Union[str, List[str]]:
    """
    A constructor for !ref yaml tags. These tags describe yaml values that
    reference other namespaces within the document, using colons to separate
    namespaces. For example:
    !ref 'environment:plugins:sample-classifier'

    At present, ForwardRef tags are only used in the framework to 'link' the
    plugin name to the plugin version and other details in the 'execution'
    namespace of action.yaml

    This constructor explicitly handles this type of !ref by extracting and
    returning the plugin name to simplify parsing, while supporting the return
    of a generic list of 'keys' (e.g. ['environment', 'framework', 'version'])
    in the event ForwardRef is used more broadly in future.
    """
    value = loader.construct_scalar(node)
    keys = value.split(':')
    if keys[0:2] == ['environment', 'plugins']:
        plugin_name = keys[2]
        return plugin_name
    else:
        return keys


def set_constructor(loader, node) -> str:
    """
    A constructor for !set yaml tags, returning a python set object
    """
    value = loader.construct_sequence(node)
    return set(value)


# NOTE: New yaml tag constructors must be added to this registry, or tags will
# raise ConstructorErrors
CONSTRUCTOR_REGISTRY = {
    '!cite': citation_key_constructor,
    '!color': color_constructor,
    '!metadata': metadata_path_constructor,
    '!no-provenance': no_provenance_constructor,
    '!ref': ref_constructor,
    '!set': set_constructor,
    }

for key in CONSTRUCTOR_REGISTRY:
    yaml.SafeLoader.add_constructor(key, CONSTRUCTOR_REGISTRY[key])


class ProvDAG(DiGraph):
    """
    A single-rooted DAG of ProvNode objects, representing a single QIIME 2
    Archive.
    """
    _num_results: int
    _archv_contents: Dict[UUID, ProvNode]
    _archive_md: _ResultMetadata

    # TODO: remove this? replace with a collection of terminal uuids
    @property
    def root_uuid(self) -> UUID:
        """The UUID of the terminal node of one QIIME 2 Archive"""
        return self._archive_md.uuid

    # TODO: remove this? replace with a collection of terminal nodes
    @property
    def root_node(self) -> ProvNode:
        """The terminal ProvNode of one QIIME 2 Archive"""
        return self.get_result(self.root_uuid)

    def get_result(self, uuid) -> ProvNode:
        """Returns a ProvNode from this ProvDAG selected by UUID"""
        return self._archv_contents[uuid]

    def __str__(self) -> str:
        return repr(self._archive_md)

    def __repr__(self) -> str:
        # Traverse DAG, printing UUIDs
        # TODO: Improve this repr to remove id duplication
        r_str = self.__str__() + "\nContains Results:\n"
        uuid_yaml = yaml.dump(self.traverse_uuids())
        r_str += uuid_yaml
        return r_str

    def traverse_uuids(self, node_id: UUID = None) -> \
            Dict[UUID, ProvNode]:
        """ depth-first traversal of this ProvNode's ancestors """
        # Use this DAG's root uuid by default
        node_id = self.root_uuid if node_id is None else node_id
        local_parents = dict()
        if not self.nodes[node_id]['parents']:
            local_parents = {node_id: None}
        else:
            sub_dag = dict()
            parents = self.nodes[node_id]['parents']
            parent_uuids = (list(parent.values())[0] for parent in parents)
            for uuid in parent_uuids:
                sub_dag.update(self.traverse_uuids(uuid))
            local_parents[node_id] = sub_dag
        return local_parents

    def __init__(self, archive_fp: str):
        super().__init__()
        with zipfile.ZipFile(archive_fp) as zf:
            handler = FormatHandler(zf)
            self._archive_md, (self._num_results, self._archv_contents) = \
                handler.parse(zf)

            # Nodes are literally UUIDs. Entire ProvNodes and select other data
            # are stored as attributes.

            # TODO: If our nodes are ProvNodes instead of uuids, do we get
            # these attributes, queryable, "for free"? Do we only get
            # "enhanced" node equality checking? And if so, is that really a
            # value? Related - how does nx.union_some_dags work? If node
            # attributes are .updated, then uuid might make this less painful.
            # Otherwise, we're replacing one ProvNode with another, and we
            # might have to re-implement nx's union logic to preference the
            # non-empty provNode, which I think should be avoided.

            con = self._archv_contents
            node_contents = [
                (n_id, dict(full_ProvNode_payload=con[n_id],
                            type=con[n_id].sem_type,
                            format=con[n_id].format,
                            framework_version=con[n_id].framework_version,
                            archive_version=con[n_id].archive_version,
                            has_provenance=con[n_id].has_provenance,
                            provenance_is_valid=con[n_id].provenance_is_valid,
                            )) for n_id in self._archv_contents]
            self.add_nodes_from(node_contents)

            # Add attributes which only exist if provenance was captured
            for node in self.nodes:
                provnode = self.nodes[node]['full_ProvNode_payload']
                if provnode.has_provenance:
                    action_properties = dict(
                        action_type=provnode.action.action_type,
                        plugin=provnode.action.plugin,
                        parents=provnode.action.parents,
                        runtime=provnode.action.runtime,
                    )
                    self.nodes[node].update(action_properties)
                # TODO: smoketest the following chunk
                if not provnode.provenance_is_valid:
                    self.nodes[node].update({'checksum_diff':
                                             provnode.checksum_diff})

            # NOTE: When parsing v1+ archives, v0 ancestor nodes without
            # tracked provenance (e.g. !no-provenance inputs) are discovered
            # only as parents to the current inputs, and are added to our DAG
            # when we add in-edges to "real" provenance nodes below.

            # As such, dag.nodes[<uuid>] returns an empty dict if the node has
            # no provenance. The has_provenance attribute allows red-flagging
            # of nodes with something like this, even if we end up adding
            # other attributes (e.g. type) to our no-provenance nodes:
            # `if not dag.nodes[<uuid>].get(has_provenance)`

            ebunch = []
            for node_id, data in self.nodes(data=True):
                if data.get('parents'):
                    for parent in data['parents']:
                        type = tuple(parent.keys())[0]
                        parent_uuid = tuple(parent.values())[0]
                        ebunch.append((parent_uuid, node_id,
                                       {'type': type}))
            self.add_edges_from(ebunch)
            # TODO: De-duplicate the graph?
            # Our digraph contains all directories in the archive,
            # and doesn't handle aliases in the same way that q2view does.
            # We'll need to consider the semantics here.


class ProvNode:
    """ One node of a provenance DAG, describing one QIIME 2 Result """

    @property
    def uuid(self) -> UUID:
        return self._result_md.uuid

    @property
    def sem_type(self) -> str:
        return self._result_md.type

    @property
    def format(self) -> Optional[str]:
        return self._result_md.format

    @property
    def archive_version(self) -> int:
        return self._archive_version

    @property
    def framework_version(self) -> str:
        return self._framework_version

    @property
    def has_provenance(self) -> bool:
        return self.archive_version != '0'

    def __init__(self, zf: zipfile,
                 fps_for_this_result: List[pathlib.Path]) -> None:
        """
        Constructs a ProvNode from a zipfile and some filepaths.

        This constructor is intentionally flexible, and will parse any
        files handed to it. It is the responsibility of the ParserVx classes to
        decide what files need to be passed.

        When `checksums.md5` is present, it validates the Archive.
        For Archive formats prior to v5, we assume correctness.
        """
        self.provenance_is_valid = True
        for fp in fps_for_this_result:
            if fp.name == 'VERSION':
                self._archive_version, self._framework_version = \
                    get_version(zf, fp)
            elif fp.name == 'metadata.yaml':
                self._result_md = _ResultMetadata(zf, str(fp))
            elif fp.name == 'action.yaml':
                self.action = _Action(zf, str(fp))
            elif fp.name == 'citations.bib':
                self.citations = _Citations(zf, str(fp))
            elif fp.name == 'checksums.md5':
                # TODO: Test the following chunk
                # Check warnings are as expected
                # Check that our ProvNodes have expected .provenance_is_valid
                diff = validate_checksums(zf)
                if diff != ChecksumDiff({}, {}, {}):
                    # self._result_md may not have been parsed yet, so get uuid
                    root_uuid = pathlib.Path(zf.namelist()[0]).parts[0]
                    warnings.warn(
                        f"Checksums are invalid for Archive{root_uuid}. "
                        "Archive may be corrupt or provenance may be false."
                        f"Files added since archive creation: {diff[0]}"
                        f"Files removed since archive creation: {diff[1]}"
                        f"Files changed since archive creation: {diff[2]}",
                        UserWarning)
                    self.provenance_is_valid = False
                    self.checksum_diff = diff

    def __repr__(self) -> str:
        return f'ProvNode({self.uuid}, {self.sem_type}, fmt={self.format})'

    def __str__(self) -> UUID:
        return f'{self.uuid}'

    def __hash__(self) -> int:
        return hash(self.uuid)

    def __eq__(self, other) -> bool:
        return (self.__class__ == other.__class__
                and self.uuid == other.uuid
                )


class _Action:
    """ Provenance data from action.yaml for a single QIIME 2 Result """

    @property
    def action_id(self) -> str:
        """ the UUID assigned to this Action (not its Results) """
        return self._execution_details['uuid']

    @property
    def action_type(self) -> str:
        """
        The type of Action represented (e.g. Method, Pipeline, etc. )
        Returns Import if an import - this is a useful sentinel for deciding
        what type of action we're parsing (Action vs import)
        """
        return self._action_details['type']

    @property
    def runtime(self) -> timedelta:
        """
        The elapsed run time of the Action, as a datetime object
        """
        end = self._execution_details['runtime']['end']
        start = self._execution_details['runtime']['start']
        return end - start

    @property
    def runtime_str(self) -> str:
        """
        The elapsed run time of the Action, in Seconds and microseconds
        """
        return self._execution_details['runtime']['duration']

    @property
    def action(self) -> str:
        """
        The name of the action itself. Returns 'import' if this is an import.
        """
        action = self._action_details.get('action')
        if self.action_type == 'import':
            action = 'import'
        return action

    @property
    def plugin(self) -> str:
        """
        The plugin which executed this Action. Returns 'framework' if this is
        an import.
        """
        plugin = self._action_details.get('plugin')
        if self.action_type == 'import':
            plugin = 'framework'
        return plugin

    @property
    def parents(self) -> List[Dict[str, UUID]]:
        """
        a list of single-item {Type: UUID} dicts describing this
        action's inputs, and including Artifacts passed as Metadata parameters.

        Returns [] if this "action" is an Import
        """
        inputs = self._action_details.get('inputs')
        parents = [] if inputs is None else inputs

        archives_as_metadata = self._get_artifacts_passed_as_md()
        return parents + archives_as_metadata

    def _get_artifacts_passed_as_md(self, action_details=None) -> \
            List[Dict[str, UUID]]:
        """
        When Artifacts are passed as Metadata, they are captured in action.py's
        action['parameters'], rather than in action['inputs'] with the other
        Artifacts. Replay wouldn't be as usable without these Artifact inputs,
        so our DAG must be able to track them as parents to a given node.

        Figuring out whether there is an Action passed as MD is gross, so this
        function. For example:

        action:
            parameters:
            -   arbitrary_metadata_name: !metadata 'sample_metadata.tsv'
            -   other_metadata: !metadata '4154...301b4:feature_metadata.tsv'

        loads as:

        {'action': {'parameters': [{'some_param': 'foo'},
                                   {'arbitrary_metadata_name':
                                    {'input_artifact_uuids': [],
                                     'relative_fp': 'metadata.tsv'}},
                                   {'other_metadata':
                                    {'input_artifact_uuids': ['4154...301b4'],
                                     'relative_fp': 'metadata.tsv'}},]}}
        We can key into 'parameters', then must iterate over the list of
        parameters capturing dict values that contain UUIDs.

        NOTE: When Actions are passed as MD, Semantic Type data isn't captured,
        so the filler 'artifact_passed_as_metadata' 'Type' created here
        will not match the actual Type of the parent Artifact. The filler type
        should make it possible for a ProvDAG to identify and relabel any
        artifacts passed as metadata with their actual type if needed.
        """
        action_details = action_details if action_details is not None \
            else self._action_details
        artifacts_as_metadata = []
        all_params = action_details.get('parameters')
        if all_params is None:
            return []

        # PEP589 doesn't support isinstance checks against TypedDict objects,
        # and structural pattern matching also relies on isinstance(),
        # so if action['params'] exists, we look for params with a value that
        # matches the yaml_constructors.MetadataInfo spec well enough, and
        # grab any uuids associated with em.
        for param in all_params:
            param_val = list(param.values())[0]
            if isinstance(param_val, dict) \
               and 'input_artifact_uuids' in param_val \
               and 'relative_fp' in param_val:
                artifacts_as_metadata += [
                    {'artifact_passed_as_metadata': uuid} for uuid in
                    param_val['input_artifact_uuids']]

        return artifacts_as_metadata

    def __init__(self, zf: zipfile, fp: str):
        self._action_dict = yaml.safe_load(zf.read(fp))
        self._action_details = self._action_dict['action']
        self._execution_details = self._action_dict['execution']
        self._env_details = self._action_dict['environment']

    def __repr__(self):
        return (f"_Action(action_id={self.action_id}, type={self.action_type},"
                f" plugin={self.plugin}, action={self.action})")


class _Citations:
    """
    citations for a single QIIME 2 Result, as a dict of dicts where each
    inner dictionary represents one citation keyed on the citation's bibtex ID
    """
    def __init__(self, zf: zipfile, fp: str):
        bib_db = bp.loads(zf.read(fp))
        self.citations = {entry['ID']: entry for entry in bib_db.entries}

    def __repr__(self):
        keys = [entry for entry in self.citations]
        return (f"Citations({keys})")


class _ResultMetadata:
    """ Basic metadata about a single QIIME 2 Result from metadata.yaml """
    def __init__(self, zf: zipfile, md_fp: str):
        _md_dict = yaml.safe_load(zf.read(md_fp))
        self.uuid = _md_dict['uuid']
        self.type = _md_dict['type']
        self.format = _md_dict['format']

    def __repr__(self):
        return (f"UUID:\t\t{self.uuid}\n"
                f"Type:\t\t{self.type}\n"
                f"Data Format:\t{self.format}")


class ParserV0():
    """
    Parser for V0 archives. These have no provenance, so we only parse metadata
    """
    version_string = 0
    prov_filenames = ('metadata.yaml', 'VERSION')

    @classmethod
    def get_root_md(self, zf: zipfile.ZipFile) \
            -> _ResultMetadata:
        """ Get archive metadata including root uuid """
        # All files in zf start with root uuid, so we'll grab it from the first
        root_md_fp = pathlib.Path(zf.namelist()[0]).parts[0] + '/metadata.yaml'
        try:
            return _ResultMetadata(zf, root_md_fp)
        except KeyError:
            raise ValueError("Malformed Archive: "
                             "no top-level metadata.yaml file")

    @classmethod
    def parse_prov(self, zf: zipfile.ZipFile) -> \
            Tuple[int, Dict[UUID, ProvNode]]:
        archv_contents = {}
        num_results = 1
        uuid = pathlib.Path(zf.namelist()[0]).parts[0]
        warnings.warn(f"Artifact {uuid} was created prior to provenance" +
                      "tracking. Provenance data will be incomplete.",
                      UserWarning)
        prov_data_fps = [pathlib.Path(uuid) / fp for fp in self.prov_filenames]
        archv_contents[uuid] = ProvNode(zf, prov_data_fps)
        return (num_results, archv_contents)


class ParserV1(ParserV0):
    """
    Parser for V1 archives. These track provenance, so we parse it.
    """
    version_string = 1
    prov_filenames = ('metadata.yaml', 'action/action.yaml', 'VERSION')

    @classmethod
    def parse_prov(self, zf: zipfile.ZipFile) -> \
            Tuple[int, Dict[UUID, ProvNode]]:
        """
        Parses provenance data for one Archive.

        By convention, the filepaths within these Archives begin with:
        <archive_root_uuid>/provenance/...
        archive-root provenance files live directly inside 'provenance'
        e.g: <archive_root_uuid>/provenance/metadata.yaml
        non-root provenance files live inside 'artifacts/<uuid>'
        e.g: <archive_root_uuid>/provenance/artifacts/<uuid>/metadata.yaml
        or <archive_root_uuid>/provenance/artifacts/<uuid>/action/action.yaml
        """
        archv_contents = {}
        num_results = 0

        prov_data_fps = [
            pathlib.Path(fp) for fp in zf.namelist()
            if 'provenance' in fp
            # and any of the filenames above show up in the filepath
            and any(map(lambda x: x in fp, self.prov_filenames))
        ]

        # make a provnode for each UUID
        for fp in prov_data_fps:
            # if no 'artifacts' -> this is provenance for the archive root
            if 'artifacts' not in fp.parts:
                uuid = fp.parts[0]
                prefix = pathlib.Path(uuid) / 'provenance'
            else:
                uuid = self._get_nonroot_uuid(fp)
                prefix = pathlib.Path(*fp.parts[0:4])

            if uuid not in archv_contents:
                fps_for_this_result = [prefix / name
                                       for name in self.prov_filenames]
                num_results += 1
                archv_contents[uuid] = ProvNode(zf, fps_for_this_result)
        return (num_results, archv_contents)

    @classmethod
    def _get_nonroot_uuid(self, fp: pathlib.Path) -> UUID:
        """
        For non-root provenance files, get the Result's uuid from the path
        (avoiding the root Result's UUID which is in all paths)
        """
        if fp.name == 'action.yaml':
            uuid = fp.parts[-3]
        else:
            uuid = fp.parts[-2]
        return uuid


class ParserV2(ParserV1):
    """
    Parser for V2 archives. Directory structure identical to V1
    action.yaml changes to support Pipelines
    """
    version_string = 2
    prov_filenames = ParserV1.prov_filenames


class ParserV3(ParserV2):
    """
    Parser for V3 archives. Directory structure identical to V1 & V2
    action.yaml now supports variadic inputs, so !set tags in action.yaml
    """
    version_string = 3
    prov_filenames = ParserV2.prov_filenames


class ParserV4(ParserV3):
    """
    Parser for V4 archives. Adds citations to dir structure, changes to
    action.yaml incl transformers
    """
    version_string = 4
    prov_filenames = (*ParserV3.prov_filenames, 'citations.bib')


class ParserV5(ParserV4):
    """
    Parser for V5 archives. Adds checksums.md5
    """
    version_string = 5
    prov_filenames = (*ParserV4.prov_filenames, 'checksums.md5')
    # TODO: Add checksum validation (imported from framework) here


class FormatHandler():
    """
    Parses VERSION file data, has a version-specific parser which allows
    for version-safe archive parsing
    """
    _FORMAT_REGISTRY = {
        # NOTE: update for new format versions in qiime2.core.archive.Archiver
        '0': ParserV0,
        '1': ParserV1,
        '2': ParserV2,
        '3': ParserV3,
        '4': ParserV4,
        '5': ParserV5,
    }

    @property
    def archive_version(self):
        return self._archv_vrsn

    @property
    def framework_version(self):
        return self._frmwk_vrsn

    def __init__(self, zf: zipfile.ZipFile):
        self._archv_vrsn, self._frmwk_vrsn = get_version(zf)
        self.parser = self._FORMAT_REGISTRY[self._archv_vrsn]

    def parse(self, zf: zipfile.ZipFile) -> \
            Tuple[_ResultMetadata, Tuple[int, Dict[UUID, ProvNode]]]:
        return (self.parser.get_root_md(zf),
                self.parser.parse_prov(zf))
