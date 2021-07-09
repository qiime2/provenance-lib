import os
import codecs
import pathlib
import unittest
from datetime import timedelta
from unittest.mock import MagicMock

from networkx import DiGraph
import zipfile

from ..parse import (
    _VERSION_MATCHER, ProvDAG, ProvNode, FormatHandler,
    _Action, _Citations, _ResultMetadata,
    ParserV0, ParserV1, ParserV2, ParserV3, ParserV4, ParserV5,
    get_version,
)
from .util import is_root_provnode_data

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
test_data = {
    '0': {'parser': ParserV0,
          'av': '0',
          'fwv': '2.0.5',
          'uuid': '0b8b47bd-f2f8-4029-923c-0e37a68340c3',
          'n_res': None,
          'qzv_fp': os.path.join(DATA_DIR, 'v0_uu_emperor.qzv'),
          },
    '1': {'parser': ParserV1,
          'av': '1',
          'fwv': '2.0.6',
          'uuid': '0b8b47bd-f2f8-4029-923c-0e37a68340c3',
          'n_res': 10,
          'qzv_fp': os.path.join(DATA_DIR, 'v1_uu_emperor.qzv'),
          },
    '2a': {'parser': ParserV2,
           'av': '2',
           'fwv': '2017.9.0',
           'uuid': '219c4bdf-f2b1-4b3f-b66a-08de8a4d17ca',
           'n_res': 10,
           'qzv_fp': os.path.join(DATA_DIR, 'v2a_uu_emperor.qzv'),
           },
    '2b': {'parser': ParserV2,
           'av': '2',
           'fwv': '2017.10.0',
           'uuid': '8abf8dee-0047-4a7f-9826-e66893182978',
           'n_res': 14,
           'qzv_fp': os.path.join(DATA_DIR, 'v2b_uu_emperor.qzv'),
           },
    '3': {'parser': ParserV3,
          'av': '3',
          'fwv': '2017.12.0',
          'uuid': '3544061c-6e2f-4328-8345-754416828cb5',
          'n_res': 14,
          'qzv_fp': os.path.join(DATA_DIR, 'v3_uu_emperor.qzv'),
          },
    '4': {'parser': ParserV4,
          'av': '4',
          'fwv': '2018.4.0',
          'uuid': '91c2189a-2d2e-4d53-98ee-659caaf6ffc2',
          'n_res': 14,
          'qzv_fp': os.path.join(DATA_DIR, 'v4_uu_emperor.qzv'),
          },
    '5': {'parser': ParserV5,
          'av': '5',
          'fwv': '2018.11.0',
          'uuid': 'ffb7cee3-2f1f-4988-90cc-efd5184ef003',
          'n_res': 15,
          'qzv_fp': os.path.join(DATA_DIR, 'v5_uu_emperor.qzv'),
          },
    }


