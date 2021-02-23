import sys

from parse import ArchiveContents

if __name__ == '__main__':
    # To begin, we'll read in exactly one fp
    if len(sys.argv) != 2:
        raise ValueError('Please pass one filepath to a QIIME 2 Archive')

    archive_fp = sys.argv[1]
    dummy_archive = ArchiveContents(archive_fp)
    print(dummy_archive.get_root_uuid())
