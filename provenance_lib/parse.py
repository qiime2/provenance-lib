from __future__ import annotations
from dataclasses import dataclass
from io import BytesIO
import pathlib
import pandas as pd
from datetime import timedelta
from typing import List, Dict, Set, Tuple, Optional
import warnings
import zipfile

import bibtexparser as bp
import networkx as nx
from networkx.classes.reportviews import NodeView
import yaml

from . import checksum_validator
from . import version_parser
from .yaml_constructors import CONSTRUCTOR_REGISTRY, MetadataInfo

# Alias string as UUID so we can specify types more clearly
UUID = str

for key in CONSTRUCTOR_REGISTRY:
    yaml.SafeLoader.add_constructor(key, CONSTRUCTOR_REGISTRY[key])


@dataclass(frozen=True)
class Config():
    perform_checksum_validation: bool = True
    parse_study_metadata: bool = False


@dataclass
class ParserResults():
    """
    Results generated by a ParserVx
    """
    root_md: _ResultMetadata
    archive_contents: Dict[UUID, ProvNode]
    provenance_is_valid: checksum_validator.ValidationCodes
    checksum_diff: Optional[checksum_validator.ChecksumDiff]


class ProvDAG():
    """
    A single-rooted DAG of UUIDs representing a single QIIME 2 Archive.


    DAG Attributes:

    parser_results: ParserResults
    provenance_is_valid: checksum_validator.ValidationCodes
    checksum_diff = checksum_validator.ChecksumDiff

    Nodes are literally UUIDs (strings)
    Every node has the following attributes:
    node_data: Optional[ProvNode]
    has_provenance: bool

    Notes:

    No-provenance nodes:
    When parsing v1+ archives, v0 ancestor nodes without tracked provenance
    (e.g. !no-provenance inputs) are discovered only as parents to the current
    inputs. They are added to the DAG when we add in-edges to "real" provenance
    nodes. These nodes are explicitly assigned the node attributes above,
    allowing red-flagging of no-provenance nodes with a slightly cleaner API,
    as all nodes should have a boolean value for that attribute.

    Custom node objects:
    Though NetworkX supports the use of custom objects as nodes, querying the
    DAG for an individual graph node requires keying with object literals,
    which feels much less intuitive than with e.g. the UUID string of the
    ProvNode you want to access, and might make testing a bit clunky.
    """
    @property
    def root_uuid(self) -> UUID:
        """The UUID of the terminal node of one QIIME 2 Archive"""
        return self.parser_results.root_md.uuid

    @property
    def root_node(self) -> ProvNode:
        """The terminal ProvNode of one QIIME 2 Archive"""
        return self.get_node_data(self.root_uuid)

    @property
    def provenance_is_valid(self) -> checksum_validator.ValidationCodes:
        return self.parser_results.provenance_is_valid

    @property
    def checksum_diff(self) -> Optional[checksum_validator.ChecksumDiff]:
        return self.parser_results.checksum_diff

    @property
    def nodes(self) -> NodeView:
        return self.dag.nodes

    def has_edge(self, start_node, end_node) -> bool:
        """
        Returns True if the edge u, v is in the graph
        Calls nx.DiGraph.has_edge
        """
        return self.dag.has_edge(start_node, end_node)

    def node_has_provenance(self, uuid: UUID) -> bool:
        return self.dag.nodes[uuid]['has_provenance']

    def get_node_data(self, uuid: UUID) -> ProvNode:
        """Returns a ProvNode from this ProvDAG selected by UUID"""
        return self.dag.nodes[uuid]['node_data']

    def __init__(self, archive_fp: str, cfg: Config = Config()):
        """
        Create a ProvDAG (digraph) by:
            0. Create an empty nx.digraph
            1. parse the raw data from the zip archive
            2. gather nodes with their associated data
            3. Add edges to graph (adding all !no-provenance nodes and any
               artifacts passed as metadata that aren't predecessors of the
               root node)
            4. Create guaranteed node attributes for these no-provenance nodes
        """
        # TODO: NEXT - stop subclassign DiGraph and start this by creating a
        # DiGraph "owned by" this class.
        # Check whether this allows us to reverse direction, create views, etc

        self.dag = nx.DiGraph()
        with zipfile.ZipFile(archive_fp) as zf:
            handler = FormatHandler(cfg, zf)
            self.parser_results = handler.parse(zf)

            arc_contents = self.parser_results.archive_contents
            nbunch = [
                (n_id, dict(
                    node_data=arc_contents[n_id],
                    has_provenance=arc_contents[n_id].has_provenance,
                    )) for n_id in arc_contents]
            self.dag.add_nodes_from(nbunch)

            ebunch = []
            for node_id, attrs in self.dag.nodes(data=True):
                if parents := attrs['node_data'].parents:
                    for parent in parents:
                        type = tuple(parent.keys())[0]
                        parent_uuid = tuple(parent.values())[0]
                        ebunch.append((parent_uuid, node_id,
                                       {'type': type}))
            self.dag.add_edges_from(ebunch)

            for node_id, attrs in self.dag.nodes(data=True):
                if attrs.get('node_data') is None:
                    attrs['has_provenance'] = False
                    attrs['node_data'] = None

    def __repr__(self) -> str:
        return repr(self.parser_results.root_md)

    __str__ = __repr__

    def __len__(self) -> int:
        return len(self.dag)

    def get_nested_provenance_nodes(self, node_id: UUID) -> Set[UUID]:
        """
        Depth-first traversal of this ProvNode's ancestors, returns the set of
        nodes that represent "nested" provenance, like that seen in q2view.

        Because the terminal/alias nodes created by pipelines show _pipeline_
        inputs, this simple recursion skips over all inner nodes.

        TODO: This traversal returns a set of UUIDs. In the long run, we're
        probably looking for a proper nx.GraphView
        """
        nodes = {node_id}
        if parents := self.get_node_data(node_id).parents:
            parent_uuids = (list(parent.values())[0] for parent in parents)
            for uuid in parent_uuids:
                nodes = nodes | self.get_nested_provenance_nodes(uuid)
        return nodes


