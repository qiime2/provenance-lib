import os
import pathlib
import unittest
from unittest.mock import MagicMock

import zipfile

from ..parse import Archive, ProvNode, ProvTree
from ..parse import _Action, _Citations, _ResultMetadata


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
        # TODO: See parse.py l.232
        pass

    def test_multiple_root_md(self):
        # TODO: See parse.py l.232
        pass


class ResultMetadataTests(unittest.TestCase):
    v5_qza = os.path.join(DATA_DIR, 'unweighted_unifrac_emperor.qzv')
    md_fp = "8854f06a-872f-4762-87b7-4541d0f283d4/provenance/metadata.yaml"
    with zipfile.ZipFile(v5_qza) as zf:
        v5_root_md = _ResultMetadata(zf, md_fp)

    def test_smoke(self):
        self.assertEqual(self.v5_root_md.uuid,
                         "8854f06a-872f-4762-87b7-4541d0f283d4")
        self.assertEqual(self.v5_root_md.type, "Visualization")
        self.assertEqual(self.v5_root_md.format, None)

    def test_repr(self):
        exp = ("_ResultMetadata(UUID: "
               "8854f06a-872f-4762-87b7-4541d0f283d4, "
               "Semantic Type: Visualization, Format: None)")
        self.assertEqual(repr(self.v5_root_md), exp)


class ActionTests(unittest.TestCase):
    action_fp = os.path.join(DATA_DIR, 'action.zip')
    with zipfile.ZipFile(action_fp) as zf:
        act = _Action(zf, 'action.yaml')

    def test_action_id(self):
        exp = "5bc4b090-abbc-46b0-a219-346c8026f7d7"
        self.assertEqual(self.act.action_id, exp)

    def test_action_type(self):
        exp = "pipeline"
        self.assertEqual(self.act.action_type, exp)

    def test_action(self):
        exp = "core_metrics_phylogenetic"
        self.assertEqual(self.act.action, exp)

    def test_plugin(self):
        exp = "diversity"
        self.assertEqual(self.act.plugin, exp)

    def test_inputs(self):
        exp = [{"table": "706b6bce-8f19-4ae9-b8f5-21b14a814a1b"},
               {"phylogeny": "ad7e5b50-065c-4fdd-8d9b-991e92caad22"}]
        self.assertEqual(self.act.inputs, exp)

    def test_repr(self):
        exp = ("_Action(action_id=5bc4b090-abbc-46b0-a219-346c8026f7d7, "
               "type=pipeline, plugin=diversity, "
               "action=core_metrics_phylogenetic)")
        self.assertEqual(repr(self.act), exp)


class CitationsTests(unittest.TestCase):
    cite_strs = ['cite_none', 'cite_one', 'cite_many']
    bibs = [bib+".bib" for bib in cite_strs]
    zips = [os.path.join(DATA_DIR, bib+".zip") for bib in cite_strs]

    def test_empty_bib(self):
        with zipfile.ZipFile(self.zips[0]) as zf:
            citations = _Citations(zf, self.bibs[0])
            # Is the _citations dict empty?
            self.assertFalse(len(citations._citations))

    def test_citation(self):
        with zipfile.ZipFile(self.zips[1]) as zf:
            exp = "framework"
            citations = _Citations(zf, self.bibs[1])
            for key in citations._citations.keys():
                self.assertRegex(key, exp)

    def test_many_citations(self):
        exp = ["2020.6.0.dev0", "unweighted_unifrac.+0",
               "unweighted_unifrac.+1", "unweighted_unifrac.+2",
               "unweighted_unifrac.+3", "unweighted_unifrac.+4",
               "BIOMV210DirFmt", "BIOMV210Format"]
        with zipfile.ZipFile(self.zips[2]) as zf:
            citations = _Citations(zf, self.bibs[2])
            for i, key in enumerate(citations._citations.keys()):
                print(key, exp[i])
                self.assertRegex(key, exp[i])

    def test_repr(self):
        exp = ("Citations(['framework|qiime2:2020.6.0.dev0|0'])")
        with zipfile.ZipFile(self.zips[1]) as zf:
            citations = _Citations(zf, self.bibs[1])
            self.assertEqual(repr(citations), exp)


def _is_provnode_data(fp):
    """
    a filter predicate which returns metadata, action, citation,
    and VERSION fps with which we can construct a ProvNode
    """
    # TODO: add VERSION.
    return 'provenance' in fp and 'artifacts' not in fp and (
        'metadata.yaml' in fp or
        'action.yaml' in fp or
        'citations.bib' in fp)


