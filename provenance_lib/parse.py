from __future__ import annotations
import pathlib
import pandas as pd
from datetime import timedelta
from typing import List, Dict, Mapping, Tuple, Optional
import warnings
import zipfile

import bibtexparser as bp
from networkx import DiGraph
import yaml

from .checksum_validator import ChecksumDiff, validate_checksums
from .version_parser import get_version
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
            Mapping[UUID, Optional[ProvNode]]:
        """ depth-first traversal of this ProvNode's ancestors """
        # Use this DAG's root uuid by default
        node_id = self.root_uuid if node_id is None else node_id
        local_parents = dict()
        if not self.nodes[node_id]['parents']:
            local_parents = {node_id: None}
        else:
            sub_dag = dict()  # type: Dict[UUID, Optional[ProvNode]]
            parents = self.nodes[node_id]['parents']
            parent_uuids = (list(parent.values())[0] for parent in parents)
            for uuid in parent_uuids:
                sub_dag.update(self.traverse_uuids(uuid))
            local_parents[node_id] = sub_dag  # type: ignore
        return local_parents

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
            # TODO: Handle nested provenance correctly
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
    def archive_version(self) -> str:
        return self._archive_version

    @property
    def framework_version(self) -> str:
        return self._framework_version

    @property
    def has_provenance(self) -> bool:
        return self.archive_version != '0'

    def __init__(self, zf: zipfile.ZipFile,
                 fps_for_this_result: List[pathlib.Path]) -> None:
        """
        Constructs a ProvNode from a zipfile and some filepaths.

        This constructor is intentionally flexible, and will parse any
        files handed to it. It is the responsibility of the ParserVx classes to
        decide what files need to be passed.

        For Archive Versions in which `checksums.md5` is present,
        it validates the Archive.
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
                self.checksum_diff: Optional[ChecksumDiff]
                try:
                    # TODO: factor this checking out into checksum_validator.py
                    diff = validate_checksums(zf)
                    if diff != ChecksumDiff({}, {}, {}):
                        # self._result_md may not have been parsed, so get uuid
                        root_uuid = pathlib.Path(zf.namelist()[0]).parts[0]
                        warnings.warn(
                            f"Checksums are invalid for Archive {root_uuid}\n"
                            "Archive may be corrupt or provenance may be false"
                            ".\n"
                            f"Files added since archive creation: {diff[0]}\n"
                            f"Files removed since archive creation: {diff[1]}"
                            "\n"
                            f"Files changed since archive creation: {diff[2]}",
                            UserWarning)
                        self.provenance_is_valid = False
                        self.checksum_diff = diff
                # zipfiles KeyError if file not found. checksums.md5 is missing
                except KeyError as err:
                    warnings.warn(
                        str(err).strip('"') +
                        ". Archive may be corrupt or provenance may be false",
                        UserWarning)
                    self.provenance_is_valid = False
                    self.checksum_diff = None

        # If the _Action constructor finds metadata files, this will parse them
        # TODO: This should be a user-facing option, right?
        # Isn't Metadata parsing only useful if we want to use the
        # same metadata for our replay as we did in the original.
        # This would require identical UUIDs, as well as an
        # identical mapping of metadata to those UUIDs.
        # This seems like a neat trick, but not a common use case?

        # This only makes sense if we have provenance to track. Otherwise,
        # there is no action.yaml to interrogate.
        # TODO: test what happens if archive has had action.yaml removed
        if self.has_provenance:
            self._metadata = self._parse_metadata(zf)

    def _parse_metadata(self, zf: zipfile.ZipFile,
                        mock_action_details: Dict[str, List] = None
                        ) -> Dict[str, pd.DataFrame]:
        """
        For now at least, this parses all Metadata and MetadataColumns into
        pd.DataFrames. In the future, we may need a simple type that can hold
        the name of the original associated parameter, the type (MetadataColumn
        or Metadata), and the appropriate Series or Dataframe respectively.
        """
        # TODO: Open this up again once we're testing
        # action_details = mock_action_details \
        #     if mock_action_details is not None
        # else self.action._action_details
        all_md, artifacts_passed_as_md = self._get_metadata_from_Action()
        # TODO: NEXT parse metadata into our object, returning a
        # {param_name: pd.DF}

    def _get_metadata_from_Action(
        self, mock_action_details: Dict[str, List] = None) \
            -> Tuple[Dict[str, str], List[Dict[str, UUID]]]:
        action_details = mock_action_details \
            if mock_action_details is not None else self.action._action_details
        all_metadata = dict()
        if (all_params := action_details.get('parameters')) is not None:
            for param in all_params:
                param_val = list(param.values())[0]
                if isinstance(param_val, MetadataInfo):
                    # the name of the Metadata or MdCol that was registered:
                    param_name = list(param)[0]
                    md_fp = param_val.relative_fp
                    all_metadata.update({param_name: md_fp})

        arts_as_md = None
        return all_metadata, arts_as_md

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

    # TODO: Move up to ProvNode
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

    # TODO NEXT: Do we want to move this into ProvNode? It would sit with the
    # metadata parsing method, which could reduce the need for code duplication
    def _get_artifacts_passed_as_md(
        self, action_details: Dict[str, List] = None) -> \
            List[Dict[str, UUID]]:
        """
        Returns a list of single-item dictionaries conforming to:
        {'artifact_passed_as_metadata': <uuid>}, representing all artifacts
        passed into this action as metadata.

        By default, this will operate on self._action_details. The optional
        `action_details` parameter is provided only to simplify testing,
        allowing us to pass hardcoded 'action_details' dictionaries.

        We expect data like this:

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
        action_details = action_details if action_details is not None \
            else self._action_details
        artifacts_as_metadata = []
        if (all_params := action_details.get('parameters')) is not None:
            for param in all_params:
                param_val = list(param.values())[0]
                if isinstance(param_val, MetadataInfo):
                    artifacts_as_metadata += [
                        {'artifact_passed_as_metadata': uuid} for uuid in
                        param_val.input_artifact_uuids]

                    # TODO: REMOVE
                    # print(artifacts_as_metadata)
        return artifacts_as_metadata

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
    # this format. "Optional" filenames should not be included here.
    expected_files = ('metadata.yaml', 'VERSION')  # type: Tuple[str, ...]

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
        prov_data_fps = [pathlib.Path(uuid) / fp for fp in self.expected_files]
        archv_contents[uuid] = ProvNode(zf, prov_data_fps)
        return (num_results, archv_contents)


