import collections
import hashlib
import io
import pathlib
import warnings
import zipfile
from typing import Optional, Tuple

from .version_parser import parse_version


ChecksumDiff = collections.namedtuple(
    'ChecksumDiff', ['added', 'removed', 'changed'])


def validate_checksums(zf: zipfile.ZipFile) -> Tuple[bool,
                                                     Optional[ChecksumDiff]]:
    """
    Uses diff_checksums to validate the archive's provenance, warning the user
    if checksums.md5 is missing, or if the archive is corrupt/has been modified
    """
    provenance_is_valid = True
    checksum_diff = None

    # TODO: Try/except should be in diff_checksums, where the file io happens

    try:
        checksum_diff = diff_checksums(zf)
        if checksum_diff != ChecksumDiff({}, {}, {}):
            # self._result_md may not have been parsed, so get uuid
            root_uuid = pathlib.Path(zf.namelist()[0]).parts[0]
            warnings.warn(
                f"Checksums are invalid for Archive {root_uuid}\n"
                "Archive may be corrupt or provenance may be false"
                ".\n"
                f"Files added since archive creation: {checksum_diff[0]}\n"
                f"Files removed since archive creation: {checksum_diff[1]}"
                "\n"
                f"Files changed since archive creation: {checksum_diff[2]}",
                UserWarning)
            provenance_is_valid = False
    # zipfiles KeyError if file not found. warn if checksums.md5 is missing
    except KeyError as err:
        warnings.warn(
            str(err).strip('"') +
            ". Archive may be corrupt or provenance may be false",
            UserWarning)
        provenance_is_valid = False

    return (provenance_is_valid, checksum_diff)


def diff_checksums(zf: zipfile.ZipFile) -> ChecksumDiff:
    """
    Calculates checksums for all files in an archive (excepting checksums.md5)
    Compares these against the checksums stored in checksums.md5, returning
    a summary ChecksumDiff

    For archive formats prior to v5, returns an empty diff b/c checksums.md5
    does not exist

    Code adapted from qiime2/core/archive/archiver.py
    """
    archive_version, _ = parse_version(zf)
    if int(archive_version) < 5:
        return ChecksumDiff({}, {}, {})

    root_dir = pathlib.Path(pathlib.Path(zf.namelist()[0]).parts[0])
    checksum_filename = root_dir / 'checksums.md5'
    obs = dict(x for x in md5sum_directory(zf).items()
               if x[0] != checksum_filename)
    exp = dict(from_checksum_format(line) for line in
               zf.open(str(checksum_filename))
               )
    obs_keys = set(obs)
    exp_keys = set(exp)

    added = {x: obs[x] for x in obs_keys - exp_keys}
    removed = {x: exp[x] for x in exp_keys - obs_keys}
    changed = {x: (exp[x], obs[x]) for x in exp_keys & obs_keys
               if exp[x] != obs[x]}

    return ChecksumDiff(added=added, removed=removed, changed=changed)


def md5sum_directory(zf: zipfile.ZipFile) -> dict:
    """
    returns a mapping of fp/checksum pairs from which the root uuid dir
    has been removed.

    This mimics the output in checksums.md5 (without sorted descent), but is
    not generalizable beyond QIIME 2 archives

    Code adapted from qiime2/core/util.py
    """
    sums = dict()
    for file in zf.namelist():
        fp = pathlib.Path(file)
        if fp.name != 'checksums.md5':
            file_parts = list(fp.parts)
            fp_w_o_root_uuid = pathlib.Path(*(file_parts[1:]))
            sums[str(fp_w_o_root_uuid)] = md5sum(zf, file)
    return sums


def md5sum(zf: zipfile.ZipFile, filepath: str) -> str:
    """
    Given a ZipFile object and relative filepath within the zip archive,
    returns the md5sum of the file

    Code adapted from qiime2/core/util.py
    """
    md5 = hashlib.md5()
    with zf.open(filepath) as fh:
        for chunk in iter(lambda: fh.read(io.DEFAULT_BUFFER_SIZE), b""):
            md5.update(chunk)
    return md5.hexdigest()


def from_checksum_format(line_bytes: bytes) -> Tuple[str, str]:
    """
    Given one line of bytes from a checksums.md5 file,
    parses the line and returns the filepath and that file's recorded checksum

    We expect a line to look roughly like this:
    2eb067afb7ba4eefe89a0416ab16f688  provenance/metadata.yaml

    ...with checksum followed by relative filepath (excluding root UUID dir)

    Code adapted from qiime2/core/util.py
    """
    line = str(line_bytes, 'utf-8').rstrip('\n')
    parts = line.split('  ', 1)
    if len(parts) < 2:
        parts = line.split(' *', 1)

    checksum, filepath = parts

    if checksum[0] == '\\':
        chars = ''
        escape = False
        # Gross, but regular `.replace` will overlap with itself and
        # negative lookbehind in regex is *probably* harder than scanning
        for char in filepath:
            # 1) Escape next character
            if not escape and char == '\\':
                escape = True
                continue

            # 2) Handle escape sequence
            if escape:
                try:
                    chars += {'\\': '\\', 'n': '\n'}[char]
                except KeyError:
                    chars += '\\' + char  # Wasn't an escape after all
                escape = False
                continue

            # 3) Nothing interesting
            chars += char

        checksum = checksum[1:]
        filepath = chars

    return filepath, checksum
