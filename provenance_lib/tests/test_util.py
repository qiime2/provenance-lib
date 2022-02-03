import unittest
import zipfile

from .test_parse import TEST_DATA
from .testing_utilities import CustomAssertions
from ..util import get_root_uuid


class GetRootUUIDTests(unittest.TestCase):
    def test_get_root_uuid(self):
        for archive_version in TEST_DATA:
            fp = TEST_DATA[archive_version]['qzv_fp']
            exp = TEST_DATA[archive_version]['uuid']
            with zipfile.ZipFile(fp) as zf:
                self.assertEqual(exp, get_root_uuid(zf))


class CustomAssertionsTests(CustomAssertions):
    def test_assert_re_appears_only_once(self):
        t = ("Lick an orange. It tastes like an orange.\n"
             "The strawberries taste like strawberries!\n"
             "The snozzberries taste like snozzberries!")
        self.assertREAppearsOnlyOnce(t, 'Lick an orange')
        self.assertREAppearsOnlyOnce(t, 'tastes like')
        with self.assertRaisesRegex(AssertionError, 'Regex.*match.*orange'):
            self.assertREAppearsOnlyOnce(t, 'orange')
        with self.assertRaisesRegex(AssertionError, 'Regex.*taste like'):
            self.assertREAppearsOnlyOnce(t, 'taste like')
        with self.assertRaisesRegex(AssertionError, 'Regex.*snozzberries'):
            self.assertREAppearsOnlyOnce(t, 'snozzberries')
        with self.assertRaisesRegex(AssertionError, 'Regex.*!'):
            self.assertREAppearsOnlyOnce(t, '!')
