# import yaml
import zipfile


def _validate_fp(archive_fp):
    # TODO: implement this, or more likely, integrate it elsewhere
    # Is it a filepath?

    # Is it a valid zip archive?
    if zipfile.is_zipfile(archive_fp):
        print("Tada")

    # is it a valid QIIME 2 archive (this probably can't be determined here)
    raise NotImplementedError


def _get_relevant_files(archive_fp):
    pass


def parse_archive(archive_fp):
    # _validate_fp(archive_fp)
    # Instantiate ArchiveContents

    # save archive root id
    # deserialize actions
    # build a tree
    raise NotImplementedError


class ArchiveContents:
    """Lightly-processed contents of a single QIIME 2 Archive"""

    def __init__(self, archive_fp):
        # get relevant files
        with zipfile.ZipFile(archive_fp) as zf:
            print(zf.infolist()[0])

        # TODO: actually assign these
        self.__root_uuid = ""
        self.__file_contents = dict()

    def get_root_uuid(self):
        return self.__root_uuid

    def get_file_contents(self):
        return self.__file_contents
