from __future__ import annotations
import codecs
import pathlib
import re
from datetime import timedelta
from typing import List, Dict, Tuple, Optional

import bibtexparser as bp
from networkx import DiGraph
import yaml
import zipfile

# NOTE: str aliased to UUID in yaml_constructors to prevent circular dependency
from .yaml_constructors import UUID
from .yaml_constructors import (
    citation_key_constructor, metadata_path_constructor, ref_constructor,
    set_constructor,
    )
yaml.SafeLoader.add_constructor('!cite', citation_key_constructor)
yaml.SafeLoader.add_constructor('!metadata', metadata_path_constructor)
yaml.SafeLoader.add_constructor('!ref', ref_constructor)
yaml.SafeLoader.add_constructor('!set', set_constructor)

_VERSION_MATCHER = (
    r'QIIME 2\n'
    r'archive: [0-9]{1,2}$\n'
    r'framework: '
    r'(?:20[0-9]{2}|2)\.(?:[1-9][0-2]?|0)\.[0-9](?:\.dev[0-9]?)?\Z')


def get_version(zf: zipfile, fp: Optional[pathlib.Path] = None) -> Tuple[str]:
    """Parse a VERSION file - by default uses the VERSION at archive root"""
    if not fp:
        # All files in zf start with root uuid, so we'll grab it from the first
        version_fp = pathlib.Path(zf.namelist()[0]).parts[0] + '/VERSION'
    else:
        version_fp = str(fp)

    try:
        with zf.open(version_fp) as v_fp:
            version_contents = str(v_fp.read().strip(), 'utf-8')
    except KeyError:
        raise ValueError(
            "Malformed Archive: VERSION file misplaced or nonexistent")

    if not re.match(_VERSION_MATCHER, version_contents, re.MULTILINE):
        _vrsn_mtch_repr = codecs.decode(_VERSION_MATCHER, 'unicode-escape')
        raise ValueError(
            "Malformed Archive: VERSION file out of spec\n\n"
            f"Should match this RE:\n{_vrsn_mtch_repr}\n\n"
            f"Actually looks like:\n{version_contents}\n")

    _, archv_vrsn, frmwk_vrsn = [line.strip().split()[-1] for line in
                                 version_contents.split(sep='\n') if line]
    return (archv_vrsn, frmwk_vrsn)


class ProvDAG(DiGraph):
    """
    A single-rooted DAG of ProvNode objects, representing a single QIIME 2
    Archive.
    TODO: May also contain a non-hierarchical pool of unique ProvNodes?
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
            # value?

            con = self._archv_contents
            node_contents = [
                (n_id, dict(full_ProvNode_payload=con[n_id],
                            type=con[n_id].sem_type,
                            format=con[n_id].format,
                            framework_version=con[n_id].framework_version,
                            archive_version=con[n_id].archive_version,
                            action_type=con[n_id].action.action_type,
                            plugin=con[n_id].action.plugin,
                            parents=con[n_id].action.parents,
                            runtime=con[n_id].action.runtime
                            )) for n_id in self._archv_contents]
            self.add_nodes_from(node_contents)

            ebunch = []
            for node_id, data in self.nodes(data=True):
                if data['parents']:
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
    def uuid(self):
        return self._result_md.uuid

    @property
    def sem_type(self):
        return self._result_md.type

    @property
    def format(self):
        return self._result_md.format

    @property
    def archive_version(self):
        return self._archive_version

    @property
    def framework_version(self):
        return self._framework_version

    # NOTE: This constructor is intentionally flexible, and will parse any
    # files handed to it. It is the responsibility of the ParserVx classes to
    # decide what files need to be passed.
    def __init__(self, zf: zipfile,
                 fps_for_this_result: List[pathlib.Path]) -> None:
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
        keys = [entry for entry in self.citations.keys()]
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

    # TODO: This will prevent users from parsing v0 archives directly.
    # Though reasonable in a one-archive replay scenario, this will cause
    # problems if users want to "replay" an entire analysis that contains some
    # v0 archives. The no_provenance_constructor warns instead, allowing v1+
    # archives which contain v0 results in provenance to proceed. This seems
    # like a more graceful approach to me; replay what we can, and warn the
    # user that their replay will be incomplete.
    @classmethod
    def parse_prov(self, zf: zipfile.ZipFile) -> None:
        raise NotImplementedError("V0 Archives do not contain provenance data")


class ParserV1(ParserV0):
    """
    Parser for V1 archives. These track provenance, so we parse it.
    """
    version_string = 1
    prov_filenames = ('metadata.yaml', 'action/action.yaml', 'VERSION')

    @classmethod
    def parse_prov(self, zf: zipfile) -> Tuple[int, Dict[UUID, ProvNode]]:
        """
        Populates an _Archive with all relevant provenance data
        Takes an Archive (as a zipfile) as input.

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
