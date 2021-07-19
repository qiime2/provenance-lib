import os
import pathlib
import unittest
from datetime import timedelta
from unittest.mock import MagicMock
import warnings
import zipfile

from networkx import DiGraph
import yaml

from ..parse import (
    ProvDAG, ProvNode, FormatHandler,
    _Action, _Citations, _ResultMetadata,
    ParserV0, ParserV1, ParserV2, ParserV3, ParserV4, ParserV5,
)
from .util import is_root_provnode_data, ReallyEqualMixin

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
TEST_DATA = {
    '0': {'parser': ParserV0,
          'av': '0',
          'fwv': '2.0.5',
          'uuid': '0b8b47bd-f2f8-4029-923c-0e37a68340c3',
          'n_res': 1,
          'qzv_fp': os.path.join(DATA_DIR, 'v0_uu_emperor.qzv'),
          'has_prov': False,
          },
    '1': {'parser': ParserV1,
          'av': '1',
          'fwv': '2.0.6',
          'uuid': '0b8b47bd-f2f8-4029-923c-0e37a68340c3',
          'n_res': 10,
          'qzv_fp': os.path.join(DATA_DIR, 'v1_uu_emperor.qzv'),
          'has_prov': True,
          },
    '2a': {'parser': ParserV2,
           'av': '2',
           'fwv': '2017.9.0',
           'uuid': '219c4bdf-f2b1-4b3f-b66a-08de8a4d17ca',
           'n_res': 10,
           'qzv_fp': os.path.join(DATA_DIR, 'v2a_uu_emperor.qzv'),
           'has_prov': True,
           },
    '2b': {'parser': ParserV2,
           'av': '2',
           'fwv': '2017.10.0',
           'uuid': '8abf8dee-0047-4a7f-9826-e66893182978',
           'n_res': 14,
           'qzv_fp': os.path.join(DATA_DIR, 'v2b_uu_emperor.qzv'),
           'has_prov': True,
           },
    '3': {'parser': ParserV3,
          'av': '3',
          'fwv': '2017.12.0',
          'uuid': '3544061c-6e2f-4328-8345-754416828cb5',
          'n_res': 14,
          'qzv_fp': os.path.join(DATA_DIR, 'v3_uu_emperor.qzv'),
          'has_prov': True,
          },
    '4': {'parser': ParserV4,
          'av': '4',
          'fwv': '2018.4.0',
          'uuid': '91c2189a-2d2e-4d53-98ee-659caaf6ffc2',
          'n_res': 14,
          'qzv_fp': os.path.join(DATA_DIR, 'v4_uu_emperor.qzv'),
          'has_prov': True,
          },
    '5': {'parser': ParserV5,
          'av': '5',
          'fwv': '2018.11.0',
          'uuid': 'ffb7cee3-2f1f-4988-90cc-efd5184ef003',
          'n_res': 15,
          'qzv_fp': os.path.join(DATA_DIR, 'v5_uu_emperor.qzv'),
          'has_prov': True,
          },
    }


