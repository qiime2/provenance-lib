import os
import codecs
import pathlib
import unittest
from unittest.mock import MagicMock

import zipfile

from ..parse import (
    _VERSION_MATCHER, ProvDAG, UnionedDAG, ProvNode, FormatHandler,
    _Action, _Citations, _ResultMetadata,
    ParserV0, ParserV1, ParserV2, ParserV3, ParserV4, ParserV5,
)
from .util import is_provnode_data

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')


class ProvDAGTests(unittest.TestCase):
    # Remove the character limit when reporting failing tests for this class
    maxDiff = None

    v5_qzv = os.path.join(DATA_DIR, 'v5_uu_emperor.qzv')
    fake_fp = os.path.join(DATA_DIR, 'not_a_filepath.qza')
    not_a_zip = os.path.join(DATA_DIR, 'not_a_zip.txt')

    v5_provDag = ProvDAG(v5_qzv)

    # This should only trigger if something fails in setup or above
    # e.g. if v5_provDag fails to initialize
    def test_smoke(self):
        self.assertTrue(True)

    def test_root_uuid_correct(self):
        self.assertEqual(self.v5_provDag.root_uuid,
                         "ffb7cee3-2f1f-4988-90cc-efd5184ef003")

    def test_root_node_is_archive_root(self):
        mock_dag = MagicMock()
        self.root_metadata_fps = None
        with zipfile.ZipFile(self.v5_qzv) as zf:
            all_filenames = zf.namelist()
            self.root_md_fnames = filter(is_provnode_data, all_filenames)
            self.root_md_fps = [pathlib.Path(fp) for fp in self.root_md_fnames]
            self.v5_ProvNode = ProvNode(mock_dag, zf,
                                        self.root_md_fps)
        self.assertEqual(self.v5_ProvNode, self.v5_provDag.root_node)

    def test_str(self):
        self.assertRegex(str(self.v5_provDag),
                         "(?s)UUID:\t\tffb7cee3.*Type.*Data Format")

    def test_repr(self):
        self.assertRegex(
            repr(self.v5_provDag),
            "(?s)UUID:\t\tffb7cee3.*Type.*Data Format.*Contains")

    def test_repr_contains(self):
        self.assertRegex(repr(self.v5_provDag),
                         ("ffb7cee3-2f1f-4988-90cc-efd5184ef003:\n"
                          "  89af91c0-033d-4e30-8ac4-f29a3b407dc1:\n"
                          "    99fa3670-aa1a-45f6-ba8e-803c976a1163:\n"
                          "      a35830e1-4535-47c6-aa23-be295a57ee1c: null\n"
                          "  bce3d09b-e296-4f2b-9af4-834db6412429:\n"
                          "    7ecf8954-e49a-4605-992e-99fcee397935:\n"
                          "      99fa3670-aa1a-45f6-ba8e-803c976a1163:\n"
                          "        a35830e1-4535-47c6-aa23-be295a57ee1c: null"
                          "\n")
                         )

    def test_number_of_actions(self):
        self.assertEqual(self.v5_provDag._num_results, 15)

    def test_archive_type(self):
        self.assertEqual(self.v5_provDag.archive_type, 'Visualization')

    def test_archive_format(self):
        self.assertEqual(self.v5_provDag.archive_format, None)

    def test_nonexistent_fp(self):
        with self.assertRaisesRegex(FileNotFoundError, "not_a_filepath.qza"):
            ProvDAG(self.fake_fp)

    def test_not_a_zip_archive(self):
        with self.assertRaisesRegex(zipfile.BadZipFile,
                                    "File is not a zip file"):
            ProvDAG(self.not_a_zip)

    def test_archive_version_correct(self):
        self.assertEqual(self.v5_provDag.archive_version, '5')

    def test_framework_version_correct(self):
        self.assertEqual(self.v5_provDag.framework_version, '2018.11.0')


