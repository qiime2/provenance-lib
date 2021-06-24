import codecs
import os
import pathlib
import unittest
from unittest.mock import MagicMock

import zipfile

from ..archive_formats import _VERSION_MATCHER
from ..archive_formats import (
    ParserV0, ParserV1, ParserV2, ParserV3, ParserV4, ParserV5
)
from ..archive_formats import ProvNode, _Action, _Citations, _ResultMetadata
from ..parse import ProvDAG
from .util import is_provnode_data

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')


class ArchiveVersionMatcherTests(unittest.TestCase):
    """Testing for the _VERSION_MATCHER regex in parse.py"""

    def test_version_too_short(self):
        shorty = (
            r"QIIME 2\n"
            r"archive: 4"
        )
        self.assertNotRegex(shorty, _VERSION_MATCHER)

    def test_version_too_long(self):
        longy = (
            r"QIIME 2\n"
            r"archive: 4\n"
            r"framework: 2019.8.1.dev0\n"
            r"This line should not be here"
        )
        self.assertNotRegex(longy, _VERSION_MATCHER)

    splitvm = codecs.decode(_VERSION_MATCHER, 'unicode-escape').split(sep="\n")
    re_l1, re_l2, re_l3 = splitvm

    def test_line1_good(self):
        self.assertRegex("QIIME 2\n", self.re_l1)

    def test_line1_bad(self):
        self.assertNotRegex("SHIMMY 2\n", self.re_l1)

    def test_archive_version_1digit_numeric(self):
        self.assertRegex("archive: 1\n", self.re_l2)

    def test_archive_version_2digit_numeric(self):
        self.assertRegex("archive: 12\n", self.re_l2)

    def test_archive_version_bad(self):
        self.assertNotRegex("agama agama\n", self.re_l2)

    def test_archive_version_3digit_numeric(self):
        self.assertNotRegex("archive: 123\n", self.re_l2)

    def test_archive_version_nonnumeric(self):
        self.assertNotRegex("archive: 1a\n", self.re_l2)

    def test_fmwk_version_good_semver(self):
        self.assertRegex("framework: 2.0.6", self.re_l3)

    def test_fmwk_version_good_semver_dev(self):
        self.assertRegex("framework: 2.0.6.dev0", self.re_l3)

    def test_fmwk_version_good_year_month_patch(self):
        self.assertRegex("framework: 2020.2.0", self.re_l3)

    def test_fmwk_version_good_year_month_patch_2digit_month(self):
        self.assertRegex("framework: 2018.11.0", self.re_l3)

    def test_fmwk_version_good_year_month_patch_dev(self):
        self.assertRegex("framework: 2020.2.0.dev1", self.re_l3)

    def test_fmwk_version_good_ymp_2digit_month_dev(self):
        self.assertRegex("framework: 2020.11.0.dev0", self.re_l3)

    def test_fmwk_version_invalid_month(self):
        self.assertNotRegex("framework: 2020.13.0", self.re_l3)

    def test_fmwk_version_invalid_month_leading_zero(self):
        self.assertNotRegex("framework: 2020.03.0", self.re_l3)

    def test_fmwk_version_invalid_year(self):
        self.assertNotRegex("framework: 1953.3.0", self.re_l3)