class ParserV1(ParserV0):
    """
    Parser for V1 archives. These track provenance, so we parse it.
    """
    expected_files: Tuple[str, ...]
    version_string = 1
    # These are files we expect will be present in every QIIME2 archive with
    # this format. "Optional" filenames should not be included here.
    expected_files = ('metadata.yaml', 'action/action.yaml', 'VERSION')

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

        Note: we create a list of filepaths to parse into ProvNodes
        naively, from the version-specific list of files we expect will always
        be present, `expected_files`. This saves us from filtering repeatedly,
        but may cause problems if expected files have been removed by the user.
        Targeted error/warning messages for missing VERSION, metadata.yaml,
        and checksums.md5 have been written elsewhere.
        """
        archv_contents = {}
        num_results = 0

        prov_data_fps = [
            pathlib.Path(fp) for fp in zf.namelist()
            if 'provenance' in fp
            # and any of the filenames above show up in the filepath
            and any(map(lambda x: x in fp, self.expected_files))
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
                                       for name in self.expected_files]
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
    # These are files we expect will be present in every QIIME2 archive with
    # this format. "Optional" filenames should not be included here.
    expected_files = ParserV1.expected_files


class ParserV3(ParserV2):
    """
    Parser for V3 archives. Directory structure identical to V1 & V2
    action.yaml now supports variadic inputs, so !set tags in action.yaml
    """
    version_string = 3
    # These are files we expect will be present in every QIIME2 archive with
    # this format. "Optional" filenames should not be included here.
    expected_files = ParserV2.expected_files


class ParserV4(ParserV3):
    """
    Parser for V4 archives. Adds citations to dir structure, changes to
    action.yaml incl transformers
    """
    expected_files: Tuple[str, ...]
    version_string = 4
    # These are files we expect will be present in every QIIME2 archive with
    # this format. "Optional" filenames should not be included here.
    expected_files = (*ParserV3.expected_files, 'citations.bib')


class ParserV5(ParserV4):
    """
    Parser for V5 archives. Adds checksums.md5
    """
    expected_files: Tuple[str, ...]
    version_string = 5
    # These are files we expect will be present in every QIIME2 archive with
    # this format. "Optional" filenames should not be included here.
    expected_files = (*ParserV4.expected_files, 'checksums.md5')


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
