import codecs
import os
import unittest
import zipfile

from .test_parse import DATA_DIR, TEST_DATA
from ..version_parser import _VERSION_MATCHER, get_version


class GetVersionTests(unittest.TestCase):
    v5_no_version = os.path.join(DATA_DIR, 'VERSION_missing.qzv')
    v5_qzv_version_bad = os.path.join(DATA_DIR, 'VERSION_bad.qzv')
    v5_qzv_version_short = os.path.join(DATA_DIR, 'VERSION_short.qzv')
    v5_qzv_version_long = os.path.join(DATA_DIR, 'VERSION_long.qzv')

    # High-level checks only. Detailed tests of the VERSION_MATCHER regex are
    # in test_archive_formats.VersionMatcherTests to reduce overhead

    def test_get_version_no_VERSION_file(self):
        with zipfile.ZipFile(self.v5_no_version) as zf:
            with self.assertRaisesRegex(ValueError, 'VERSION.*nonexistent'):
                get_version(zf)

    def test_get_version_VERSION_bad(self):
        with zipfile.ZipFile(self.v5_qzv_version_bad) as zf:
            with self.assertRaisesRegex(ValueError, 'VERSION.*out of spec'):
                get_version(zf)

    def test_short_VERSION(self):
        with zipfile.ZipFile(self.v5_qzv_version_short) as zf:
            with self.assertRaisesRegex(ValueError, 'VERSION.*out of spec'):
                get_version(zf)

    def test_long_VERSION(self):
        with zipfile.ZipFile(self.v5_qzv_version_long) as zf:
            with self.assertRaisesRegex(ValueError, 'VERSION.*out of spec'):
                get_version(zf)

    def test_version_nums(self):
        for arch_ver in TEST_DATA:
            qzv = os.path.join(DATA_DIR, 'v' + arch_ver + '_uu_emperor.qzv')
            with zipfile.ZipFile(qzv) as zf:
                exp_arch, exp_frmwk = get_version(zf)
                self.assertEqual(exp_arch, TEST_DATA[arch_ver]['av'])
                self.assertEqual(exp_frmwk, TEST_DATA[arch_ver]['fwv'])


class ArchiveVersionMatcherTests(unittest.TestCase):
    """Testing for the _VERSION_MATCHER regex itself"""

    def test_version_too_short(self):
        shorty = (
            r'QIIME 2\n'
            r'archive: 4'
        )
        self.assertNotRegex(shorty, _VERSION_MATCHER)

    def test_version_too_long(self):
        longy = (
            r'QIIME 2\n'
            r'archive: 4\n'
            r'framework: 2019.8.1.dev0\n'
            r'This line should not be here'
        )
        self.assertNotRegex(longy, _VERSION_MATCHER)

    splitvm = codecs.decode(_VERSION_MATCHER, 'unicode-escape').split(sep='\n')
    re_l1, re_l2, re_l3 = splitvm

    def test_line1_good(self):
        self.assertRegex('QIIME 2\n', self.re_l1)

    def test_line1_bad(self):
        self.assertNotRegex('SHIMMY 2\n', self.re_l1)

    def test_archive_version_1digit_numeric(self):
        self.assertRegex('archive: 1\n', self.re_l2)

    def test_archive_version_2digit_numeric(self):
        self.assertRegex('archive: 12\n', self.re_l2)

    def test_archive_version_bad(self):
        self.assertNotRegex('agama agama\n', self.re_l2)

    def test_archive_version_3digit_numeric(self):
        self.assertNotRegex('archive: 123\n', self.re_l2)

    def test_archive_version_nonnumeric(self):
        self.assertNotRegex('archive: 1a\n', self.re_l2)

    def test_fmwk_version_good_semver(self):
        self.assertRegex('framework: 2.0.6', self.re_l3)

    def test_fmwk_version_good_semver_dev(self):
        self.assertRegex('framework: 2.0.6.dev0', self.re_l3)

    def test_fmwk_version_good_year_month_patch(self):
        self.assertRegex('framework: 2020.2.0', self.re_l3)

    def test_fmwk_version_good_year_month_patch_2digit_month(self):
        self.assertRegex('framework: 2018.11.0', self.re_l3)

    def test_fmwk_version_good_year_month_patch_dev(self):
        self.assertRegex('framework: 2020.2.0.dev1', self.re_l3)

    def test_fmwk_version_good_ymp_2digit_month_dev(self):
        self.assertRegex('framework: 2020.11.0.dev0', self.re_l3)

    def test_fmwk_version_invalid_month(self):
        self.assertNotRegex('framework: 2020.13.0', self.re_l3)

    def test_fmwk_version_invalid_month_leading_zero(self):
        self.assertNotRegex('framework: 2020.03.0', self.re_l3)

    def test_fmwk_version_invalid_year(self):
        self.assertNotRegex('framework: 1953.3.0', self.re_l3)
