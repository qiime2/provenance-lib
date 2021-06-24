from __future__ import annotations
import codecs
import pathlib
import re
from typing import List, Dict, Tuple

import bibtexparser as bp
import yaml
import zipfile


_VERSION_MATCHER = (
    r"QIIME 2\n"
    r"archive: [0-9]{1,2}$\n"
    r"framework: "
    r"(?:20[0-9]{2}|2)\.(?:[1-9][0-2]?|0)\.[0-9](?:\.dev[0-9]?)?\Z")

# TODO: Move constructors into a separate module
# from yaml_constructors import (
#     metadata_constructor, citation_constructor, ref_constructor)


# TODO: The framework exposes many additional custom tags not yet handled
# here. Check qiime2/core/archive/provenance.py for everything
def citation_constructor(loader, node):
    value = loader.construct_scalar(node)
    return value


def ref_constructor(loader, node):
    value = loader.construct_scalar(node)
    environment, plugins, plugin_name = value.split(':')
    return plugin_name


def metadata_constructor(loader, node):
    value = loader.construct_scalar(node)
    return value


yaml.SafeLoader.add_constructor('!metadata', metadata_constructor)
yaml.SafeLoader.add_constructor('!cite', citation_constructor)
yaml.SafeLoader.add_constructor('!ref', ref_constructor)


class ProvDAG:
    """
    A single-rooted DAG of ProvNode objects, representing a single QIIME 2
    Archive.
    TODO: May also contain a non-hierarchical pool of unique ProvNodes?
    """
    _num_results: int
    _archv_contents: Dict[str, ProvNode]
    _archive_md: _ResultMetadata

    # TODO: Drop? Does this object even care about these version numbers?
    @property
    def archive_version(self):
        """The archive version of this QIIME 2 Archive"""
        return self.handler.archive_version

    # TODO: Drop? Does this object even care about these version numbers?
    @property
    def framework_version(self):
        """The framework version that created this QIIME 2 Archive"""
        return self.handler.framework_version

    @property
    def root_uuid(self):
        """The UUID of the terminal node of one QIIME 2 Archive"""
        return self._archive_md.uuid

    @property
    def root_node(self):
        """The terminal ProvNode of one QIIME 2 Archive"""
        return self.get_result(self.root_uuid)

    # TODO: drop this - belongs to the node?
    @property
    def archive_type(self):
        """The semantic type of the terminal node of one QIIME 2 Archive"""
        return self._archive_md.type

    # TODO: drop this - belongs to the node?
    @property
    def archive_format(self):
        """The format of the terminal node of one QIIME 2 Archive"""
        return self._archive_md.format

    def get_result(self, uuid):
        """Returns a ProvNode from this ProvDAG selected by UUID"""
        return self._archv_contents[uuid]

    def _traverse_uuids_from_root(self):
        return self.root_node.traverse_uuids()

    def __str__(self):
        return repr(self._archive_md)

    def __repr__(self):
        # Traverse DAG, printing UUIDs
        # TODO: Improve this repr to remove id duplication
        r_str = self.__str__() + "\nContains Results:\n"
        uuid_yaml = yaml.dump(self._traverse_uuids_from_root())
        r_str += uuid_yaml
        return r_str

    def __init__(self, archive_fp: str):
        self._archive_md: None
        self._archv_contents: None
        self._num_results = 0

        with zipfile.ZipFile(archive_fp) as zf:
            self.handler = FormatHandler(zf)
            self._archive_md, (self._num_results, self._archv_contents) = \
                self.handler.parse(zf, owned_by=self)


class UnionedDAG:
    """
    a many-rooted DAG of ProvNode objects, created from a Union of ProvDAGs
    """

    # TODO: Implement
    def __init__(self, dags: List[ProvDAG]):
        self.root_uuids = [dag.root_uuid for dag in dags]
        self.root_nodes = [dag.root_node for dag in dags]