class ProvDAGTests(unittest.TestCase):
    # Remove the character limit when reporting failing tests for this class
    maxDiff = None
    fake_fp = os.path.join(DATA_DIR, 'not_a_filepath.qza')
    not_a_zip = os.path.join(DATA_DIR, 'not_a_zip.txt')
    v5_provDag = ProvDAG(test_data['5']['qzv_fp'])

    # This should only trigger if something fails in setup or above
    # e.g. if v5_provDag fails to initialize
    def test_smoke(self):
        self.assertTrue(True)

    def test_root_uuid_correct(self):
        self.assertEqual(self.v5_provDag.root_uuid, test_data['5']['uuid'])

    def test_root_node_is_archive_root(self):
        with zipfile.ZipFile(test_data['5']['qzv_fp']) as zf:
            all_filenames = zf.namelist()
            root_md_fnames = filter(is_root_provnode_data, all_filenames)
            root_md_fps = [pathlib.Path(fp) for fp in root_md_fnames]
            v5_ProvNode = ProvNode(zf, root_md_fps)
            self.assertEqual(v5_ProvNode, self.v5_provDag.root_node)

    def test_number_of_actions(self):
        # TODO: remove _num_results and rely on node.len()?
        # This call should be made once we've decided how to represent nodes,
        # e.g. nested or all-nodes/raw
        # At that time, remove one of these assertions
        self.assertEqual(self.v5_provDag._num_results, test_data['5']['n_res'])
        self.assertEqual(len(self.v5_provDag), test_data['5']['n_res'])

    def test_nonexistent_fp(self):
        with self.assertRaisesRegex(FileNotFoundError, 'not_a_filepath.qza'):
            ProvDAG(self.fake_fp)

    def test_not_a_zip_archive(self):
        with self.assertRaisesRegex(zipfile.BadZipFile,
                                    'File is not a zip file'):
            ProvDAG(self.not_a_zip)

    def test_is_digraph(self):
        self.assertIsInstance(self.v5_provDag, DiGraph)

    def test_has_nodes(self):
        self.assertIn(test_data['5']['uuid'], self.v5_provDag.nodes)

    def test_root_node_attributes(self):
        root_node = self.v5_provDag.nodes[test_data['5']['uuid']]
        self.assertEqual(root_node['type'], 'Visualization')
        self.assertEqual(root_node['format'], None)
        self.assertEqual(root_node['framework_version'], '2018.11.0')
        self.assertEqual(root_node['archive_version'], '5')
        self.assertEqual(root_node['action_type'], 'pipeline')
        self.assertEqual(root_node['plugin'], 'diversity')
        self.assertIn({'table': '89af91c0-033d-4e30-8ac4-f29a3b407dc1'},
                      root_node['parents'])
        self.assertIn({'phylogeny': 'bce3d09b-e296-4f2b-9af4-834db6412429'},
                      root_node['parents'])
        self.assertEqual(root_node['runtime'],
                         timedelta(seconds=5, microseconds=249201))

    def test_has_edges(self):
        self.assertTrue(self.v5_provDag.has_edge(
            '89af91c0-033d-4e30-8ac4-f29a3b407dc1',
            'ffb7cee3-2f1f-4988-90cc-efd5184ef003'))
        self.assertTrue(self.v5_provDag.has_edge(
            'bce3d09b-e296-4f2b-9af4-834db6412429',
            'ffb7cee3-2f1f-4988-90cc-efd5184ef003'))

    def test_edge_types(self):
        self.assertEqual('table',
                         self.v5_provDag
                         ['89af91c0-033d-4e30-8ac4-f29a3b407dc1']
                         ['ffb7cee3-2f1f-4988-90cc-efd5184ef003']
                         ['type'])
        self.assertEqual('phylogeny',
                         self.v5_provDag
                         ['bce3d09b-e296-4f2b-9af4-834db6412429']
                         ['ffb7cee3-2f1f-4988-90cc-efd5184ef003']
                         ['type'])

    def test_str(self):
        self.assertRegex(str(self.v5_provDag),
                         '(?s)UUID:\t\tffb7cee3.*Type.*Data Format')

    def test_repr(self):
        self.assertRegex(
            repr(self.v5_provDag),
            '(?s)UUID:\t\tffb7cee3.*Type.*Data Format.*Contains')

    # TODO: This should probably be reduced to a minimum example
    def test_traverse_uuids(self):
        exp = {'ffb7cee3-2f1f-4988-90cc-efd5184ef003':
               {'89af91c0-033d-4e30-8ac4-f29a3b407dc1':
                {'99fa3670-aa1a-45f6-ba8e-803c976a1163':
                 {'a35830e1-4535-47c6-aa23-be295a57ee1c': None}},
                'bce3d09b-e296-4f2b-9af4-834db6412429':
                {'7ecf8954-e49a-4605-992e-99fcee397935':
                 {'99fa3670-aa1a-45f6-ba8e-803c976a1163':
                  {'a35830e1-4535-47c6-aa23-be295a57ee1c': None}}}}}
        actual = self.v5_provDag.traverse_uuids()
        self.assertEqual(actual, exp)

    def test_repr_contains(self):
        self.assertRegex(repr(self.v5_provDag),
                         ('ffb7cee3-2f1f-4988-90cc-efd5184ef003:\n'
                          '  89af91c0-033d-4e30-8ac4-f29a3b407dc1:\n'
                          '    99fa3670-aa1a-45f6-ba8e-803c976a1163:\n'
                          '      a35830e1-4535-47c6-aa23-be295a57ee1c: null\n'
                          '  bce3d09b-e296-4f2b-9af4-834db6412429:\n'
                          '    7ecf8954-e49a-4605-992e-99fcee397935:\n'
                          '      99fa3670-aa1a-45f6-ba8e-803c976a1163:\n'
                          '        a35830e1-4535-47c6-aa23-be295a57ee1c: null'
                          '\n')
                         )


