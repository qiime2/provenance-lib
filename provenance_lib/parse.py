import itertools
import pathlib
from typing import Iterator, List, Dict

import bibtexparser as bp
import yaml
import zipfile

# TODO: Move constructors into a separate module
# from yaml_constructors import (
#     metadata_constructor, citation_constructor, ref_constructor)


def citation_constructor(loader, node):
    # TODO: The framework exposes many additional custom tags not yet handled
    # here. Check qiime2/core/archive/provenance.py for everything
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


def _validate_fp(archive_fp):
    # This seems to be happening already
    # TODO: implement this, or more likely, integrate it elsewhere
    # Is it a filepath?
    # Is it a valid zip archive?
    # is it a valid QIIME 2 archive (this probably can't be determined here)
    raise NotImplementedError


# TODO: remove - just a checklist at this point
def parse_archive(archive_fp):
    # _validate_fp(archive_fp)
    # build a tree
    raise NotImplementedError


class Archive:
    """Lightly-processed contents of a single QIIME 2 Archive"""

    # TODO: add property for archive version?
    # TODO: UUID class with basic validation?
    _number_of_results: int
    # TODO: UUID class
    _archive_contents: Dict

    @property
    def root_uuid(self):
        return self._archive_md.uuid

    @property
    def archive_type(self):
        return self._archive_md.type

    @property
    def archive_format(self):
        return self._archive_md.format

    def get_result(self, uuid):
        return self._archive_contents[uuid]

    def __init__(self, archive_fp: str):
        self._archive_md: None
        self._archive_contents: None
        self._number_of_results = 0

        # Get archive metadata including root uuid
        with zipfile.ZipFile(archive_fp) as zf:
            all_filenames = zf.namelist()
            root_metadata_fps = filter(self._is_root_metadata_file,
                                       all_filenames)
            # TODO: protect this with a try/except and test it
            root_metadata_fp = next(root_metadata_fps)

            try:
                next(root_metadata_fps)
                raise ValueError("Malformed Archive: "
                                 "multiple top-level metadata.yaml files")
            except StopIteration:
                pass

            self._archive_md = _ResultMetadata(zf, root_metadata_fp)
            self._populate_archive(zf)

    def _populate_archive(self, zf: zipfile):
        self._archive_contents = {}

        prov_data_filenames = filter(self._is_prov_data, zf.namelist())
        prov_data_fps = list(map(pathlib.Path, prov_data_filenames))

        all_uuids = set()
        for fp in prov_data_fps:
            uuid = ""
            if 'artifacts' not in fp.parts:
                uuid = fp.parts[0]
            else:
                uuid = self._get_nonroot_uuid(fp)
            all_uuids.add(uuid)

        # make a provnode for each UUID
        for uuid in all_uuids:
            fps_for_this_result = Iterator
            if uuid == self.root_uuid:
                fps_for_this_result = filter(self._is_root_prov_data,
                                             prov_data_fps)
            else:
                fps_for_this_result = itertools.filterfalse(
                    self._is_root_prov_data, prov_data_fps)
                fps_for_this_result = (fp for fp in fps_for_this_result if
                                       self._check_nonroot_uuid(fp, uuid))

            self._archive_contents[uuid] = ProvNode(zf, fps_for_this_result)
            self._number_of_results += 1

    def _get_nonroot_uuid(self, fp: pathlib.Path):
        """
        For non-root provenance files, get the Result's uuid from the path
        (avoiding the root Result's UUID which is in all paths)
        """
        if fp.name == 'action.yaml':
            uuid = fp.parts[-3]
        else:
            uuid = fp.parts[-2]
        return uuid

    def _check_nonroot_uuid(self, fp, uuid):
        """
        Helper for grouping files by uuid, returns True if file is from a
        a non-root Result as specified by uuid
        """
        fp_uuid = self._get_nonroot_uuid(fp)
        return fp_uuid == uuid

    def _is_version_file(self, fp, uuid):
        # TODO: remove? matches all files if given root UUID; root in all fps
        if False:
            return ('VERSION' in fp and uuid in fp)
        raise NotImplementedError

    def _normalize_path_iteration(self, fp):
        if isinstance(fp, pathlib.PurePath):
            fp = fp.parts
        return fp

    def _is_root_file(self, fp):
        fp = self._normalize_path_iteration(fp)
        return ('provenance' not in fp and '/data' not in fp)

    def _is_prov_data(self, fp):
        fp = self._normalize_path_iteration(fp)
        return 'provenance' in fp and ('metadata.yaml' in fp or
                                       'action.yaml' in fp or
                                       'citations.bib' in fp)
        # TODO: add VERSION. Why does doing so increase _number_of_results?

    def _is_root_prov_data(self, fp):
        fp = self._normalize_path_iteration(fp)
        return (self._is_prov_data(fp) and 'artifacts' not in fp)

    def _is_root_metadata_file(self, fp):
        fp = self._normalize_path_iteration(fp)
        return (self._is_root_prov_data(fp) and 'metadata.yaml' in fp)


