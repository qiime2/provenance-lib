import unittest
import zipfile

from .test_parse import TEST_DATA
from ..util import get_root_uuid


class GetRootUUIDTests(unittest.TestCase):
    def test_get_root_uuid(self):
        for archive_version in TEST_DATA:
            fp = TEST_DATA[archive_version]['qzv_fp']
            exp = TEST_DATA[archive_version]['uuid']
            with zipfile.ZipFile(fp) as zf:
                self.assertEqual(exp, get_root_uuid(zf))