class ArchiveVersionMatcherTests(unittest.TestCase):
    """Testing for the _VERSION_MATCHER regex in parse.py"""

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


class ParserVxTests(unittest.TestCase):
    # TODO: 0 should have a real v0 archive. Currently a hacked V1 archive

    def test_get_root_md(self):
        for archv_vrsn in test_data.keys():
            fp = test_data[archv_vrsn]['qzv_fp']
            root_uuid = test_data[archv_vrsn]['uuid']
            with zipfile.ZipFile(fp) as zf:
                root_md = test_data[archv_vrsn]['parser'].get_root_md(zf)
                self.assertEqual(root_md.uuid, root_uuid)
                self.assertEqual(root_md.type,  'Visualization')
                self.assertEqual(root_md.format, None)

    def test_get_root_md_no_md_yaml(self):
        v5_qzv_no_root_md = os.path.join(DATA_DIR, 'no_root_md_yaml.qzv')
        for archv_vrsn in test_data.keys():
            with zipfile.ZipFile(v5_qzv_no_root_md) as zf:
                with self.assertRaisesRegex(ValueError, 'Malformed.*metadata'):
                    test_data[archv_vrsn]['parser'].get_root_md(zf)

    def test_populate_archive(self):
        for archv_vrsn in test_data.keys():
            fp = test_data[archv_vrsn]['qzv_fp']
            root_uuid = test_data[archv_vrsn]['uuid']
            with zipfile.ZipFile(fp) as zf:
                if archv_vrsn == '0':
                    with self.assertRaisesRegex(NotImplementedError,
                                                'V0.*no.*provenance'):
                        test_data[archv_vrsn]['parser'].parse_prov(zf)
                else:
                    num_res, contents = test_data[archv_vrsn]['parser'] \
                                            .parse_prov(zf)
                    print(f'Debug: archive version #{archv_vrsn} failing')
                    # Does this archive have the right number of Results?
                    self.assertEqual(num_res, test_data[archv_vrsn]['n_res'])
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

        # Only parsers from v1 forward have this method
        parsers = [vrsn['parser'] for vrsn in list(test_data.values())[1:]]

        for parser in parsers:
            self.assertEqual(parser._get_nonroot_uuid(md_example), exp)
            self.assertEqual(parser._get_nonroot_uuid(action_example), exp)


class FormatHandlerTests(unittest.TestCase):

    # Can we make a FormatHandler without anything blowing up?
    def test_smoke(self):
        for arch_ver in test_data.keys():
            qzv = test_data[arch_ver]['qzv_fp']
            with zipfile.ZipFile(qzv) as zf:
                FormatHandler(zf)
        self.assertTrue(True)

    def test_archive_version(self):
        for arch_ver in test_data.keys():
            qzv = test_data[arch_ver]['qzv_fp']
            with zipfile.ZipFile(qzv) as zf:
                handler = FormatHandler(zf)
                self.assertEqual(handler.archive_version,
                                 test_data[arch_ver]['av'])

    def test_framework_version(self):
        for arch_ver in test_data.keys():
            qzv = test_data[arch_ver]['qzv_fp']
            with zipfile.ZipFile(qzv) as zf:
                handler = FormatHandler(zf)
                self.assertEqual(handler.framework_version,
                                 test_data[arch_ver]['fwv'])

    def test_correct_parser(self):
        for arch_ver in test_data.keys():
            qzv = test_data[arch_ver]['qzv_fp']
            with zipfile.ZipFile(qzv) as zf:
                handler = FormatHandler(zf)
                self.assertEqual(handler.parser,
                                 test_data[arch_ver]['parser'])

    def test_parse(self):
        uuid = test_data['5']['uuid']
        with zipfile.ZipFile(test_data['5']['qzv_fp']) as zf:
            handler = FormatHandler(zf)
            md, (num_r, contents) = handler.parse(zf)
            self.assertIs(type(md), _ResultMetadata)
            self.assertEqual(md.uuid, uuid)
            self.assertEqual(md.type, 'Visualization')
            self.assertEqual(md.format, None)
            self.assertIs(type(num_r), int)
            self.assertEqual(num_r, 15)
            self.assertIn(uuid, contents.keys())
            self.assertIs(type(contents[uuid]), ProvNode)


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
        for arch_ver in test_data.keys():
            qzv = os.path.join(DATA_DIR, 'v' + arch_ver + '_uu_emperor.qzv')
            with zipfile.ZipFile(qzv) as zf:
                exp_arch, exp_frmwk = get_version(zf)
                self.assertEqual(exp_arch, test_data[arch_ver]['av'])
                self.assertEqual(exp_frmwk, test_data[arch_ver]['fwv'])


