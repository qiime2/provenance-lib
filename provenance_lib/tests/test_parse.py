import os
import pathlib
import unittest
from unittest.mock import MagicMock

import zipfile

from ..parse import Archive, ProvNode
# from ..parse import ProvTree


DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')


class ArchiveTests(unittest.TestCase):

    v5_qza = os.path.join(DATA_DIR, 'unweighted_unifrac_emperor.qzv')
    fake_fp = os.path.join(DATA_DIR, 'not_a_filepath.qza')
    not_a_zip = os.path.join(DATA_DIR, 'not_a_zip.txt')

    def test_smoke(self):
        contents = Archive(self.v5_qza)
        self.assertEqual(contents.get_root_uuid(),
                         "8854f06a-872f-4762-87b7-4541d0f283d4")

    def test_number_of_actions(self):
        contents = Archive(self.v5_qza)
        self.assertEqual(contents._number_of_results, 15)

    def test_nonexistent_fp(self):
        with self.assertRaisesRegex(FileNotFoundError, "not_a_filepath.qza"):
            Archive(self.fake_fp)

    def test_not_a_zip_archive(self):
        with self.assertRaisesRegex(zipfile.BadZipFile,
                                    "File is not a zip file"):
            Archive(self.not_a_zip)

    # Test does it check archive version?
    # Does it recognize out-of-format archives?


class ProvNodeTests(unittest.TestCase):
    def setUp(self):
        self.v5_qza = os.path.join(DATA_DIR, 'unweighted_unifrac_emperor.qzv')
        super().setUp()
        self.root_metadata_fps = None

        with zipfile.ZipFile(self.v5_qza) as zf:
            all_filenames = zf.namelist()
            self.root_md_fnames = filter(self._is_provnode_data, all_filenames)
            self.root_md_fps = [pathlib.Path(fp) for fp in self.root_md_fnames]
            self.v5_ProvNode = ProvNode(zf, self.root_md_fps)

    def _is_provnode_data(self, fp):
        """
        a filter predicate which returns metadata, action, citation,
        and VERSION fps with which we can construct a ProvNode
        """
        # TODO: add VERSION.
        return 'provenance' in fp and 'artifacts' not in fp and (
            'metadata.yaml' in fp or
            'action.yaml' in fp or
            'citations.bib' in fp)

    def test_smoke(self):
        self.assertIs(type(self.v5_ProvNode), ProvNode)

    def test_v5_viz_md(self):
        print(self.v5_ProvNode)
        self.assertEqual(self.v5_ProvNode.uuid,
                         '8854f06a-872f-4762-87b7-4541d0f283d4')
        self.assertEqual(self.v5_ProvNode.sem_type, 'Visualization')
        # TODO: Is it problematic that format is stored as a NoneType (not str)
        self.assertEqual(self.v5_ProvNode.format, None)

    def test_eq(self):
        self.assertEqual(self.v5_ProvNode, self.v5_ProvNode)
        mock_node = MagicMock()
        mock_node.uuid = '8854f06a-872f-4762-87b7-4541d0f283d4'
        self.assertEqual(self.v5_ProvNode, mock_node)
        mock_node.uuid = 'gerbil'
        self.assertNotEqual(self.v5_ProvNode, mock_node)

    def test_str(self):
        self.assertEqual(str(self.v5_ProvNode),
                         "ProvNode(8854f06a-872f-4762-87b7-4541d0f283d4)")

    def test_repr(self):
        self.assertEqual(repr(self.v5_ProvNode),
                         "ProvNode(8854f06a-872f-4762-87b7-4541d0f283d4, "
                         "Visualization, fmt=None)")

    def test_traverse_ids(self):
        pass

# class ProvTreeTests(unittest.TestCase):
#     pass
