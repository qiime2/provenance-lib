import collections
from enum import Enum
import hashlib
import io
import pathlib
import warnings
import zipfile
from typing import Optional, Tuple

from .version_parser import parse_version


ChecksumDiff = collections.namedtuple(
    'ChecksumDiff', ['added', 'removed', 'changed'])


class ValidationCodes(Enum):
    """
    Codes indicating the level of validation a ProvDAG has passed.

    The code that determines what ValidationCode an archive receives is by
    necessity scattered. Though not ideal, this is probably the best
    "central" location to keep information on when these codes will occur.

    INVALID: one or more files are known to be missing or unparseable. Occurs
        either when checksum validation fails, or when expected files are
        absent or unparseable.
    VALIDATION_OPTOUT: The user opted out of checksum validation. This will be
        overridden by INVALID iff a required file is missing. In this context,
        `checksums.md5` is not required. If data files, for example, have been
        manually modified, the code will remain VALIDATION_OPTOUT, but if an
        action.yaml file is missing, INVALID will result.
    PREDATES_CHECKSUMS: The archive format predates the creation of
        checksums.md5, so full validation is impossible. We initially assume
        validity. This will be overridden by INVALID iff an expected file is
        missing or unparseable.  If data files, for example, have been manually
        modified, the code will remain PREDATES_CHECKSUMS
    VALID: The archive has passed checksum validation and is "known" to be
        valid. Md5 checksums are technically falsifiable, so this is not a
        guarantee of correctness/authenticity. It would, however, require a
        significant and unlikely effort at falsification of results to render
        this untrue.
    """
    INVALID = 0                 # Archive is known to be invalid
    VALIDATION_OPTOUT = 1       # User opted out of validation
    PREDATES_CHECKSUMS = 2      # v0-v4 cannot be validated, so assume validity
    VALID = 3                   # Archive known to be valid


def validate_checksums(zf: zipfile.ZipFile) -> Tuple[ValidationCodes,
                                                     Optional[ChecksumDiff]]:
    """
    Uses diff_checksums to validate the archive's provenance, warning the user
    if checksums.md5 is missing, or if the archive is corrupt/has been modified
    """
    provenance_is_valid = ValidationCodes.VALID
    checksum_diff = None

    # One broad try/except here saves us many down the call stack
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
            provenance_is_valid = ValidationCodes.INVALID
    # zipfiles KeyError if file not found. warn if checksums.md5 or any of the
    # filepaths it contains are missing
    except KeyError as err:
        warnings.warn(
            str(err).strip('"') +
            ". Archive may be corrupt or provenance may be false",
            UserWarning)
        provenance_is_valid = ValidationCodes.INVALID

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