class ResultMetadataTests(unittest.TestCase):
    v5_qzv = test_data['5']['qzv_fp']
    v5_uuid = test_data['5']['uuid']
    md_fp = f'{v5_uuid}/provenance/metadata.yaml'
    with zipfile.ZipFile(v5_qzv) as zf:
        v5_root_md = _ResultMetadata(zf, md_fp)

    def test_smoke(self):
        self.assertEqual(self.v5_root_md.uuid, self.v5_uuid)
        self.assertEqual(self.v5_root_md.type, 'Visualization')
        self.assertEqual(self.v5_root_md.format, None)

    def test_repr(self):
        exp = (f'UUID:\t\t{self.v5_uuid}\n'
               'Type:\t\tVisualization\n'
               'Data Format:\tNone')
        self.assertEqual(repr(self.v5_root_md), exp)


class ActionTests(unittest.TestCase):
    root_action_fp = os.path.join(DATA_DIR, 'v5_emperor_root_action.zip')
    import_action_fp = os.path.join(DATA_DIR, 'v5_import_action.zip')
    artifact_as_md_fp = os.path.join(DATA_DIR, 'v5_artifact_as_md_action.zip')
    with zipfile.ZipFile(root_action_fp) as zf:
        act = _Action(zf, 'action.yaml')

    with zipfile.ZipFile(import_action_fp) as zf:
        imp_act = _Action(zf, 'action.yaml')

    with zipfile.ZipFile(artifact_as_md_fp) as zf:
        art_as_md_act = _Action(zf, 'action.yaml')

    def test_action_id(self):
        exp = '5bc4b090-abbc-46b0-a219-346c8026f7d7'
        self.assertEqual(self.act.action_id, exp)

    def test_action_type(self):
        exp = 'pipeline'
        self.assertEqual(self.act.action_type, exp)

    def test_runtime(self):
        exp_t = timedelta
        exp = timedelta(seconds=2, microseconds=17110)
        self.assertIs(type(self.act.runtime), exp_t)
        self.assertEqual(self.act.runtime, exp)

    def test_runtime_str(self):
        exp = '2 seconds, and 17110 microseconds'
        self.assertEqual(self.act.runtime_str, exp)

    def test_action(self):
        exp = 'core_metrics_phylogenetic'
        self.assertEqual(self.act.action, exp)

    def test_plugin(self):
        exp = 'diversity'
        self.assertEqual(self.act.plugin, exp)

    def test_parents(self):
        exp = [{'table': '706b6bce-8f19-4ae9-b8f5-21b14a814a1b'},
               {'phylogeny': 'ad7e5b50-065c-4fdd-8d9b-991e92caad22'}]
        self.assertEqual(self.act.parents, exp)

    def test_parents_with_artifact_passed_as_md(self):
        exp = [{'tree': 'e710bdc5-e875-4876-b238-5451e3e8eb46'},
               {'feature_table': 'abc22fdc-e7fa-4976-a980-8f2ff8c4bb58'},
               {'pcoa': '1ed04b10-d29c-495f-996e-3d4db89434d2'},
               {'artifact_passed_as_metadata':
                '415409a4-371d-4c69-9433-e3eaba5301b4'},
               ]
        actual = self.art_as_md_act.parents
        # print(actual)
        self.assertEqual(actual, exp)

    def test_repr(self):
        exp = ('_Action(action_id=5bc4b090-abbc-46b0-a219-346c8026f7d7, '
               'type=pipeline, plugin=diversity, '
               'action=core_metrics_phylogenetic)')
        self.assertEqual(repr(self.act), exp)

    # NOTE: Import is not handled by a plugin, and has no inputs. Parsing logic
    # provides values for the following properties which are not present in
    # action.yaml
    def test_action_for_import_node(self):
        exp = 'import'
        self.assertEqual(self.imp_act.action, exp)

    def test_plugin_for_import_node(self):
        exp = 'framework'
        self.assertEqual(self.imp_act.plugin, exp)

    def test_parents_for_import_node(self):
        exp = []
        self.assertEqual(self.imp_act.parents, exp)


