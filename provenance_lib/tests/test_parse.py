import os
import pathlib
import unittest
from unittest.mock import MagicMock

import zipfile

from ..parse import Archive, ProvNode
# from ..parse import ProvTree


DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')


class ArchiveTests(unittest.TestCase):
    # Removes the character limit when reporting failing tests for this class
    maxDiff = None

    v5_qza = os.path.join(DATA_DIR, 'unweighted_unifrac_emperor.qzv')
    fake_fp = os.path.join(DATA_DIR, 'not_a_filepath.qza')
    not_a_zip = os.path.join(DATA_DIR, 'not_a_zip.txt')

    v5_archive = Archive(v5_qza)

    def test_smoke(self):
        self.assertEqual(self.v5_archive.root_uuid,
                         "8854f06a-872f-4762-87b7-4541d0f283d4")

    def test_str(self):
        self.assertEqual(str(self.v5_archive),
                         "Archive(Root: 8854f06a-872f-4762-87b7-4541d0f283d4)")

    def test_repr(self):
        repr(self.v5_archive)
        self.assertRegex(repr(self.v5_archive),
                         "Archive.*Root.*Semantic Type.*Format.*\nContains.*")

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

    # TODO: Test does it check archive version?
    # Does it recognize out-of-format archives?
    def test_no_root_md(self):
        pass

    def test_multiple_root_md(self):
        pass


class ResultMetadataTests(unittest.TestCase):
    pass


class ActionTests(unittest.TestCase):
    pass


class CitationsTests(unittest.TestCase):
    pass


class ProvNodeTests(unittest.TestCase):
    # As implemented, ProvNodes must belong to an Archive
    # 1281878510acdc42cb5ba3ee40c9ad8b62dacf0e shows another approach with
    # ProvTrees responsible for assigning parentage to their ProvNodes
    mock_archive = MagicMock()

    def setUp(self):
        self.v5_qza = os.path.join(DATA_DIR, 'unweighted_unifrac_emperor.qzv')
        super().setUp()
        self.root_metadata_fps = None

        with zipfile.ZipFile(self.v5_qza) as zf:
            all_filenames = zf.namelist()
            self.root_md_fnames = filter(self._is_provnode_data, all_filenames)
            self.root_md_fps = [pathlib.Path(fp) for fp in self.root_md_fnames]
            self.v5_ProvNode = ProvNode(self.mock_archive, zf,
                                        self.root_md_fps)

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
        # TODO: Is it problematic that format is loaded as a NoneType (not str)
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

    def test_traverse_uuids(self):
        pass

    # Building an archive for the following 2 tests b/c the alternative is to
    # hand-build two to three more test nodes and mock an Archive to hold them.
    def test_has_no_parents(self):
        # qiime tools import node has no parents
        parentless_node_id = 'f5d67104-9506-4373-96e2-97df9199a719'
        archive = Archive(self.v5_qza)
        repr(archive)
        parentless_node = archive.get_result(parentless_node_id)
        # _parents not initialized before call
        self.assertEqual(parentless_node._parents, None)
        # ProvNode.parents should get parents - here that's None
        self.assertEqual(parentless_node.parents, None)
        # _parents initialized now
        self.assertEqual(parentless_node._parents, None)

    def test_has_parents(self):
        self.v5_ProvNode._origin_archive = Archive(self.v5_qza)
        exp_nodes = [self.v5_ProvNode._origin_archive._archive_contents[id]
                     for id in ['706b6bce-8f19-4ae9-b8f5-21b14a814a1b',
                                'ad7e5b50-065c-4fdd-8d9b-991e92caad22']]
        # _parents not initialized before call
        self.assertEqual(self.v5_ProvNode._parents, None)
        # ProvNode.parents should get parents
        self.assertEqual(self.v5_ProvNode.parents, exp_nodes)
        # _parents initialized now
        self.assertEqual(self.v5_ProvNode._parents, exp_nodes)


class ProvTreeTests(unittest.TestCase):
    pass


class UnionedTreeTests(unittest.TestCase):
    pass