class ProvNode:
    """ One node of a provenance DAG, describing one QIIME 2 Result """

    @property
    def uuid(self) -> UUID:
        return self._result_md.uuid

    @property
    def type(self) -> str:
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
        provenance, or the user opted out of metadata parsing.
        """
        self._metadata: Optional[Dict[str, pd.DataFrame]]

        md = None
        if hasattr(self, '_metadata'):
            md = self._metadata
        return md

    @property
    def parents(self) -> Optional[List[Dict[str, UUID]]]:
        """
        a list of single-item {Type: UUID} dicts describing this
        action's inputs, and including Artifacts passed as Metadata parameters.

        Returns [] if this "action" is an Import
        """
        self._artifacts_passed_as_md: List[Dict[str, UUID]]

        if not self.has_provenance:
            return None

        inputs = self.action._action_details.get('inputs')
        parents = [] if inputs is None else inputs

        artifacts_as_metadata = self._artifacts_passed_as_md
        return parents + artifacts_as_metadata

    def __init__(self, cfg: Config, zf: zipfile.ZipFile,
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

        if self.has_provenance:
            all_metadata_fps, self._artifacts_passed_as_md = \
                self._get_metadata_from_Action(self.action._action_details)
            if cfg.parse_study_metadata:
                self._metadata = self._parse_metadata(zf, all_metadata_fps)

    def _get_metadata_from_Action(
        self, action_details: Dict[str, List]) \
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
        return f'ProvNode({self.uuid}, {self.type}, fmt={self.format})'

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
    expected_files_root_only = tuple()  # type: Tuple[str, ...]
    expected_files_in_all_nodes = (
        'metadata.yaml', 'VERSION')  # type: Tuple[str, ...]

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
            Tuple[checksum_validator.ValidationCodes,
                  Optional[checksum_validator.ChecksumDiff]]:
        """
        V0 archives predate provenance tracking, so
        - provenance_is_valid = False
        - checksum_diff = None
        """
        return (checksum_validator.ValidationCodes.PREDATES_CHECKSUMS,
                None)

    @classmethod
    def parse_prov(cls, cfg: Config, zf: zipfile.ZipFile) -> ParserResults:
        archv_contents = {}

        if cfg.perform_checksum_validation:
            provenance_is_valid, checksum_diff = cls._validate_checksums(zf)
        else:
            provenance_is_valid, checksum_diff = (
                checksum_validator.ValidationCodes.VALIDATION_OPTOUT, None)

        uuid = pathlib.Path(zf.namelist()[0]).parts[0]

        warnings.warn(f"Artifact {uuid} was created prior to provenance" +
                      " tracking. Provenance data will be incomplete.",
                      UserWarning)

        root_md = cls._parse_root_md(zf, uuid)
        expected_files = cls.expected_files_in_all_nodes
        prov_data_fps = [pathlib.Path(uuid) / fp for fp in expected_files]
        archv_contents[uuid] = ProvNode(cfg, zf, prov_data_fps)

        return ParserResults(
            root_md, archv_contents, provenance_is_valid, checksum_diff
            )


class ParserV1(ParserV0):
    """
    Parser for V1 archives. These track provenance, so we parse it.
    """
    version_string = 1
    # These are files we expect will be present in every QIIME2 archive with
    # this format. "Optional" filenames should not be included here.
    expected_files_root_only = ParserV0.expected_files_root_only
    expected_files_in_all_nodes = ParserV0.expected_files_in_all_nodes + \
        ('action/action.yaml', )

    @classmethod
    def _validate_checksums(cls, zf: zipfile.ZipFile) -> \
            Tuple[checksum_validator.ValidationCodes,
                  Optional[checksum_validator.ChecksumDiff]]:
        """
        Provenance is initially assumed valid because we have no checksums,
        so:
        - provenance_is_valid = False
        - checksum_diff = None
        """
        return (checksum_validator.ValidationCodes.PREDATES_CHECKSUMS,
                None)

    @classmethod
    def parse_prov(cls, cfg: Config, zf: zipfile.ZipFile) -> ParserResults:
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

        if cfg.perform_checksum_validation:
            provenance_is_valid, checksum_diff = cls._validate_checksums(zf)
        else:
            provenance_is_valid, checksum_diff = (
                checksum_validator.ValidationCodes.VALIDATION_OPTOUT, None)

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
                fps_for_this_result = [
                    prefix / name for name in cls.expected_files_in_all_nodes]

                # Warn/reset provenance_is_valid if expected files are missing
                files_are_missing = False
                error_contents = "Malformed Archive: "
                for fp in fps_for_this_result:
                    if fp not in prov_data_fps:
                        files_are_missing = True
                        provenance_is_valid = \
                            checksum_validator.ValidationCodes.INVALID
                        error_contents += (
                            f"{fp.name} file for node {node_uuid} misplaced "
                            "or nonexistent.\n")

                if(files_are_missing):
                    error_contents += (f"Archive {root_uuid} may be corrupt "
                                       "or provenance may be false.")
                    raise ValueError(error_contents)

                archv_contents[node_uuid] = ProvNode(cfg, zf,
                                                     fps_for_this_result)

        return ParserResults(
            root_md, archv_contents, provenance_is_valid, checksum_diff
        )

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
    expected_files_in_all_nodes = ParserV3.expected_files_in_all_nodes + \
        ('citations.bib', )
    expected_files_root_only = ParserV3.expected_files_root_only


class ParserV5(ParserV4):
    """
    Parser for V5 archives. Adds checksum validation with checksums.md5
    """
    version_string = 5
    # These are files we expect will be present in every QIIME2 archive with
    # this format. "Optional" filenames should not be included here.
    expected_files_in_all_nodes = ParserV4.expected_files_in_all_nodes
    expected_files_root_only = ('checksums.md5', )

    @classmethod
    def _validate_checksums(cls, zf: zipfile.ZipFile) -> \
            Tuple[checksum_validator.ValidationCodes,
                  Optional[checksum_validator.ChecksumDiff]]:
        """
        With v5, we can actually validate checksums, so use checksum_validator
        to return:
        - provenance_is_valid: bool
        - checksum_diff: Optional[ChecksumDiff], where None only if
            checksums.md5 is missing
        """
        return checksum_validator.validate_checksums(zf)

    @classmethod
    def parse_prov(cls, cfg: Config, zf: zipfile.ZipFile) -> ParserResults:
        """
        Parses provenance data for one Archive, applying the local
        _validate_checksums() method to the v1 parser
        """
        return super().parse_prov(cfg, zf)


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
        return self._archive_version

    @property
    def framework_version(self):
        return self._frmwk_vrsn

    def __init__(self, cfg: Config, zf: zipfile.ZipFile):
        self.cfg = cfg
        self._archive_version, self._frmwk_vrsn = \
            version_parser.parse_version(zf)
        self.parser = self._FORMAT_REGISTRY[self._archive_version]

    def parse(self, zf: zipfile.ZipFile) -> ParserResults:
        return self.parser.parse_prov(self.cfg, zf)