class CitationsTests(unittest.TestCase):
    cite_strs = ['cite_none', 'cite_one', 'cite_many']
    bibs = [bib+'.bib' for bib in cite_strs]
    zips = [os.path.join(DATA_DIR, bib+'.zip') for bib in cite_strs]

    def test_empty_bib(self):
        with zipfile.ZipFile(self.zips[0]) as zf:
            citations = _Citations(zf, self.bibs[0])
            # Is the _citations dict empty?
            self.assertFalse(len(citations.citations))

    def test_citation(self):
        with zipfile.ZipFile(self.zips[1]) as zf:
            exp = 'framework'
            citations = _Citations(zf, self.bibs[1])
            for key in citations.citations.keys():
                self.assertRegex(key, exp)

    def test_many_citations(self):
        exp = ['2020.6.0.dev0', 'unweighted_unifrac.+0',
               'unweighted_unifrac.+1', 'unweighted_unifrac.+2',
               'unweighted_unifrac.+3', 'unweighted_unifrac.+4',
               'BIOMV210DirFmt', 'BIOMV210Format']
        with zipfile.ZipFile(self.zips[2]) as zf:
            citations = _Citations(zf, self.bibs[2])
            for i, key in enumerate(citations.citations.keys()):
                print(key, exp[i])
                self.assertRegex(key, exp[i])

    def test_repr(self):
        exp = ("Citations(['framework|qiime2:2020.6.0.dev0|0'])")
        with zipfile.ZipFile(self.zips[1]) as zf:
            citations = _Citations(zf, self.bibs[1])
            self.assertEqual(repr(citations), exp)


class ProvNodeTests(unittest.TestCase):

    def setUp(self):
        # Using a dag to back these tests, because the alternative is to
        # hand-build two to three test nodes and mock a ProvDAG to hold them.
        self.v5_dag = ProvDAG(test_data['5']['qzv_fp'])
        super().setUp()
        self.root_metadata_fps = None

        with zipfile.ZipFile(test_data['5']['qzv_fp']) as zf:
            all_filenames = zf.namelist()
            root_md_fnames = filter(is_root_provnode_data, all_filenames)
            root_md_fps = [pathlib.Path(fp) for fp in root_md_fnames]
            self.v5_ProvNode = ProvNode(zf, root_md_fps)

    def test_smoke(self):
        self.assertTrue(True)
        self.assertIs(type(self.v5_ProvNode), ProvNode)

    def test_v5_viz_md(self):
        self.assertEqual(self.v5_ProvNode.uuid, test_data['5']['uuid'])
        self.assertEqual(self.v5_ProvNode.sem_type, 'Visualization')
        self.assertEqual(self.v5_ProvNode.format, None)

    def test_self_eq(self):
        self.assertEqual(self.v5_ProvNode, self.v5_ProvNode)

    def test_eq(self):
        # Mock has no matching UUID
        mock_node = MagicMock()
        self.assertNotEqual(self.v5_ProvNode, mock_node)

        # Mock has bad UUID
        mock_node.uuid = 'gerbil'
        self.assertNotEqual(self.v5_ProvNode, mock_node)

        # Matching UUIDs insufficient if classes differ
        mock_node.uuid = test_data['5']['uuid']
        self.assertNotEqual(self.v5_ProvNode, mock_node)
        mock_node.__class__ = ProvNode
        self.assertEqual(self.v5_ProvNode, mock_node)

    def test_is_hashable(self):
        exp_hash = hash(test_data['5']['uuid'])
        self.assertEqual(hash(self.v5_ProvNode), exp_hash)

    def test_str(self):
        v5_uuid = test_data['5']['uuid']
        self.assertEqual(str(self.v5_ProvNode), f'{v5_uuid}')

    def test_repr(self):
        v5_uuid = test_data['5']['uuid']
        self.assertEqual(repr(self.v5_ProvNode),
                         f'ProvNode({v5_uuid}, Visualization, fmt=None)')

    def test_archive_version(self):
        self.assertEqual(self.v5_ProvNode.archive_version,
                         test_data['5']['av'])

    def test_framework_version(self):
        self.assertEqual(self.v5_ProvNode.framework_version,
                         test_data['5']['fwv'])