class ParserVxTests(unittest.TestCase):
    # TODO: 0 should have a v0 archive
    cfg = {
        '0': {'uuid': 'ffb7cee3-2f1f-4988-90cc-efd5184ef003',
              'parser': ParserV0,
              'n_res': None
              },
        '1': {'uuid': '0b8b47bd-f2f8-4029-923c-0e37a68340c3',
              'parser': ParserV1,
              'n_res': 10,
              },
        '2a': {'uuid': '219c4bdf-f2b1-4b3f-b66a-08de8a4d17ca',
               'parser': ParserV2,
               'n_res': 10,
               },
        '2b': {'uuid': '8abf8dee-0047-4a7f-9826-e66893182978',
               'parser': ParserV2,
               'n_res': 14,
               },
        '3': {'uuid': '3544061c-6e2f-4328-8345-754416828cb5',
              'parser': ParserV3,
              'n_res': 14,
              },
        '4': {'uuid': '91c2189a-2d2e-4d53-98ee-659caaf6ffc2',
              'parser': ParserV4,
              'n_res': 14,
              },
        '5': {'uuid': 'ffb7cee3-2f1f-4988-90cc-efd5184ef003',
              'parser': ParserV5,
              'n_res': 15,
              },
        }

    for archv_vrsn in cfg.keys():
        qzv = os.path.join(DATA_DIR, 'v' + archv_vrsn + '_uu_emperor.qzv')
        root_uuid = cfg[archv_vrsn]['uuid']

        def test_get_root_md(self):
            with zipfile.ZipFile(self.qzv) as zf:
                root_md = self.cfg[self.archv_vrsn]['parser'].get_root_md(zf)
                self.assertEqual(root_md.uuid, self.root_uuid)
                self.assertEqual(root_md.type,  'Visualization')
                self.assertEqual(root_md.format, None)

        def test_populate_archive(self):
            with zipfile.ZipFile(self.qzv) as zf:
                if self.archv_vrsn == '0':
                    with self.assertRaisesRegex(NotImplementedError,
                                                "V0.*no.*provenance"):
                        self.cfg[self.archv_vrsn]['parser'].populate_archv(zf)
                else:
                    num_res, contents = \
                        self.cfg[self.archv_vrsn]['parser'].populate_archv(zf)
                    # Does this archive have the right number of Results?
                    self.assertEqual(num_res, 10)
                    # Is contents a dict?
                    self.assertEqual(dict, type(contents))
                    # Is contents keyed on uuids, containing ProvNodes?
                    self.assertEqual(ProvNode, type(contents[self.root_uuid]))
                    # Is the root UUID a key in the contents dict?
                    self.assertIn(self.root_uuid, contents)

            # NEXT: Why does archive 5 have 0 Results in it?
            # test_parse.test_number_of_actions returns 15 successfully.
            # NEXT: Coverage
            # Do we want a test here that considers all results somehow? Is
            # that niche already covered by our ProvDAG tests?


class ResultMetadataTests(unittest.TestCase):
    v5_qzv = os.path.join(DATA_DIR, 'v5_uu_emperor.qzv')
    md_fp = "ffb7cee3-2f1f-4988-90cc-efd5184ef003/provenance/metadata.yaml"
    with zipfile.ZipFile(v5_qzv) as zf:
        v5_root_md = _ResultMetadata(zf, md_fp)

    def test_smoke(self):
        self.assertEqual(self.v5_root_md.uuid,
                         "ffb7cee3-2f1f-4988-90cc-efd5184ef003")
        self.assertEqual(self.v5_root_md.type, "Visualization")
        self.assertEqual(self.v5_root_md.format, None)

    def test_repr(self):
        exp = ("UUID:\t\tffb7cee3-2f1f-4988-90cc-efd5184ef003\n"
               "Type:\t\tVisualization\n"
               "Data Format:\tNone")
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


