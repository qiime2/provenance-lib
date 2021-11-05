import pathlib
import zipfile

# Alias string as UUID so we can specify types more clearly
UUID = str


def get_root_uuid(zf: zipfile.ZipFile) -> UUID:
    """
    Returns the root UUID for a QIIME 2 Archive.

    There's no particular reason we use the first filename here.  All QIIME 2
    Artifacts store their contents in a directory named with the Artifact's
    UUID, so we can get the UUID of an artifact by taking the first part of the
    filepath of any file in the zip archive.
    """
    return pathlib.Path(zf.namelist()[0]).parts[0]
