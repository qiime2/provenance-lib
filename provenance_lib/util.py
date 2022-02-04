import pathlib
import zipfile

# Alias string as UUID so we can specify types more clearly
UUID = str

# Alias string as FileName because that's what some strings mean
# FileNames are not path objects - just strings that describe paths
FileName = str


def get_root_uuid(zf: zipfile.ZipFile) -> UUID:
    """
    Returns the root UUID for a QIIME 2 Archive.

    There's no particular reason we use the first filename here.  All QIIME 2
    Artifacts store their contents in a directory named with the Artifact's
    UUID, so we can get the UUID of an artifact by taking the first part of the
    filepath of any file in the zip archive.
    """
    return pathlib.Path(zf.namelist()[0]).parts[0]


def get_nonroot_uuid(fp: pathlib.Path) -> UUID:
    """
    For non-root provenance files, get the Result's uuid from the path
    (avoiding the root Result's UUID which is in all paths)
    """
    if fp.name == 'action.yaml':
        uuid = fp.parts[-3]
    else:
        uuid = fp.parts[-2]
    return uuid