class ProvNode:
    """ One node of a provenance DAG, describing one QIIME 2 Result """
    _parents = None
    _owner_dag = None

    @property
    def parents(self):
        """ The list of ProvNodes used as inputs in creating this ProvNode """
        # NOTE: We must delay gathering parentage data until the ProvDAG is
        # fully populated (otherwise KeyError on the UUID of a not-yet-parsed
        # ProvNode). Caching this lazily allows us to delay until the first
        # call (likely the first DAG traversal)
        if not self._parents:
            try:
                parent_dicts = [parent for parent in self._action.inputs]
                parent_uuids = [
                    list(uuid.values())[0] for uuid in parent_dicts]
                self._parents = [
                    self._owner_dag._archv_contents[uuid]
                    for uuid in parent_uuids]
            except KeyError:
                pass
        return self._parents

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
        # TODO: NEXT Fix this
        return self._owner_dag.version_string

    @property
    def framework_version(self):
        # storing this would require passing it from Handler -> parser -> node
        # or factoring _get_version() out into a standalone function and
        # calling it again here. For now, I'm saying we don't care.
        return NotImplementedError

    # NOTE: This constructor is intentionally flexible, and will parse any
    # files handed to it. It is the responsibility of the ParserVx classes to
    # decide what files need to be passed.
    def __init__(self, ownedBy, zf: zipfile,
                 fps_for_this_result: List[pathlib.Path]):
        self._owner_dag = ownedBy
        for fp in fps_for_this_result:
            # TODO: Should we be reading these zipfiles once here,
            # and then passing them to the constructors below?
            if fp.name == 'metadata.yaml':
                self._result_md = _ResultMetadata(zf, str(fp))
            elif fp.name == 'action.yaml':
                self._action = _Action(zf, str(fp))
            elif fp.name == 'citations.bib':
                self._citations = _Citations(zf, str(fp))

    def __repr__(self):
        return f'ProvNode({self.uuid}, {self.sem_type}, fmt={self.format})'

    def __str__(self):
        return f'ProvNode({self.uuid})'

    def __eq__(self, other):
        # TODO: Should this offer more robust validation?
        return self.uuid == other.uuid

    # TODO: Should this live in ProvDAG?
    def traverse_uuids(self):
        """ depth-first traversal of this ProvNode's ancestors """
        local_parents = dict()
        if not self.parents:
            local_parents = {self.uuid: None}
        else:
            sub_dag = dict()
            for parent in self.parents:
                sub_dag.update(parent.traverse_uuids())
            local_parents[self.uuid] = sub_dag
        return local_parents


class _Action:
    """ Provenance data for a single QIIME 2 Result from action.yaml """
    _action_details = None

    @property
    def action_id(self):
        """ the UUID assigned to this Action (not its Results) """
        return self._execution_details['uuid']

    @property
    def action_type(self):
        """ the type of Action represented (e.g. Method, Pipeline, etc. ) """
        return self._action_details['type']

    @property
    def action(self):
        """ the action executed by this Action """
        return self._action_details['action']

    @property
    def plugin(self):
        """ the plugin which executed this Action """
        return self._action_details['plugin']

    @property
    def inputs(self):
        """
        a list of single-item dicts containing the types and UUIDs of this
        action's inputs
        """
        return self._action_details['inputs']

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
        self._citations = {entry['ID']: entry for entry in bib_db.entries}

    def __repr__(self):
        keys = [entry for entry in self._citations.keys()]
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

    @classmethod
    def populate_archv(self, zf: zipfile.ZipFile) -> None:
        raise NotImplementedError("V0 Archives do not contain provenance data")


class ParserV1(ParserV0):
    """
    Parser for V1 archives. These track provenance, so we parse it.
    """
    version_string = 1
    prov_filenames = ['metadata.yaml', 'action/action.yaml']

    @classmethod
    def populate_archv(self, zf: zipfile, owner_dag: ProvDAG) -> \
            Tuple[int, Dict[str, ProvNode]]:
        """
        Populates an _Archive with all relevant provenance data
        Takes an Archive (as a zipfile) as input.

        By convention, the filepaths within these Archives begin with:
        <archive_root_uuid>/provenance/...
        archive-root provenance files live directly inside 'provenance'
        e.g: <archive_root_uuid>/provenance/metadata.yaml
        non-root provenance files live inside 'artifacts/<uuid>'
        e.g: <archive_root_uuid>/provenance/artifacts/<uuid>/metadata.yaml
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
                archv_contents[uuid] = ProvNode(owner_dag, zf,
                                                fps_for_this_result)
        return (num_results, archv_contents)

    @classmethod
    def _get_nonroot_uuid(self, fp: pathlib.Path) -> str:
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


class ParserV3(ParserV2):
    """
    Parser for V3 archives. Directory structure identical to V1 & V2
    action.yaml now supports variadic inputs, so !set tags in action.yaml
    """
    version_string = 3
    # TODO: move set constructor over here? (and !cite constructor below?)


class ParserV4(ParserV3):
    """
    Parser for V4 archives. Adds citations to dir structure, changes to
    action.yaml incl transformers
    """
    version_string = 4
    prov_filenames = ['metadata.yaml', 'action/action.yaml', 'citations.bib']


class ParserV5(ParserV4):
    """
    Parser for V5 archives. Adds checksums.md5
    """
    version_string = 5
    prov_filenames = ['metadata.yaml', 'action/action.yaml', 'citations.bib',
                      'checksums.md5']
    # TODO: Add very optional checksum validation?


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
        _, self._archv_vrsn, self._frmwk_vrsn = self._get_version(zf)
        self.parser = self._FORMAT_REGISTRY[self._archv_vrsn]

    def _get_version(self, zf: zipfile) -> List[str]:
        """Parse Archive VERSION file"""
        # All files in zf start with root uuid, so we'll grab it from the first
        version_fp = pathlib.Path(zf.namelist()[0]).parts[0] + '/VERSION'
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

        return [line.strip().split()[-1]
                for line in version_contents.split(sep="\n") if line]

    def parse(self, zf: zipfile.ZipFile, owned_by: ProvDAG) -> \
            Tuple[_ResultMetadata, Tuple[int, Dict[str, ProvNode]]]:
        return (self.parser.get_root_md(zf),
                self.parser.populate_archv(zf, owned_by))
