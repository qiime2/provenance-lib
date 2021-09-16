from __future__ import annotations
from dataclasses import dataclass
from io import BytesIO
import pathlib
import pandas as pd
from datetime import timedelta
from typing import List, Dict, Mapping, Tuple, Optional
import warnings
import zipfile

import bibtexparser as bp
from networkx import DiGraph
import yaml

from . import checksum_validator
from . import version_parser
from .yaml_constructors import CONSTRUCTOR_REGISTRY, MetadataInfo

# Alias string as UUID so we can specify types more clearly
UUID = str

for key in CONSTRUCTOR_REGISTRY:
    yaml.SafeLoader.add_constructor(key, CONSTRUCTOR_REGISTRY[key])


class ProvDAG(DiGraph):
    """
    A single-rooted DAG of ProvNode objects, representing a single QIIME 2
    Archive.
    """
    @property
    def root_uuid(self) -> UUID:
        """The UUID of the terminal node of one QIIME 2 Archive"""
        return self.parser_results.root_md.uuid

    @property
    def root_node(self) -> ProvNode:
        """The terminal ProvNode of one QIIME 2 Archive"""
        return self.get_result(self.root_uuid)

    def get_result(self, uuid) -> ProvNode:
        """Returns a ProvNode from this ProvDAG selected by UUID"""
        return self.parser_results.archive_contents[uuid]

    def __init__(self, archive_fp: str):
        """
        Create a ProvDAG (digraph) by:
            0. Creating an empty nx.digraph
            1. parsing the raw data from the zip archive
            2. adding nodes with their associated guaranteed data
            3. adding provenance-dependent data to nodes with provenance
            4. Connect nodes with edges
        """
        super().__init__()
        with zipfile.ZipFile(archive_fp) as zf:
            handler = FormatHandler(zf)
            self.parser_results = handler.parse(zf)
            self.provenance_is_valid = self.parser_results.provenance_is_valid
            self.checksum_diff = self.parser_results.checksum_diff

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

            arc_contents = self.parser_results.archive_contents
            node_contents = [
                (n_id, dict(
                    full_ProvNode_payload=arc_contents[n_id],
                    type=arc_contents[n_id].sem_type,
                    format=arc_contents[n_id].format,
                    framework_version=arc_contents[n_id].framework_version,
                    archive_version=arc_contents[n_id].archive_version,
                    has_provenance=arc_contents[n_id].has_provenance,
                    )) for n_id in arc_contents]
            self.add_nodes_from(node_contents)

            # Add attributes which only exist if provenance was captured
            for node in self.nodes:
                provnode = self.nodes[node]['full_ProvNode_payload']
                if provnode.has_provenance:
                    action_properties = dict(
                        action_type=provnode.action.action_type,
                        plugin=provnode.action.plugin,
                        runtime=provnode.action.runtime,
                        parents=provnode.parents,
                    )
                    self.nodes[node].update(action_properties)
                self.nodes[node]['metadata'] = provnode.metadata

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
            # TODO: Handle nested provenance correctly
            # Our digraph contains all directories in the archive,
            # and doesn't handle aliases in the same way that q2view does.
            # We'll need to consider the semantics here.

    def __str__(self) -> str:
        return repr(self.parser_results.root_md)

    def __repr__(self) -> str:
        # Traverse DAG, printing UUIDs
        # TODO: Improve this repr to remove id duplication
        r_str = self.__str__() + "\nContains Results:\n"
        uuid_yaml = yaml.dump(self.traverse_uuids())
        r_str += uuid_yaml
        return r_str

    def _traverse_uuids(self, node_id: UUID = None) -> \
            Mapping[UUID, Optional[ProvNode]]:
        """ depth-first traversal of this ProvNode's ancestors """
        # Use this DAG's root uuid by default
        node_id = self.root_uuid if node_id is None else node_id
        local_parents = dict()
        if not self.nodes[node_id].get('parents'):
            local_parents = {node_id: None}
        else:
            sub_dag = dict()  # type: Dict[UUID, Optional[ProvNode]]
            parents = self.nodes[node_id]['parents']
            parent_uuids = (list(parent.values())[0] for parent in parents)
            for uuid in parent_uuids:
                sub_dag.update(self.traverse_uuids(uuid))
            local_parents[node_id] = sub_dag  # type: ignore
        return local_parents


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
    def archive_version(self) -> str:
        return self._archive_version

    @property
    def framework_version(self) -> str:
        return self._framework_version

    @property
    def has_provenance(self) -> bool:
        return self.archive_version != '0'

    @property
    def metadata(self) -> Optional[Dict[str, pd.DataFrame]]:
        """
        A dict containing {parameter_name: metadata_dataframe} pairs, where
        parameter_name is the registered name of the parameter the Metadata
        or MetadataColumn was passed to.

        Returns {} if this action took in no Metadata or MetadataColumn

        Returns None if this action has no metadata because the archive has no
        provenance.
        """
        md = None
        if hasattr(self, '_metadata'):
            md = self._metadata
        return md

    @property
    def parents(self) -> List[Dict[str, UUID]]:
        """
        a list of single-item {Type: UUID} dicts describing this
        action's inputs, and including Artifacts passed as Metadata parameters.

        Returns [] if this "action" is an Import
        """
        inputs = self.action._action_details.get('inputs')
        parents = [] if inputs is None else inputs

        artifacts_as_metadata = self._artifacts_passed_as_md
        return parents + artifacts_as_metadata

    def __init__(self, zf: zipfile.ZipFile,
                 fps_for_this_result: List[pathlib.Path]) -> None:
        """
        Constructs a ProvNode from a zipfile and some filepaths.

        This constructor is intentionally flexible, and will parse any
        files handed to it. It is the responsibility of the ParserVx classes to
        decide what files need to be passed.
        """
        for fp in fps_for_this_result:
            if fp.name == 'VERSION':
                self._archive_version, self._framework_version = \
                    version_parser.parse_version(zf, fp)
            elif fp.name == 'metadata.yaml':
                self._result_md = _ResultMetadata(zf, str(fp))
            elif fp.name == 'action.yaml':
                self.action = _Action(zf, str(fp))
            elif fp.name == 'citations.bib':
                self.citations = _Citations(zf, str(fp))
            elif fp.name == 'checksums.md5':
                # Handled in ProvDAG
                pass

        # If the _Action constructor finds metadata files, we parse them
        # TODO: This should be a user-facing option, right?
        # Isn't Metadata parsing only useful if we want to use the
        # same metadata for our replay as we did in the original.
        # This would require identical UUIDs, as well as an
        # identical mapping of metadata to those UUIDs.
        # This seems like a neat trick, but not a common use case?
        if self.has_provenance:
            # We need to guard against missing action.yamls here
            # User has already been warned, and provenance flagged as invalid
            if hasattr(self, 'action'):
                all_metadata_fps, self._artifacts_passed_as_md = \
                    self._get_metadata_from_Action()
                self._metadata = self._parse_metadata(zf, all_metadata_fps)

    def _get_metadata_from_Action(
        # TODO: Stop relying on self.action - just pass it in
        self, mock_action_details: Dict[str, List] = None) \
            -> Tuple[Dict[str, str], List[Dict[str, UUID]]]:
        """
        Gathers data related to Metadata and MetadataColumn-based metadata
        files from an in-memory representation of an action.yaml file.

        Specifically:

        - it captures filepath and parameter-name data for _all_
        metadata files, so that these can be located for parsing, and then
        associated with the correct parameters during replay.

        - it captures uuids for all artifacts passed to this action as
        metadata, and associates them with a consistent/identifiable filler
        type (see NOTE below), so they can be included as parents of this node.

        Returns a two-tuple (all_metadata, artifacts_as_metadata) where:
        - all-metadata conforms to {parameter_name: relative_filename}
        - artifacts_as_metadata is a list of single-item dictionaries
        conforming to [{'artifact_passed_as_metadata': <uuid>}, ...]

        By default, this operates on this ProvNode's action._action_details.
        The optional `action_details` parameter is provided only to simplify
        testing, allowing us to pass hardcoded 'action_details' dictionaries.

        Input data looks like this:

        {'action': {'parameters': [{'some_param': 'foo'},
                                   {'arbitrary_metadata_name':
                                    {'input_artifact_uuids': [],
                                     'relative_fp': 'sample_metadata.tsv'}},
                                   {'other_metadata':
                                    {'input_artifact_uuids': ['4154...301b4'],
                                     'relative_fp': 'feature_metadata.tsv'}},
                                   ]
                    }}

        as loaded from this YAML:

        action:
            parameters:
            -   some_param: 'foo'
            -   arbitrary_metadata_name: !metadata 'sample_metadata.tsv'
            -   other_metadata: !metadata '4154...301b4:feature_metadata.tsv'

        NOTE: When Artifacts are passed as Metadata, they are captured in
        action.py's action['parameters'], rather than in action['inputs'] with
        the other Artifacts. As a result, Semantic Type data is not captured.
        This function returns a hardcoded filler 'Type' for all UUIDs
        discovered here: 'artifact_passed_as_metadata'. This will not match the
        actual Type of the parent Artifact, but should make it possible for a
        ProvDAG to identify and relabel any artifacts passed as metadata with
        their actual type if needed. Replay likely wouldn't be achievable
        without these Artifact inputs, so our DAG must be able to track them as
        parents to a given node.
        """
        action_details = mock_action_details \
            if mock_action_details is not None else self.action._action_details
        all_metadata = dict()
        artifacts_as_metadata = []
        if (all_params := action_details.get('parameters')) is not None:
            for param in all_params:
                param_val = list(param.values())[0]
                if isinstance(param_val, MetadataInfo):
                    param_name = list(param)[0]
                    md_fp = param_val.relative_fp
                    all_metadata.update({param_name: md_fp})

                    artifacts_as_metadata += [
                        {'artifact_passed_as_metadata': uuid} for uuid in
                        param_val.input_artifact_uuids]

        return all_metadata, artifacts_as_metadata

    def _parse_metadata(self, zf: zipfile.ZipFile,
                        metadata_fps: Dict[str, str]) -> \
            Dict[str, pd.DataFrame]:
        """
        Parses all metadata files captured from Metadata and MetadataColumns
        (identifiable by !metadata tags) into pd.DataFrames.

        Returns an empty dict if there is no metadata.

        In the future, we may need a simple type that can hold the name of the
        original associated parameter, the type (MetadataColumn or Metadata),
        and the appropriate Series or Dataframe respectively.
        """
        root_uuid = pathlib.Path(zf.namelist()[0]).parts[0]
        pfx = pathlib.Path(root_uuid) / 'provenance'
        if root_uuid == self.uuid:
            pfx = pfx / 'action'
        else:
            pfx = pfx / 'artifacts' / self.uuid / 'action'

        all_md = dict()
        for param_name in metadata_fps:
            filename = str(pfx / metadata_fps[param_name])
            with zf.open(filename) as myfile:
                df = pd.read_csv(BytesIO(myfile.read()), sep='\t')
                all_md.update({param_name: df})

        return all_md

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
    def action_name(self) -> str:
        """
        The name of the action itself. Returns 'import' if this is an import.
        """
        action_name = self._action_details.get('action')
        if self.action_type == 'import':
            action_name = 'import'
        return action_name

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

    def __init__(self, zf: zipfile.ZipFile, fp: str):
        self._action_dict = yaml.safe_load(zf.read(fp))
        self._action_details = self._action_dict['action']
        self._execution_details = self._action_dict['execution']
        self._env_details = self._action_dict['environment']

    def __repr__(self):
        return (f"_Action(action_id={self.action_id}, type={self.action_type},"
                f" plugin={self.plugin}, action={self.action_name})")