class _ResultMetadata:
    """ Basic metadata about a single QIIME 2 Result from metadata.yaml """

    def __init__(self, zf: zipfile, md_fp: str):
        _md_dict = yaml.safe_load(zf.read(md_fp))
        self.uuid = _md_dict['uuid']
        self.type = _md_dict['type']
        self.format = _md_dict['format']

    def __repr__(self):
        return (f"_ResultMetadata(self.uuid={self.uuid}, "
                f"self.type={self.type}, self.format={self.format}")

    def __str__(self):
        return (f"[UUID: {self.uuid}, Semantic Type: {self.type}, "
                f"Format: {self.format}]")


class _Action:
    """ Provenance data for a single QIIME 2 Result from action.yaml """

    def __init__(self, zf: zipfile, fp: str):
        self._action_dict = yaml.safe_load(zf.read(fp))
        self._action_details = self._action_dict['action']
        self._execution_details = self._action_dict['execution']
        self._env_details = self._action_dict['environment']


class _Citations:
    """
    citations for a single QIIME 2 Result, as a dict of dicts where each
    inner dictionary represents one citation keyed on the citation's bibtex key
    """
    def __init__(self, zf: zipfile, fp: str):
        bib_db = bp.loads(zf.read(fp))
        self._citations = {entry['ID']: entry for entry in bib_db.entries}


class ProvNode:
    """ One node of a provenance tree, describing one QIIME 2 Result """
    @property
    def uuid(self):
        self._uuid = self._result_md.uuid
        return self._uuid

    @property
    def sem_type(self):
        return self._result_md.type

    @property
    def format(self):
        return self._result_md.format

    def __init__(self, zf: zipfile,
                 fps_for_this_result: Iterator[pathlib.Path]):

        # TODO: This should be a @property
        # This can probably replace the assignment going on in Tree __init__
        # finding and caching self._parents when called
        self.parents = None

        # TODO: Read and check VERSION
        # (this will probably effect what other things get read in)
        for fp in fps_for_this_result:
            # TODO: Should we be reading these zipfiles once here,
            # and then passing them to the constructors below?
            if fp.name == 'metadata.yaml':
                self._result_md = _ResultMetadata(zf, str(fp))
            elif fp.name == 'action.yaml':
                self._action = _Action(zf, str(fp))
            elif fp.name == 'citations.bib':
                self._citations = _Citations(zf, str(fp))
            else:
                pass

    def __repr__(self):
        return f'ProvNode({self.uuid}, {self.sem_type}, fmt={self.format})'

    def __str__(self):
        return f'ProvNode({self.uuid})'

    def __eq__(self, other):
        # TODO: Should this offer more robust validation?
        return self.uuid == other.uuid

    def traverse_uuids(self):
        local_uuid = self._result_md.uuid
        local_parents = dict()
        if not self.parents:
            local_parents = {local_uuid: None}
        else:
            subtree = dict()
            for parent in self.parents:
                subtree.update(parent.traverse_uuids())
            local_parents[local_uuid] = subtree

        return local_parents


class ProvTree:
    """
    a single-rooted tree of ProvNode objects. The ProvenanceTree constructor
    is responsible for assigning the parentage relationships between ProvNodes
    """

    def __init__(self, archive: Archive):
        self.root_uuid = archive.root_uuid
        self.root = archive._archive_contents[self.root_uuid]

        for node in archive._archive_contents.values():
            try:
                parent_dicts = [
                    parnt for parnt in node._action._action_details['inputs']]
                parnt_uuids = [list(uuid.values())[0] for uuid in parent_dicts]
                node.parents = [
                    archive._archive_contents[uuid] for uuid in parnt_uuids]
            except KeyError:
                node.parents = None

    def __repr__(self):
        # Traverse tree, printing nodes?
        uuid_yaml = yaml.dump(self.root.traverse_uuids())
        return f"\nRoot:\n{uuid_yaml}"


class UnionedTree:
    """
    a many-rooted tree of ProvNode objects, created from a Union of ProvTrees
    """

    def __init__(self, trees: List[ProvTree]):
        self.root_uuids = [tree.root_uuid for tree in trees]
        self.root_nodes = [tree.root for tree in trees]
        raise NotImplementedError