class UnionedDAGTests(unittest.TestCase):
    v5_qzv = os.path.join(DATA_DIR, 'v5_uu_emperor.qzv')
    v5_dag = ProvDAG(v5_qzv)
    dag_list = [v5_dag]

    def test_union_one_dag(self):
        dag = UnionedDAG(self.dag_list)
        self.assertEqual(dag.root_uuids,
                         ["ffb7cee3-2f1f-4988-90cc-efd5184ef003"])
        self.assertEqual(dag.root_nodes, [self.v5_dag.root_node])


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
    # TODO: 0 should have a real v0 archive. Currently a hacked V1 arhive
    cfg = {
        '0': {'uuid': '0b8b47bd-f2f8-4029-923c-0e37a68340c3',
              'parser': ParserV0,
              'num_res': None
              },
        '1': {'uuid': '0b8b47bd-f2f8-4029-923c-0e37a68340c3',
              'parser': ParserV1,
              'num_res': 10,
              },
        '2a': {'uuid': '219c4bdf-f2b1-4b3f-b66a-08de8a4d17ca',
               'parser': ParserV2,
               'num_res': 10,
               },
        '2b': {'uuid': '8abf8dee-0047-4a7f-9826-e66893182978',
               'parser': ParserV2,
               'num_res': 14,
               },
        '3': {'uuid': '3544061c-6e2f-4328-8345-754416828cb5',
              'parser': ParserV3,
              'num_res': 14,
              },
        '4': {'uuid': '91c2189a-2d2e-4d53-98ee-659caaf6ffc2',
              'parser': ParserV4,
              'num_res': 14,
              },
        '5': {'uuid': 'ffb7cee3-2f1f-4988-90cc-efd5184ef003',
              'parser': ParserV5,
              'num_res': 15,
              },
        }

    def test_get_root_md(self):
        for archv_vrsn in self.cfg.keys():
            qzv = os.path.join(DATA_DIR, 'v' + archv_vrsn + '_uu_emperor.qzv')
            root_uuid = self.cfg[archv_vrsn]['uuid']
            with zipfile.ZipFile(qzv) as zf:
                root_md = self.cfg[archv_vrsn]['parser'].get_root_md(zf)
                self.assertEqual(root_md.uuid, root_uuid)
                self.assertEqual(root_md.type,  'Visualization')
                self.assertEqual(root_md.format, None)

    def test_get_root_md_no_md_yaml(self):
        v5_qzv_no_root_md = os.path.join(DATA_DIR, 'no_root_md_yaml.qzv')
        for archv_vrsn in self.cfg.keys():
            with zipfile.ZipFile(v5_qzv_no_root_md) as zf:
                with self.assertRaisesRegex(ValueError, "Malformed.*metadata"):
                    self.cfg[archv_vrsn]['parser'].get_root_md(zf)

    def test_populate_archive(self):
        mock_DAG = MagicMock()
        for archv_vrsn in self.cfg.keys():
            qzv = os.path.join(DATA_DIR, 'v' + archv_vrsn + '_uu_emperor.qzv')
            root_uuid = self.cfg[archv_vrsn]['uuid']
            with zipfile.ZipFile(qzv) as zf:
                if archv_vrsn == '0':
                    with self.assertRaisesRegex(NotImplementedError,
                                                "V0.*no.*provenance"):
                        self.cfg[archv_vrsn]['parser'] \
                            .populate_archv(zf, mock_DAG)
                else:
                    num_res, contents = self.cfg[archv_vrsn]['parser'] \
                                            .populate_archv(zf, mock_DAG)
                    print(f"Debug: archive version #{archv_vrsn} failing")
                    # Does this archive have the right number of Results?
                    self.assertEqual(num_res, self.cfg[archv_vrsn]['num_res'])
                    # Is contents a dict?
                    self.assertIs(type(contents), dict)
                    # Is contents keyed on uuids, containing ProvNodes?
                    self.assertIs(type(contents[root_uuid]), ProvNode)
                    # Is the root UUID a key in the contents dict?
                    self.assertIn(root_uuid, contents)

    def test_get_nonroot_uuid(self):
        md_example = pathlib.Path(
            'arch_root/provenance/artifacts/uuid123/metadata.yaml')
        action_example = pathlib.Path(
            'arch_root/provenance/artifacts/uuid123/action/action.yaml')
        exp = 'uuid123'

        with self.assertRaisesRegex(NotImplementedError, "V0"):
            self.cfg['0']['parser']._get_nonroot_uuid(md_example)

        # Only parsers from v1 forward have this method
        parsers = [vrsn['parser'] for vrsn in list(self.cfg.values())[1:]]

        for parser in parsers:
            self.assertEqual(parser._get_nonroot_uuid(md_example), exp)
            self.assertEqual(parser._get_nonroot_uuid(action_example), exp)


