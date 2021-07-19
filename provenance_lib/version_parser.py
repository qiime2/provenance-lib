import codecs
import pathlib
import re
import zipfile
from typing import Optional, Tuple

_VERSION_MATCHER = (
    r'QIIME 2\n'
    r'archive: [0-9]{1,2}$\n'
    r'framework: '
    r'(?:20[0-9]{2}|2)\.(?:[1-9][0-2]?|0)\.[0-9](?:\.dev[0-9]?)?\Z')


def get_version(zf: zipfile.ZipFile,
                fp: Optional[pathlib.Path] = None) -> Tuple[str]:
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
