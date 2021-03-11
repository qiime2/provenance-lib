import itertools
import pathlib
from typing import Iterator

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


def parse_archive(archive_fp):
    # _validate_fp(archive_fp)
    # Instantiate ArchiveContents

    # save archive root id
    # deserialize actions
    # build a tree
    raise NotImplementedError


class Archive:
    """Lightly-processed contents of a single QIIME 2 Archive"""

    def __init__(self, archive_fp: str):
        self._archive_md = None
        self._archive_contents = None
        self._number_of_results = 0
        with zipfile.ZipFile(archive_fp) as zf:

            # Get archive metadata including root uuid
            all_filenames = zf.namelist()
            root_metadata_fps = filter(self._is_root_metadata_file,
                                       all_filenames)
            root_metadata_fp = next(root_metadata_fps)

            try:
                next(root_metadata_fps)
                raise ValueError("Malformed Archive: "
                                 "multiple top-level metadata.yaml files")
            except StopIteration:
                pass

            # TODO: Should this be removed to reduce duplication?
            # this will all be stored in the root Result's provenance anyway
            self._archive_md = _ResultMetadata(zf, root_metadata_fp)

            # populate it with relevant uuid:file_contents pairs
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
            if uuid == self.get_root_uuid():
                fps_for_this_result = filter(self._is_root_prov_data,
                                             prov_data_fps)
                # for fp in fps_for_this_result:
                #     print(fp)
            else:
                fps_for_this_result = itertools.filterfalse(
                    self._is_root_prov_data, prov_data_fps)
                fps_for_this_result = (fp for fp in fps_for_this_result if
                                       self._check_nonroot_uuid(fp, uuid))

            self._archive_contents[uuid] = ProvNode(zf, fps_for_this_result)
            self._number_of_results += 1

    # TODO: refactor as read-only @properties
    def get_root_uuid(self):
        return self._archive_md.uuid

    def get_arch_type(self):
        return self._archive_md.type

    def get_arch_format(self):
        return self._archive_md.format

    def get_file_contents(self):
        return self._file_contents

    def get_contents_by_uuid(self, uuid: str):
        return self._file_contents[uuid]

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
        # TODO: will not reliably find root version b/c root uuid in all names
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

    def _is_root_prov_data(self, fp):
        fp = self._normalize_path_iteration(fp)
        return (self._is_prov_data(fp) and 'artifacts' not in fp)

    def _is_root_metadata_file(self, fp):
        fp = self._normalize_path_iteration(fp)
        return (self._is_root_prov_data(fp) and 'metadata.yaml' in fp)


class ProvNode:
    """ One node of a provenance tree, describing one QIIME 2 Result """

    def __init__(self, zf: zipfile,
                 fps_for_this_result: Iterator[pathlib.Path]):
        # TODO: Read and check VERSION
        # (this will probably effect what other things get read in)
        for fp in fps_for_this_result:
            # TODO: Should we be reading these zipfiles once here,
            # and then passing them to the constructors below?
            # print("A filepath: " + str(fp))
            if fp.name == 'metadata.yaml':
                self._result_md = _ResultMetadata(zf, str(fp))
                # print(f"Metadata parsed for {self._result_md.uuid}")
            elif fp.name == 'action.yaml':
                self._action = _Action(zf, str(fp))
            elif fp.name == 'citations.bib':
                self._citations = _Citations(zf, str(fp))
                pass


class _ResultMetadata:
    """ Basic metadata about a single QIIME 2 Result from metadata.yaml """

    def __init__(self, zf: zipfile, md_fp: str):
        _md_dict = yaml.safe_load(zf.read(md_fp))
        self.uuid = _md_dict['uuid']
        self.type = _md_dict['type']
        self.format = _md_dict['format']


class _Action:
    """ Provenance data for a single QIIME 2 Result from action.yaml """

    def __init__(self, zf: zipfile, fp: str):
        self._action_dict = yaml.safe_load(zf.read(fp))
        self._action_details = self._action_dict['action']
        self._execution_details = self._action_dict['execution']
        self._env_details = self._action_dict['environment']
        # print(f"In _Action {self._action_dict['execution']['uuid']}")
        # if (self._action_dict['execution']['uuid'] ==
        #         '5bc4b090-abbc-46b0-a219-346c8026f7d7'):
        #     print(self._action_details)
        #     print(self._action_dict['action'])


class _Citations:
    """
    citations for a single QIIME 2 Result, as a dict of dicts where each
    inner dictionary represents one citation keyed on the citation's bibtex key
    """
    def __init__(self, zf: zipfile, fp: str):
        bib_db = bp.loads(zf.read(fp))
        self._citations = {entry['ID']: entry for entry in bib_db.entries}
        # if 'f8788dfa-f50b-46d2-a59c-72fea3c05333' in fp:
        #     for k in self._citations:
        #         print(k)
