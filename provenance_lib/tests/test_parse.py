import os
import unittest

from zipfile import BadZipFile

from ..parse import Archive


DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')


class ArchiveTests(unittest.TestCase):

    v5_qza = os.path.join(DATA_DIR, 'unweighted_unifrac_emperor.qzv')
    fake_fp = os.path.join(DATA_DIR, 'not_a_filepath.qza')
    not_a_zip = os.path.join(DATA_DIR, 'not_a_zip.txt')

    def test_exists(self):
        self.assertTrue(True)

    def test_smoke(self):
        contents = Archive(self.v5_qza)
        self.assertEqual(contents.get_root_uuid(),
                         "8854f06a-872f-4762-87b7-4541d0f283d4")

    def test_number_of_actions(self):
        contents = Archive(self.v5_qza)
        self.assertEqual(contents._number_of_actions, 15)

    def test_nonexistent_fp(self):
        with self.assertRaisesRegex(FileNotFoundError, "not_a_filepath.qza"):
            Archive(self.fake_fp)

    def test_not_a_zip_archive(self):
        with self.assertRaisesRegex(BadZipFile, "File is not a zip file"):
            Archive(self.not_a_zip)