class _Citations:
    """
    citations for a single QIIME 2 Result, as a dict of dicts where each
    inner dictionary represents one citation keyed on the citation's bibtex ID
    """
    def __init__(self, zf: zipfile.ZipFile, fp: str):
        bib_db = bp.loads(zf.read(fp))
        self.citations = {entry['ID']: entry for entry in bib_db.entries}

    def __repr__(self):
        keys = [entry for entry in self.citations]
        return (f"Citations({keys})")


class _ResultMetadata:
    """ Basic metadata about a single QIIME 2 Result from metadata.yaml """
    def __init__(self, zf: zipfile.ZipFile, md_fp: str):
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
    # These are files we expect will be present in every QIIME2 archive with
    # this format. "Optional" filenames (like Metadata, which may or may
    # not be present in an archive) should not be included here.
    expected_files = ('metadata.yaml', 'VERSION')  # type: Tuple[str, ...]

    @classmethod
    def _parse_root_md(cls, zf: zipfile.ZipFile, root_uuid: UUID) \
            -> _ResultMetadata:
        """ Get archive metadata including root uuid """
        # All files in zf start with root uuid, so we'll grab it from the first
        root_md_fp = root_uuid + '/metadata.yaml'
        if root_md_fp not in zf.namelist():
            raise ValueError("Malformed Archive: root metadata.yaml file "
                             "misplaced or nonexistent")
        return _ResultMetadata(zf, root_md_fp)

    @classmethod
    def _validate_checksums(cls, zf: zipfile.ZipFile) -> \
            Tuple[bool, Optional[checksum_validator.ChecksumDiff]]:
        """
        V0 archives predate provenance tracking, so
        - provenance_is_valid = False
        - checksum_diff = None
        """
        return (False, None)

    @classmethod
    def parse_prov(cls, zf: zipfile.ZipFile) -> ParserResults:
        archv_contents = {}
        num_results = 1
        # TODO - conditional checksumming
        # if user wants checksum validation:
        # Validate checksums
        provenance_is_valid, checksum_diff = cls._validate_checksums(zf)
        uuid = pathlib.Path(zf.namelist()[0]).parts[0]

        warnings.warn(f"Artifact {uuid} was created prior to provenance" +
                      " tracking. Provenance data will be incomplete.",
                      UserWarning)

        root_md = cls._parse_root_md(zf, uuid)
        prov_data_fps = [pathlib.Path(uuid) / fp for fp in cls.expected_files]
        archv_contents[uuid] = ProvNode(zf, prov_data_fps)

        return ParserResults(
            root_md, num_results, archv_contents, provenance_is_valid,
            checksum_diff
            )