class YamlConstructorTests(unittest.TestCase):
    """
    YAML Constructors are used to handle the custom YAML tags defined by the
    framework.

    """
    def test_unknown_tag(self):
        """
        Makes explicit the current handling of unimplemented custom tags. In
        future, we may want to deal with these more graciously (e.g. warn), but
        for now we're going to fail fast
        """
        tag = r"!foo 'this is not an implemented tag'"
        with self.assertRaisesRegex(yaml.constructor.ConstructorError,
                                    'could not determine a constructor.*!foo'):
            yaml.safe_load(tag)

    def test_citation_key_constructor(self):
        tag = r"!cite 'framework|qiime2:2020.6.0.dev0|0'"
        actual = yaml.safe_load(tag)
        self.assertEqual(actual, 'framework|qiime2:2020.6.0.dev0|0')

    def test_color_primitive_constructor(self):
        tag = r"!color '#57f289'"
        actual = yaml.safe_load(tag)
        self.assertEqual(actual, '#57f289')

    def test_forward_ref_action_plugin_ref(self):
        tag = r"plugin: !ref 'environment:plugins:diversity'"
        actual = yaml.safe_load(tag)
        self.assertEqual(actual, {'plugin': 'diversity'})

    def test_forward_ref_generic_ref(self):
        tag = r"plugin: !ref 'environment:framework:version'"
        actual = yaml.safe_load(tag)
        exp = {'plugin': ['environment', 'framework', 'version']}
        self.assertEqual(exp, actual)

    def test_metadata_path_constructor(self):
        tag = r"!metadata 'metadata.tsv'"
        actual = yaml.safe_load(tag)
        self.assertEqual(actual, {'input_artifact_uuids': [],
                                  'relative_fp': 'metadata.tsv'})

    def test_metadata_path_constructor_one_Artifact_as_md(self):
        tag = r"!metadata '415409a4-stuff-e3eaba5301b4:feature_metadata.tsv'"
        actual = yaml.safe_load(tag)
        self.assertEqual(
            actual,
            {'input_artifact_uuids': ['415409a4-stuff-e3eaba5301b4'],
             'relative_fp': 'feature_metadata.tsv'}
             )

    def test_metadata_path_constructor_many_Artifacts_as_md(self):
        tag = (r"!metadata '415409a4-stuff-e3eaba5301b4,"
               r"12345-other-stuff-67890"
               r":feature_metadata.tsv'")
        actual = yaml.safe_load(tag)
        self.assertEqual(
            actual,
            {'input_artifact_uuids': ['415409a4-stuff-e3eaba5301b4',
                                      '12345-other-stuff-67890'],
             'relative_fp': 'feature_metadata.tsv'}
             )

    def test_no_provenance_constructor(self):
        tag = "!no-provenance '34b07e56-27a5-4f03-ae57-ff427b50aaa1'"
        # This context manager prevents the warning under test from
        # propagating to the test session's Warning Summary
        with self.assertWarnsRegex(UserWarning,
                                   'Artifact 34b07e.*prior to provenance'):
            actual = yaml.safe_load(tag)
            self.assertEqual(actual, '34b07e56-27a5-4f03-ae57-ff427b50aaa1')

    def test_no_provenance_multiple_warnings_fire(self):
        tag_list = """
        - !no-provenance '34b07e56-27a5-4f03-ae57-ff427b50aaa1'
        - !no-provenance 'gerbil'
        """
        with warnings.catch_warnings(record=True) as w:
            # Just in case something else has modified the filter state
            warnings.simplefilter("default")
            yaml.safe_load(tag_list)
            # There should be exactly two warnings
            self.assertEqual(len(w), 2)

            # The first should be a Userwarnign containing these strings
            self.assertEqual(UserWarning, w[0].category)
            self.assertIn('Artifact 34b07e', str(w[0].message))
            self.assertIn('prior to provenance', str(w[0].message))

            # And the second should look similar
            self.assertEqual(UserWarning, w[1].category)
            self.assertIn('gerbil', str(w[1].message))
            self.assertIn('prior to provenance', str(w[0].message))

    def test_set_ref(self):
        flow_tag = r"!set ['foo', 'bar', 'baz']"
        flow = yaml.safe_load(flow_tag)
        self.assertEqual(flow, {'foo', 'bar', 'baz'})

        # NOTE: we don't expect duplicate values here (because dumped values
        # were a set), but it doesn't hurt to test the behavior
        block_tag = '!set\n- spam\n- egg\n- spam\n'
        block = yaml.safe_load(block_tag)
        self.assertEqual(block, {'spam', 'egg'})


class ProvDAGTests(unittest.TestCase):
    # Remove the character limit when reporting failing tests for this class
    maxDiff = None
    fake_fp = os.path.join(DATA_DIR, 'not_a_filepath.qza')
    not_a_zip = os.path.join(DATA_DIR, 'not_a_zip.txt')
    v5_provDag = ProvDAG(TEST_DATA['5']['qzv_fp'])

    # This should only trigger if something fails in setup or above
    # e.g. if v5_provDag fails to initialize
    def test_smoke(self):
        self.assertTrue(True)

    def test_root_uuid_correct(self):
        self.assertEqual(self.v5_provDag.root_uuid, TEST_DATA['5']['uuid'])

    def test_root_node_is_archive_root(self):
        with zipfile.ZipFile(TEST_DATA['5']['qzv_fp']) as zf:
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
        self.assertEqual(self.v5_provDag._num_results, TEST_DATA['5']['n_res'])
        self.assertEqual(len(self.v5_provDag), TEST_DATA['5']['n_res'])

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
        self.assertIn(TEST_DATA['5']['uuid'], self.v5_provDag.nodes)

    def test_root_node_attributes(self):
        root_node = self.v5_provDag.nodes[TEST_DATA['5']['uuid']]
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


