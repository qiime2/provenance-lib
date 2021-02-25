import os
import unittest

from ..parse import ArchiveContents


DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')


class ArchiveContentsTests(unittest.TestCase):

    v5_qza = os.path.join(DATA_DIR, 'unweighted_unifrac_emperor.qzv')

    def test_exists(self):
        self.assertTrue(True)

    def test_smoke(self):

        contents = ArchiveContents(self.v5_qza)
        self.assertEqual(contents.get_root_uuid(), "")