class ProvNodeTests(unittest.TestCase):
    # As implemented, ProvNodes must belong to an ProvDAG. Commit
    # 1281878510acdc42cb5ba3ee40c9ad8b62dacf0e shows another approach with
    # ProvDAGs responsible for assigning parentage to their ProvNodes
    mock_archive = MagicMock()

    def setUp(self):
        self.v5_qzv = os.path.join(DATA_DIR, 'v5_uu_emperor.qzv')
        super().setUp()
        self.root_metadata_fps = None

        with zipfile.ZipFile(self.v5_qzv) as zf:
            all_filenames = zf.namelist()
            self.root_md_fnames = filter(is_provnode_data, all_filenames)
            self.root_md_fps = [pathlib.Path(fp) for fp in self.root_md_fnames]
            self.v5_ProvNode = ProvNode(self.mock_archive, zf,
                                        self.root_md_fps)

    def test_smoke(self):
        self.assertIs(type(self.v5_ProvNode), ProvNode)

    def test_v5_viz_md(self):
        print(self.v5_ProvNode)
        self.assertEqual(self.v5_ProvNode.uuid,
                         'ffb7cee3-2f1f-4988-90cc-efd5184ef003')
        self.assertEqual(self.v5_ProvNode.sem_type, 'Visualization')
        self.assertEqual(self.v5_ProvNode.format, None)

    def test_eq(self):
        self.assertEqual(self.v5_ProvNode, self.v5_ProvNode)
        mock_node = MagicMock()
        mock_node.uuid = 'ffb7cee3-2f1f-4988-90cc-efd5184ef003'
        self.assertEqual(self.v5_ProvNode, mock_node)
        mock_node.uuid = 'gerbil'
        self.assertNotEqual(self.v5_ProvNode, mock_node)

    def test_str(self):
        self.assertEqual(str(self.v5_ProvNode),
                         "ProvNode(ffb7cee3-2f1f-4988-90cc-efd5184ef003)")

    def test_repr(self):
        self.assertEqual(repr(self.v5_ProvNode),
                         "ProvNode(ffb7cee3-2f1f-4988-90cc-efd5184ef003, "
                         "Visualization, fmt=None)")

    maxDiff = None

    # TODO: This should probably be reduced to a minimum example
    def test_traverse_uuids(self):
        # This is disgusting, but avoids a baffling syntax error raised
        # whenever I attempted to define exp as a single literal
        exp = {"ffb7cee3-2f1f-4988-90cc-efd5184ef003":
               {"89af91c0-033d-4e30-8ac4-f29a3b407dc1":
                {"99fa3670-aa1a-45f6-ba8e-803c976a1163":
                 {"a35830e1-4535-47c6-aa23-be295a57ee1c": None}}}}
        second_half = {"bce3d09b-e296-4f2b-9af4-834db6412429":
                       {"7ecf8954-e49a-4605-992e-99fcee397935":
                        {"99fa3670-aa1a-45f6-ba8e-803c976a1163":
                         {"a35830e1-4535-47c6-aa23-be295a57ee1c": None}}}}
        exp["ffb7cee3-2f1f-4988-90cc-efd5184ef003"].update(second_half)
        actual = self.v5_ProvNode.traverse_uuids()
        self.assertEqual(actual, exp)

    # Building an archive for the following 2 tests b/c the alternative is to
    # hand-build two to three more test nodes and mock a ProvDAG to hold them.
    def test_parents_property_has_no_parents(self):
        # qiime tools import node has no parents
        parentless_node_id = 'a35830e1-4535-47c6-aa23-be295a57ee1c'
        archive = ProvDAG(self.v5_qzv)
        repr(archive)
        parentless_node = archive.get_result(parentless_node_id)
        # _parents not initialized before call
        self.assertEqual(parentless_node._parents, None)
        # ProvNode.parents should get parents - here that's None
        self.assertEqual(parentless_node.parents, None)
        # _parents initialized now
        self.assertEqual(parentless_node._parents, None)

    def test_parents_property_has_parents(self):
        self.v5_ProvNode._origin_parser.append(ProvDAG(self.v5_qzv))
        exp_nodes = [self.v5_ProvNode._origin_parser[0].archv_contents[id]
                     for id in ['89af91c0-033d-4e30-8ac4-f29a3b407dc1',
                                'bce3d09b-e296-4f2b-9af4-834db6412429']]
        # _parents not initialized before call
        self.assertEqual(self.v5_ProvNode._parents, None)
        # ProvNode.parents should get parents
        self.assertEqual(self.v5_ProvNode.parents, exp_nodes)
        # _parents initialized now
        self.assertEqual(self.v5_ProvNode._parents, exp_nodes)