class ParserVxTests(unittest.TestCase):
    def test_get_root_md(self):
        for archv_vrsn in TEST_DATA:
            fp = TEST_DATA[archv_vrsn]['qzv_fp']
            root_uuid = TEST_DATA[archv_vrsn]['uuid']
            with zipfile.ZipFile(fp) as zf:
                root_md = TEST_DATA[archv_vrsn]['parser'].get_root_md(zf)
                self.assertEqual(root_md.uuid, root_uuid)
                self.assertEqual(root_md.type,  'Visualization')
                self.assertEqual(root_md.format, None)

    def test_get_root_md_no_md_yaml(self):
        v5_qzv_no_root_md = os.path.join(DATA_DIR, 'no_root_md_yaml.qzv')
        for archv_vrsn in TEST_DATA:
            with zipfile.ZipFile(v5_qzv_no_root_md) as zf:
                with self.assertRaisesRegex(ValueError, 'Malformed.*metadata'):
                    TEST_DATA[archv_vrsn]['parser'].get_root_md(zf)

    def test_populate_archive(self):
        for archv_vrsn in TEST_DATA:
            fp = TEST_DATA[archv_vrsn]['qzv_fp']
            root_uuid = TEST_DATA[archv_vrsn]['uuid']
            with zipfile.ZipFile(fp) as zf:
                if archv_vrsn == '0':
                    with self.assertWarnsRegex(
                        UserWarning,
                            'Artifact 0b8b47.*prior to provenance'):
                        num_res, contents = \
                            TEST_DATA[archv_vrsn]['parser'].parse_prov(zf)
                else:
                    num_res, contents = \
                        TEST_DATA[archv_vrsn]['parser'].parse_prov(zf)
                print(f'Debug: archive version #{archv_vrsn} failing')
                # Does this archive have the right number of Results?
                self.assertEqual(num_res, TEST_DATA[archv_vrsn]['n_res'])
                # Is contents a dict?
                self.assertIs(type(contents), dict)
                # Is the root UUID a key in the contents dict?
                self.assertIn(root_uuid, contents)
                # Is contents keyed on uuids, containing ProvNodes?
                self.assertIs(type(contents[root_uuid]), ProvNode)

    def test_get_nonroot_uuid(self):
        md_example = pathlib.Path(
            'arch_root/provenance/artifacts/uuid123/metadata.yaml')
        action_example = pathlib.Path(
            'arch_root/provenance/artifacts/uuid123/action/action.yaml')
        exp = 'uuid123'

        # Only parsers from v1 forward have this method
        parsers = [vrsn['parser'] for vrsn in list(TEST_DATA.values())[1:]]

        for parser in parsers:
            self.assertEqual(parser._get_nonroot_uuid(md_example), exp)
            self.assertEqual(parser._get_nonroot_uuid(action_example), exp)


class FormatHandlerTests(unittest.TestCase):

    # Can we make a FormatHandler without anything blowing up?
    def test_smoke(self):
        for arch_ver in TEST_DATA:
            qzv = TEST_DATA[arch_ver]['qzv_fp']
            with zipfile.ZipFile(qzv) as zf:
                FormatHandler(zf)
        self.assertTrue(True)

    def test_archive_version(self):
        for arch_ver in TEST_DATA:
            qzv = TEST_DATA[arch_ver]['qzv_fp']
            with zipfile.ZipFile(qzv) as zf:
                handler = FormatHandler(zf)
                self.assertEqual(handler.archive_version,
                                 TEST_DATA[arch_ver]['av'])

    def test_framework_version(self):
        for arch_ver in TEST_DATA:
            qzv = TEST_DATA[arch_ver]['qzv_fp']
            with zipfile.ZipFile(qzv) as zf:
                handler = FormatHandler(zf)
                self.assertEqual(handler.framework_version,
                                 TEST_DATA[arch_ver]['fwv'])

    def test_correct_parser(self):
        for arch_ver in TEST_DATA:
            qzv = TEST_DATA[arch_ver]['qzv_fp']
            with zipfile.ZipFile(qzv) as zf:
                handler = FormatHandler(zf)
                self.assertEqual(handler.parser,
                                 TEST_DATA[arch_ver]['parser'])

    def test_parse(self):
        uuid = TEST_DATA['5']['uuid']
        with zipfile.ZipFile(TEST_DATA['5']['qzv_fp']) as zf:
            handler = FormatHandler(zf)
            md, (num_r, contents) = handler.parse(zf)
            self.assertIs(type(md), _ResultMetadata)
            self.assertEqual(md.uuid, uuid)
            self.assertEqual(md.type, 'Visualization')
            self.assertEqual(md.format, None)
            self.assertIs(type(num_r), int)
            self.assertEqual(num_r, 15)
            self.assertIn(uuid, contents)
            self.assertIs(type(contents[uuid]), ProvNode)