class FormatHandlerTests(unittest.TestCase):
    v5_qzv = os.path.join(DATA_DIR, 'v5_uu_emperor.qzv')
    v5_no_version = os.path.join(DATA_DIR, 'VERSION_missing.qzv')
    v5_qzv_version_bad = os.path.join(DATA_DIR, 'VERSION_bad.qzv')
    v5_qzv_version_short = os.path.join(DATA_DIR, 'VERSION_short.qzv')
    v5_qzv_version_long = os.path.join(DATA_DIR, 'VERSION_long.qzv')

    cfg = {
        '0': {'parser': ParserV0,
              'av': '0',
              'fwv': '2.0.5',
              },
        '1': {'parser': ParserV1,
              'av': '1',
              'fwv': '2.0.6',
              },
        '2a': {'parser': ParserV2,
               'av': '2',
               'fwv': '2017.9.0',
               },
        '2b': {'parser': ParserV2,
               'av': '2',
               'fwv': '2017.10.0',
               },
        '3': {'parser': ParserV3,
              'av': '3',
              'fwv': '2017.12.0',
              },
        '4': {'parser': ParserV4,
              'av': '4',
              'fwv': '2018.4.0',
              },
        '5': {'parser': ParserV5,
              'av': '5',
              'fwv': '2018.11.0',
              },
        }

    # Can we make a FormatHandler without anything blowing up?
    def test_smoke(self):
        for arch_ver in self.cfg.keys():
            qzv = os.path.join(DATA_DIR, 'v' + arch_ver + '_uu_emperor.qzv')
            with zipfile.ZipFile(qzv) as zf:
                FormatHandler(zf)
        self.assertTrue(True)

    def test_archive_version(self):
        for arch_ver in self.cfg.keys():
            qzv = os.path.join(DATA_DIR, 'v' + arch_ver + '_uu_emperor.qzv')
            with zipfile.ZipFile(qzv) as zf:
                handler = FormatHandler(zf)
                self.assertEqual(handler.archive_version,
                                 self.cfg[arch_ver]['av'])

    def test_framework_version(self):
        for arch_ver in self.cfg.keys():
            qzv = os.path.join(DATA_DIR, 'v' + arch_ver + '_uu_emperor.qzv')
            with zipfile.ZipFile(qzv) as zf:
                handler = FormatHandler(zf)
                print(arch_ver)
                print(handler.archive_version)
                print(handler.framework_version)
                print(self.cfg[arch_ver]['fwv'])
                self.assertEqual(handler.framework_version,
                                 self.cfg[arch_ver]['fwv'])

    def test_correct_parser(self):
        for arch_ver in self.cfg.keys():
            qzv = os.path.join(DATA_DIR, 'v' + arch_ver + '_uu_emperor.qzv')
            with zipfile.ZipFile(qzv) as zf:
                handler = FormatHandler(zf)
                self.assertEqual(handler.parser,
                                 self.cfg[arch_ver]['parser'])

    def test_parse(self):
        uuid = 'ffb7cee3-2f1f-4988-90cc-efd5184ef003'
        with zipfile.ZipFile(self.v5_qzv) as zf:
            handler = FormatHandler(zf)
            mock_DAG = MagicMock()
            md, (num_r, contents) = handler.parse(zf, mock_DAG)
            self.assertIs(type(md), _ResultMetadata)
            self.assertEqual(md.uuid, uuid)
            self.assertEqual(md.type, 'Visualization')
            self.assertEqual(md.format, None)
            self.assertIs(type(num_r), int)
            self.assertEqual(num_r, 15)
            self.assertIn(uuid, contents.keys())
            self.assertIs(type(contents[uuid]), ProvNode)

    # Testing _get_version's behavior with major VERSION file issues is easier
    # and more reliable with "real" zip archives. Detailed tests of the VERSION
    # regex are in test_archive_formats.VersionMatcherTests to reduce overhead
    def test_get_version_no_VERSION_file(self):
        with zipfile.ZipFile(self.v5_no_version) as zf:
            with self.assertRaisesRegex(ValueError, "VERSION.*nonexistent"):
                FormatHandler(zf)

    def test_get_version_VERSION_bad(self):
        with zipfile.ZipFile(self.v5_qzv_version_bad) as zf:
            with self.assertRaisesRegex(ValueError, "VERSION.*out of spec"):
                FormatHandler(zf)

    def test_short_VERSION(self):
        with zipfile.ZipFile(self.v5_qzv_version_short) as zf:
            with self.assertRaisesRegex(ValueError, "VERSION.*out of spec"):
                FormatHandler(zf)

    def test_long_VERSION(self):
        with zipfile.ZipFile(self.v5_qzv_version_long) as zf:
            with self.assertRaisesRegex(ValueError, "VERSION.*out of spec"):
                FormatHandler(zf)


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
    # As implemented, ProvNodes must belong to a ProvDAG. Commit
    # 1281878510acdc42cb5ba3ee40c9ad8b62dacf0e shows another approach with
    # ProvDAGs responsible for assigning parentage to their ProvNodes

    def setUp(self):
        self.v5_qzv = os.path.join(DATA_DIR, 'v5_uu_emperor.qzv')
        # Building a dag to back thesee tests, because the alternative is to
        # hand-build two to three test nodes and mock a ProvDAG to hold them.
        self.v5_dag = ProvDAG(self.v5_qzv)
        self.v5_uuid = 'ffb7cee3-2f1f-4988-90cc-efd5184ef003'
        super().setUp()
        self.root_metadata_fps = None

        with zipfile.ZipFile(self.v5_qzv) as zf:
            all_filenames = zf.namelist()
            self.root_md_fnames = filter(is_provnode_data, all_filenames)
            self.root_md_fps = [pathlib.Path(fp) for fp in self.root_md_fnames]
            self.v5_ProvNode = ProvNode(self.v5_dag, zf, self.root_md_fps)

    def test_smoke(self):
        self.assertTrue(True)
        self.assertIs(type(self.v5_ProvNode), ProvNode)

    def test_v5_viz_md(self):
        print(self.v5_ProvNode)
        self.assertEqual(self.v5_ProvNode.uuid, self.v5_uuid)
        self.assertEqual(self.v5_ProvNode.sem_type, 'Visualization')
        self.assertEqual(self.v5_ProvNode.format, None)

    def test_eq(self):
        self.assertEqual(self.v5_ProvNode, self.v5_ProvNode)
        mock_node = MagicMock()
        # Mock has no matching UUID
        self.assertNotEqual(self.v5_ProvNode, mock_node)
        mock_node.uuid = 'gerbil'

        # Mock has bad UUID
        self.assertNotEqual(self.v5_ProvNode, mock_node)
        mock_node.uuid = self.v5_uuid

        # Matching UUIDs insufficient if classes differ
        self.assertNotEqual(self.v5_ProvNode, mock_node)
        mock_node.__class__ = ProvNode
        self.assertEqual(self.v5_ProvNode, mock_node)

    def test_is_hashable(self):
        exp_hash = hash(self.v5_uuid)
        self.assertEqual(hash(self.v5_ProvNode), exp_hash)

    def test_str(self):
        self.assertEqual(str(self.v5_ProvNode), f"ProvNode({self.v5_uuid})")

    def test_repr(self):
        self.assertEqual(repr(self.v5_ProvNode),
                         "ProvNode(ffb7cee3-2f1f-4988-90cc-efd5184ef003, "
                         "Visualization, fmt=None)")

    def test_archive_version(self):
        self.assertEqual(self.v5_ProvNode.archive_version, '5')

    def test_framework_version(self):
        self.assertEqual(self.v5_ProvNode.framework_version, '2018.11.0')

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

    def test_parents_property_has_no_parents(self):
        # qiime tools import node has no parents
        parentless_node_id = 'a35830e1-4535-47c6-aa23-be295a57ee1c'
        archive = self.v5_dag
        repr(archive)
        parentless_node = archive.get_result(parentless_node_id)
        # _parents not initialized before call
        self.assertEqual(parentless_node._parents, None)
        # ProvNode.parents should get parents - here that's None
        self.assertEqual(parentless_node.parents, None)
        # _parents initialized now
        self.assertEqual(parentless_node._parents, None)

    def test_parents_property_has_parents(self):
        self.v5_ProvNode._owner_dag = ProvDAG(self.v5_qzv)
        exp_nodes = [self.v5_ProvNode._owner_dag._archv_contents[id]
                     for id in ['89af91c0-033d-4e30-8ac4-f29a3b407dc1',
                                'bce3d09b-e296-4f2b-9af4-834db6412429']]
        # _parents not initialized before call
        self.assertEqual(self.v5_ProvNode._parents, None)
        # ProvNode.parents should get parents
        self.assertEqual(self.v5_ProvNode.parents, exp_nodes)
        # _parents initialized now
        self.assertEqual(self.v5_ProvNode._parents, exp_nodes)