class ParserV1(ParserV0):
    """
    Parser for V1 archives. These track provenance, so we parse it.
    """
    version_string = 1
    expected_files_in_all_nodes: Tuple[str, ...]
    expected_files_root_only: Tuple[str, ...]
    # These are files we expect will be present in every QIIME2 archive with
    # this format. "Optional" filenames (like Metadata, which may or may
    # not be present in an archive) should not be included here.
    expected_files_root_only = tuple()
    expected_files_in_all_nodes = (
        'metadata.yaml', 'action/action.yaml', 'VERSION')

    @classmethod
    def _validate_checksums(cls, zf: zipfile.ZipFile) -> \
            Tuple[bool, Optional[checksum_validator.ChecksumDiff]]:
        """
        Provenance is initially assumed valid because we have no checksums,
        so:
        - provenance_is_valid = False
        - checksum_diff = None
        """
        return (True, None)

    @classmethod
    def parse_prov(cls, zf: zipfile.ZipFile) -> ParserResults:
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

        # TODO - conditional checksumming
        # if user wants checksum validation:
        # Validate checksums
        provenance_is_valid, checksum_diff = cls._validate_checksums(zf)

        prov_data_fps = cls._get_prov_data_fps(
            zf, cls.expected_files_in_all_nodes + cls.expected_files_root_only)
        root_uuid = pathlib.Path(zf.namelist()[0]).parts[0]

        root_md = cls._parse_root_md(zf, root_uuid)

        # make a provnode for each UUID
        for fp in prov_data_fps:
            fps_for_this_result = []
            # if no 'artifacts' -> this is provenance for the archive root
            if 'artifacts' not in fp.parts:
                node_uuid = root_uuid
                prefix = pathlib.Path(node_uuid) / 'provenance'
                root_only_expected_fps = [
                    pathlib.Path(node_uuid) / filename for filename in
                    cls.expected_files_root_only]
                fps_for_this_result += root_only_expected_fps
            else:
                node_uuid = cls._get_nonroot_uuid(fp)
                prefix = pathlib.Path(*fp.parts[0:4])

            if node_uuid not in archv_contents:
                num_results += 1
                fps_for_this_result = [
                    prefix / name for name in cls.expected_files_in_all_nodes]

                # Warn/reset provenance_is_valid if expected files are missing
                files_are_missing = False
                error_contents = "Malformed Archive: "
                for fp in fps_for_this_result:
                    if fp not in prov_data_fps:
                        files_are_missing = True
                        provenance_is_valid = False
                        error_contents += (
                            f"{fp.name} file for node {node_uuid} misplaced "
                            "or nonexistent.\n")

                if(files_are_missing):
                    error_contents += (f"Archive {root_uuid} may be corrupt "
                                       "or provenance may be false.")
                    raise ValueError(error_contents)

                archv_contents[node_uuid] = ProvNode(zf, fps_for_this_result)

        return ParserResults(
            root_md, num_results, archv_contents, provenance_is_valid,
            checksum_diff
        )

    # TODO: We can probably remove this, but keeping it for now because removal
    # breaks the num_results counter (which we can probably also remove)
    @classmethod
    def _get_prov_data_fps(
        cls, zf: zipfile.ZipFile, expected_files: Tuple['str', ...]) -> \
            List[pathlib.Path]:
        return [pathlib.Path(fp) for fp in zf.namelist()
                if 'provenance' in fp
                # and any of the filenames above show up in the filepath
                and any(map(lambda x: x in fp, expected_files))
                ]

    @classmethod
    def _get_nonroot_uuid(cls, fp: pathlib.Path) -> UUID:
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
    # These are files we expect will be present in every QIIME2 archive with
    # this format. "Optional" filenames should not be included here.
    expected_files_in_all_nodes = ParserV1.expected_files_in_all_nodes
    expected_files_root_only = ParserV1.expected_files_root_only


