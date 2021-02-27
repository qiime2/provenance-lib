import itertools
import pathlib
from typing import Iterator

import yaml
import zipfile


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


class _ArchiveMetadata:
    """Basic metadata about a single QIIME 2 Archive"""

    def __init__(self, zf: zipfile, md_fp: str):
        _md_dict = yaml.safe_load(zf.read(md_fp))
        self.uuid = _md_dict['uuid']
        self.type = _md_dict['type']
        self.format = _md_dict['format']


class Archive:
    """Lightly-processed contents of a single QIIME 2 Archive"""

    def __init__(self, archive_fp: str):
        self._number_of_actions = 0
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

            self._archive_md = _ArchiveMetadata(zf, root_metadata_fp)

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
            fps_for_this_action = Iterator
            if uuid == self.get_root_uuid():
                fps_for_this_action = filter(self._is_root_prov_data,
                                             prov_data_fps)
                for fp in fps_for_this_action:
                    print(fp)
            else:
                fps_for_this_action = itertools.filterfalse(
                    self._is_root_prov_data, prov_data_fps)
                fps_for_this_action = (fp for fp in fps_for_this_action if
                                       self._check_nonroot_uuid(fp, uuid))

            self._archive_contents[uuid] = ProvNode(fps_for_this_action)
            self._number_of_actions += 1

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
        if fp.name == 'action.yaml':
            uuid = fp.parts[-3]
        else:
            uuid = fp.parts[-2]
        return uuid

    def _check_nonroot_uuid(self, fp, uuid):
        """ For non-root provenance files only, get the uuid from the path """
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
    """ One node of a provenance tree, describing one QIIME 2 Action """

    def __init__(self, fps_for_this_action: Iterator[pathlib.Path]):
        # TODO: Read and check VERSION
        # (this will probably effect what other things get read in)
        for fp in fps_for_this_action:
            print("A filepath: " + str(fp))
        print("In ProvNode constructor")

        # TODO: Read in metadata.yaml as medatadat object
        # TODO: Read in action.yaml
        # TODO: Read in citations.bib
