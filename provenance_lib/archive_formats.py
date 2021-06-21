from __future__ import annotations
import codecs
import pathlib
import re
from typing import List, Tuple

import bibtexparser as bp
import yaml
import zipfile


_VERSION_MATCHER = (
    r"QIIME 2\n"
    r"archive: [0-9]{1,2}$\n"
    r"framework: "
    r"(?:20[0-9]{2}|2)\.(?:[1-9][0-2]?|0)\.[0-9](?:\.dev[0-9]?)?\Z")


class ParserV0():
    """
    Parser for V0 archives. These have no provenance, so we only parse metadata
    """
    @classmethod
    def get_root_md(self, zf: zipfile.ZipFile, archive_fp: str) \
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
        # TODO: How does mypy handle the different return type in subclasses?
        # TODO: This should probably Warn that v0 has no provenance, citations
        raise NotImplementedError


class ParserV1(ParserV0):
    """
    Parser for V1 archives. These track provenance, so we parse it.
    """
    prov_filenames = ['metadata.yaml', 'action/action.yaml']

    @classmethod
    def populate_archv(self, zf: zipfile) -> Tuple[int, ProvNode]:
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
                archv_contents[uuid] = ProvNode(self, zf, fps_for_this_result)

            # NEXT: Fix tests
            # NEXT: ProvNode is going to need to handle version numbers too.

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


class ParserV3(ParserV2):
    """
    Parser for V3 archives. Directory structure identical to V1 & V2
    action.yaml now supports variadic inputs, so !set tags in action.yaml
    """
    # TODO: move set constructor over here? (and !cite constructor below?)


class ParserV4(ParserV3):
    """
    Parser for V4 archives. Adds citations to dir structure, changes to
    action.yaml incl transformers
    """
    prov_filenames = ['metadata.yaml', 'action/action.yaml', 'citations.bib']


class ParserV5(ParserV4):
    """
    Parser for V5 archives. Adds checksums.md5
    """
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

    def parse(self, zf: zipfile.ZipFile, archive_fp: str) -> \
            Tuple[_ResultMetadata, Tuple[int, ProvNode]]:
        return (self.parser.get_root_md(zf, archive_fp),
                self.parser.populate_archv(zf))


# NEXT: ProvNode is going to need to handle version numbers as well.
class ProvNode:
    """ One node of a provenance DAG, describing one QIIME 2 Result """
    _parents = None
    _origin_archives = []

    # NOTE: ProvNodes capture their "origin_archive" in a list when
    # initialized, and ProvNode.parents expects that origin_archive to be at
    # index 0. Union (and similar operations) should not interfere with this
    # convention.

    @property
    def parents(self):
        """ The list of ProvNodes used as inputs in creating this ProvNode """
        # NOTE: We must delay gathering parentage data until the ProvDAG is
        # fully populated (or risk KeyError). Caching this lazily allows us to
        # delay until the first call (likely the first DAG traversal)
        if not self._parents:
            try:
                parent_dicts = [parent for parent in self._action.inputs]
                parent_uuids = [
                    list(uuid.values())[0] for uuid in parent_dicts]
                self._parents = [
                    self._origin_archives[0]._archv_contents[uuid]
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

    def __init__(self, origin_archive, zf: zipfile,
                 fps_for_this_result: List[pathlib.Path]):
        self._origin_archives.append(origin_archive)
        # TODO: Does VERSION effect what other things get read in?
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