class ParserV3(ParserV2):
    """
    Parser for V3 archives. Directory structure identical to V1 & V2
    action.yaml now supports variadic inputs, so !set tags in action.yaml
    """
    version_string = 3
    # These are files we expect will be present in every QIIME2 archive with
    # this format. "Optional" filenames should not be included here.
    expected_files_in_all_nodes = ParserV2.expected_files_in_all_nodes
    expected_files_root_only = ParserV2.expected_files_root_only


class ParserV4(ParserV3):
    """
    Parser for V4 archives. Adds citations to dir structure, changes to
    action.yaml incl transformers
    """
    version_string = 4
    # These are files we expect will be present in every QIIME2 archive with
    # this format. "Optional" filenames should not be included here.
    # TODO: can we replace this unpacking junk with a + ?
    expected_files_in_all_nodes = (*ParserV3.expected_files_in_all_nodes,
                                   'citations.bib')
    expected_files_root_only = ParserV3.expected_files_root_only


class ParserV5(ParserV4):
    """
    Parser for V5 archives. Adds checksum validation with checksums.md5
    """
    version_string = 5
    # These are files we expect will be present in every QIIME2 archive with
    # this format. "Optional" filenames should not be included here.
    expected_files_root_only = ('checksums.md5', )
    expected_files_in_all_nodes = ParserV4.expected_files_in_all_nodes

    @classmethod
    def _validate_checksums(cls, zf: zipfile.ZipFile) -> \
            Tuple[bool, Optional[checksum_validator.ChecksumDiff]]:
        """
        With v5, we can actually validate checksums, so use checksum_validator
        - provenance_is_valid: bool
        - checksum_diff: Optional[ChecksumDiff], where None only if
            checksums.md5 is missing
        """
        return checksum_validator.validate_checksums(zf)

    @classmethod
    def parse_prov(cls, zf: zipfile.ZipFile) -> ParserResults:
        """
        Parses provenance data for one Archive, applying the local
        _validate_checksums() method to the v1 parser
        """
        return super().parse_prov(zf)


@dataclass
class ParserResults():
    """
    Results generated by a ParserVx
    TODO: Should we drop all the @classmethod garbage and turn parse_prov()
    into an __init__ that makes various versions of these?

    No idea what to call the Parser classes instead, but it might simplify
    things a bit.
    """
    root_md: _ResultMetadata
    num_results: int
    archive_contents: Dict[UUID, ProvNode]
    provenance_is_valid: bool
    checksum_diff: Optional[checksum_validator.ChecksumDiff]


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
        self._archv_vrsn, self._frmwk_vrsn = version_parser.parse_version(zf)
        self.parser = self._FORMAT_REGISTRY[self._archv_vrsn]

    def parse(self, zf: zipfile.ZipFile) -> ParserResults:
        return self.parser.parse_prov(zf)