class ResultMetadataTests(unittest.TestCase):
    v5_qzv = TEST_DATA['5']['qzv_fp']
    v5_uuid = TEST_DATA['5']['uuid']
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
    root_action_fp = os.path.join(DATA_DIR, 'action_emperor_root_node_v5.zip')
    import_action_fp = os.path.join(DATA_DIR, 'action_import_v5.zip')
    artifact_as_md_fp = os.path.join(DATA_DIR, 'action_artifact_as_md_v5.zip')
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
        self.assertEqual(actual, exp)

    def test_get_one_artifact_passed_as_md(self):
        get_artifacts = self.act._get_artifacts_passed_as_md
        action_details = \
            {'parameters':
                [
                 {'some_param': 'foo'},
                 {'arbitrary_metadata_name':
                  {'input_artifact_uuids': [],
                   'relative_fp': 'some_metadata.tsv'}},
                 {'other_metadata':
                  {'input_artifact_uuids': ['301b4'],
                   'relative_fp': 'other_metadata.tsv'}},
                 ]}
        actual = get_artifacts(action_details)
        exp = [
               {'artifact_passed_as_metadata': '301b4'},
               ]
        self.assertEqual(actual, exp)

    def test_get_two_artifacts_passed_as_md(self):
        get_artifacts = self.act._get_artifacts_passed_as_md
        action_details = \
            {'parameters':
                [
                 {'some_param': 'foo'},
                 {'arbitrary_metadata_name':
                  {'input_artifact_uuids': [],
                   'relative_fp': 'some_metadata.tsv'}},
                 {'other_metadata':
                  {'input_artifact_uuids': ['4154', '301b4'],
                   'relative_fp': 'other_metadata.tsv'}},
                 ]}
        actual = get_artifacts(action_details)
        exp = [{'artifact_passed_as_metadata': '4154'},
               {'artifact_passed_as_metadata': '301b4'},
               ]
        self.assertEqual(actual, exp)

    def test_get_zero_artifacts_passed_as_md(self):
        get_artifacts = self.act._get_artifacts_passed_as_md
        action_details = \
            {'parameters':
                [
                 {'some_param': 'foo'},
                 {'arbitrary_metadata_name':
                  {'input_artifact_uuids': [],
                   'relative_fp': 'some_metadata.tsv'}},
                 {'other_metadata':
                  {'input_artifact_uuids': [],
                   'relative_fp': 'other_metadata.tsv'}},
                 ]}
        actual = get_artifacts(action_details)
        exp = []
        self.assertEqual(actual, exp)

    def test_get_artifacts_passed_as_md_no_params(self):
        get_artifacts = self.act._get_artifacts_passed_as_md
        action_details = {'non-parameters-key': 'here is a thing'}
        actual = get_artifacts(action_details)
        exp = []
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
            for key in citations.citations:
                self.assertRegex(key, exp)

    def test_many_citations(self):
        exp = ['2020.6.0.dev0', 'unweighted_unifrac.+0',
               'unweighted_unifrac.+1', 'unweighted_unifrac.+2',
               'unweighted_unifrac.+3', 'unweighted_unifrac.+4',
               'BIOMV210DirFmt', 'BIOMV210Format']
        with zipfile.ZipFile(self.zips[2]) as zf:
            citations = _Citations(zf, self.bibs[2])
            for i, key in enumerate(citations.citations):
                self.assertRegex(key, exp[i])

    def test_repr(self):
        exp = ("Citations(['framework|qiime2:2020.6.0.dev0|0'])")
        with zipfile.ZipFile(self.zips[1]) as zf:
            citations = _Citations(zf, self.bibs[1])
            self.assertEqual(repr(citations), exp)