class ProvNodeTests(unittest.TestCase):
    # As implemented, ProvNodes must belong to an Archive. Commit
    # 1281878510acdc42cb5ba3ee40c9ad8b62dacf0e shows another approach with
    # ProvTrees responsible for assigning parentage to their ProvNodes
    mock_archive = MagicMock()

    def setUp(self):
        self.v5_qza = os.path.join(DATA_DIR, 'unweighted_unifrac_emperor.qzv')
        super().setUp()
        self.root_metadata_fps = None

        with zipfile.ZipFile(self.v5_qza) as zf:
            all_filenames = zf.namelist()
            self.root_md_fnames = filter(_is_provnode_data, all_filenames)
            self.root_md_fps = [pathlib.Path(fp) for fp in self.root_md_fnames]
            self.v5_ProvNode = ProvNode(self.mock_archive, zf,
                                        self.root_md_fps)

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

    maxDiff = None

    # TODO: This should probably be reduced to a minimum example
    def test_traverse_uuids(self):
        # This is disgusting, but avoids a baffling syntax error raised
        # whenever I attempted to define exp as a single literal
        exp = {"8854f06a-872f-4762-87b7-4541d0f283d4":
               {"706b6bce-8f19-4ae9-b8f5-21b14a814a1b":
                {"4de0fc23-6462-43d3-8497-f55fc49f5db6":
                 {"f5d67104-9506-4373-96e2-97df9199a719": None}}}}
        second_half = {"ad7e5b50-065c-4fdd-8d9b-991e92caad22":
                       {"b662f326-ac26-4047-8766-2288464d157d":
                        {"4de0fc23-6462-43d3-8497-f55fc49f5db6":
                         {"f5d67104-9506-4373-96e2-97df9199a719": None}}}}
        exp["8854f06a-872f-4762-87b7-4541d0f283d4"].update(second_half)
        actual = self.v5_ProvNode.traverse_uuids()
        self.assertEqual(actual, exp)

    # Building an archive for the following 2 tests b/c the alternative is to
    # hand-build two to three more test nodes and mock an Archive to hold them.
    def test_parents_property_has_no_parents(self):
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

    def test_parents_property_has_parents(self):
        self.v5_ProvNode._origin_archives.append(Archive(self.v5_qza))
        exp_nodes = [self.v5_ProvNode._origin_archives[0]._archive_contents[id]
                     for id in ['706b6bce-8f19-4ae9-b8f5-21b14a814a1b',
                                'ad7e5b50-065c-4fdd-8d9b-991e92caad22']]
        # _parents not initialized before call
        self.assertEqual(self.v5_ProvNode._parents, None)
        # ProvNode.parents should get parents
        self.assertEqual(self.v5_ProvNode.parents, exp_nodes)
        # _parents initialized now
        self.assertEqual(self.v5_ProvNode._parents, exp_nodes)


class ProvTreeTests(unittest.TestCase):
    mock_archive = MagicMock()
    v5_qza = os.path.join(DATA_DIR, 'unweighted_unifrac_emperor.qzv')
    v5_archive = Archive(v5_qza)

    def setUp(self):
        super().setUp()
        self.root_metadata_fps = None

        with zipfile.ZipFile(self.v5_qza) as zf:
            all_filenames = zf.namelist()
            self.root_md_fnames = filter(_is_provnode_data, all_filenames)
            self.root_md_fps = [pathlib.Path(fp) for fp in self.root_md_fnames]
            self.v5_ProvNode = ProvNode(self.mock_archive, zf,
                                        self.root_md_fps)

    def test_smoke(self):
        ProvTree(self.v5_archive)
        self.assertTrue(True)

    def test_root_uuid(self):
        exp = "8854f06a-872f-4762-87b7-4541d0f283d4"
        actual_uuid = ProvTree(self.v5_archive).root_uuid
        self.assertEqual(exp, actual_uuid)

    def test_root_node_is_archive_root(self):
        self.assertEqual(self.v5_ProvNode, ProvTree(self.v5_archive).root)

    def test_str(self):
        dag = ProvTree(self.v5_archive)
        self.assertEqual(str(dag),
                         ("ProvTree("
                          "Root: 8854f06a-872f-4762-87b7-4541d0f283d4)"))

    def test_repr(self):
        dag = ProvTree(self.v5_archive)
        repr(dag)
        self.assertEqual(repr(dag),
                         ("Root:\n"
                          "8854f06a-872f-4762-87b7-4541d0f283d4:\n"
                          "  706b6bce-8f19-4ae9-b8f5-21b14a814a1b:\n"
                          "    4de0fc23-6462-43d3-8497-f55fc49f5db6:\n"
                          "      f5d67104-9506-4373-96e2-97df9199a719: null\n"
                          "  ad7e5b50-065c-4fdd-8d9b-991e92caad22:\n"
                          "    b662f326-ac26-4047-8766-2288464d157d:\n"
                          "      4de0fc23-6462-43d3-8497-f55fc49f5db6:\n"
                          "        f5d67104-9506-4373-96e2-97df9199a719: null"
                          "\n")
                         )


class UnionedTreeTests(unittest.TestCase):
    pass