class ProvNodeTests(unittest.TestCase, ReallyEqualMixin):
    # TODO: If possible, we should load ProvDAGs for v0-v5 and make them
    # globally available to these test classes. This should allow us to
    # reduce test time and run more tests iteratively.
    # This class and ProvDAGTests, at least, would benefit

    def setUp(self):
        # Using a dag to back these tests, because the alternative is to
        # hand-build two to three test nodes and mock a ProvDAG to hold them.
        self.v5_dag = ProvDAG(TEST_DATA['5']['qzv_fp'])
        super().setUp()
        self.root_metadata_fps = None

        with zipfile.ZipFile(TEST_DATA['0']['qzv_fp']) as zf:
            root_md_fnames = [pathlib.Path(TEST_DATA['0']['uuid']) / fp for
                              fp in ('metadata.yaml', 'VERSION')]
            root_md_fps = [pathlib.Path(fp) for fp in root_md_fnames]
            self.v0_ProvNode = ProvNode(zf, root_md_fps)

        with zipfile.ZipFile(TEST_DATA['5']['qzv_fp']) as zf:
            all_filenames = zf.namelist()
            root_md_fnames = filter(is_root_provnode_data, all_filenames)
            root_md_fps = [pathlib.Path(fp) for fp in root_md_fnames]
            self.v5_ProvNode = ProvNode(zf, root_md_fps)

    def test_smoke(self):
        self.assertTrue(True)
        self.assertIs(type(self.v5_ProvNode), ProvNode)

    def test_viz_properties(self):
        # TODO: expand to other versions once we're globally loading ProvDAGs
        nodes = {'0': self.v0_ProvNode,
                 '5': self.v5_ProvNode,
                 }
        for node in nodes:
            self.assertEqual(nodes[node].uuid, TEST_DATA[node]['uuid'])
            self.assertEqual(nodes[node].sem_type, 'Visualization')
            self.assertEqual(nodes[node].format, None)
            self.assertEqual(nodes[node].archive_version,
                             TEST_DATA[node]['av'])
            self.assertEqual(nodes[node].framework_version,
                             TEST_DATA[node]['fwv'])
            self.assertEqual(nodes[node].has_provenance,
                             TEST_DATA[node]['has_prov'])

    def test_self_eq(self):
        self.assertReallyEqual(self.v5_ProvNode, self.v5_ProvNode)

    def test_eq(self):
        # Mock has no matching UUID
        mock_node = MagicMock()
        self.assertNotEqual(self.v5_ProvNode, mock_node)

        # Mock has bad UUID
        mock_node.uuid = 'gerbil'
        self.assertReallyNotEqual(self.v5_ProvNode, mock_node)

        # Matching UUIDs insufficient if classes differ
        mock_node.uuid = TEST_DATA['5']['uuid']
        self.assertReallyNotEqual(self.v5_ProvNode, mock_node)
        mock_node.__class__ = ProvNode
        self.assertReallyEqual(self.v5_ProvNode, mock_node)

    def test_is_hashable(self):
        exp_hash = hash(TEST_DATA['5']['uuid'])
        self.assertReallyEqual(hash(self.v5_ProvNode), exp_hash)

    def test_str(self):
        v5_uuid = TEST_DATA['5']['uuid']
        self.assertEqual(str(self.v5_ProvNode), f'{v5_uuid}')

    def test_repr(self):
        v5_uuid = TEST_DATA['5']['uuid']
        self.assertEqual(repr(self.v5_ProvNode),
                         f'ProvNode({v5_uuid}, Visualization, fmt=None)')

    def test_archive_version(self):
        self.assertEqual(self.v5_ProvNode.archive_version,
                         TEST_DATA['5']['av'])

    def test_framework_version(self):
        self.assertEqual(self.v5_ProvNode.framework_version,
                         TEST_DATA['5']['fwv'])
