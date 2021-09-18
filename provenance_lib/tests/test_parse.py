import os
import pandas as pd
import pathlib
import unittest
from datetime import timedelta
from unittest.mock import MagicMock
import warnings
import zipfile

from networkx import DiGraph

from ..checksum_validator import ChecksumDiff, ValidationCodes
from ..parse import (
    ProvDAG, ProvNode, FormatHandler,
    _Action, _Citations, _ResultMetadata,
    ParserV0, ParserV1, ParserV2, ParserV3, ParserV4, ParserV5,
    ParserResults, Config,
)
from ..yaml_constructors import MetadataInfo

from .util import (
    is_root_provnode_data, generate_archive_with_file_removed,
    ReallyEqualMixin,
)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
TEST_DATA = {
    '0': {'parser': ParserV0,
          'av': '0',
          'fwv': '2.0.5',
          'uuid': '0b8b47bd-f2f8-4029-923c-0e37a68340c3',
          'n_res': 1,
          'qzv_fp': os.path.join(DATA_DIR, 'v0_uu_emperor.qzv'),
          'has_prov': False,
          'prov_is_valid': ValidationCodes.PREDATES_CHECKSUMS,
          'checksum': None,
          },
    '1': {'parser': ParserV1,
          'av': '1',
          'fwv': '2.0.6',
          'uuid': '0b8b47bd-f2f8-4029-923c-0e37a68340c3',
          'nonroot_node': '60cde83c-180d-40cb-87c9-b9363f23f796',
          'n_res': 10,
          'qzv_fp': os.path.join(DATA_DIR, 'v1_uu_emperor.qzv'),
          'has_prov': True,
          'prov_is_valid': ValidationCodes.PREDATES_CHECKSUMS,
          'checksum': None,
          },
    '2a': {'parser': ParserV2,
           'av': '2',
           'fwv': '2017.9.0',
           'uuid': '219c4bdf-f2b1-4b3f-b66a-08de8a4d17ca',
           'nonroot_node': '512ced83-cc8b-4bed-8c22-a829e8fc89a2',
           'n_res': 10,
           'qzv_fp': os.path.join(DATA_DIR, 'v2a_uu_emperor.qzv'),
           'has_prov': True,
           'prov_is_valid': ValidationCodes.PREDATES_CHECKSUMS,
           'checksum': None,
           },
    '2b': {'parser': ParserV2,
           'av': '2',
           'fwv': '2017.10.0',
           'uuid': '8abf8dee-0047-4a7f-9826-e66893182978',
           'nonroot_node': '10ebb316-169e-422c-8fb9-423e131fe42f',
           'n_res': 14,
           'qzv_fp': os.path.join(DATA_DIR, 'v2b_uu_emperor.qzv'),
           'has_prov': True,
           'prov_is_valid': ValidationCodes.PREDATES_CHECKSUMS,
           'checksum': None,
           },
    '3': {'parser': ParserV3,
          'av': '3',
          'fwv': '2017.12.0',
          'uuid': '3544061c-6e2f-4328-8345-754416828cb5',
          'nonroot_node': '32c222f5-d991-4168-bca2-d305513e258f',
          'n_res': 14,
          'qzv_fp': os.path.join(DATA_DIR, 'v3_uu_emperor.qzv'),
          'has_prov': True,
          'prov_is_valid': ValidationCodes.PREDATES_CHECKSUMS,
          'checksum': None,
          },
    '4': {'parser': ParserV4,
          'av': '4',
          'fwv': '2018.4.0',
          'uuid': '91c2189a-2d2e-4d53-98ee-659caaf6ffc2',
          'nonroot_node': '48c153b4-314c-4249-88a3-020f5444a76f',
          'n_res': 14,
          'qzv_fp': os.path.join(DATA_DIR, 'v4_uu_emperor.qzv'),
          'has_prov': True,
          'prov_is_valid': ValidationCodes.PREDATES_CHECKSUMS,
          'checksum': None,
          },
    '5': {'parser': ParserV5,
          'av': '5',
          'fwv': '2018.11.0',
          'uuid': 'ffb7cee3-2f1f-4988-90cc-efd5184ef003',
          'nonroot_node': '3b7d36ff-37ab-4ac2-958b-6a547d442bcf',
          'n_res': 15,
          'qzv_fp': os.path.join(DATA_DIR, 'v5_uu_emperor.qzv'),
          'has_prov': True,
          'prov_is_valid': ValidationCodes.VALID,
          'checksum': ChecksumDiff({}, {}, {}),
          },
    }


class ProvDAGTests(unittest.TestCase):
    # Remove the character limit when reporting failing tests for this class
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.dags = dict()
        for archive_version in list(TEST_DATA):
            # supress warning from parsing provenance for a v0 provDag
            uuid = TEST_DATA['0']['uuid']
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore',  f'Art.*{uuid}.*prior')
                cls.dags[archive_version] = ProvDAG(
                    Config(), str(TEST_DATA[archive_version]['qzv_fp']))

    # This should only trigger if something fails in setup or above
    # e.g. if a ProvDag fails to initialize
    def test_smoke(self):
        self.assertTrue(True)

    def test_root_uuid_correct(self):
        for dag_version in self.dags:
            self.assertEqual(self.dags[dag_version].root_uuid,
                             TEST_DATA[dag_version]['uuid'])

    def test_root_node_is_archive_root(self):
        for dag_version in self.dags:
            with zipfile.ZipFile(TEST_DATA[dag_version]['qzv_fp']) as zf:
                all_filenames = zf.namelist()
                root_md_fnames = filter(is_root_provnode_data, all_filenames)
                root_md_fps = [pathlib.Path(fp) for fp in root_md_fnames]
                node = ProvNode(zf, root_md_fps)
                self.assertEqual(node, self.dags[dag_version].root_node)

    def test_number_of_actions(self):
        # TODO: remove _num_results and rely on node.len()?
        # This decision should be made once we've decided how to represent
        # nodes, e.g. nested or all-nodes/raw
        # At that time, remove one of these assertions
        for dag_version in self.dags:
            self.assertEqual(self.dags[dag_version].parser_results.num_results,
                             TEST_DATA[dag_version]['n_res'])
            self.assertEqual(len(self.dags[dag_version]),
                             TEST_DATA[dag_version]['n_res'])

    def test_nonexistent_fp(self):
        fake_fp = os.path.join(DATA_DIR, 'not_a_filepath.qza')
        with self.assertRaisesRegex(FileNotFoundError, 'not_a_filepath.qza'):
            ProvDAG(Config(), fake_fp)

    def test_not_a_zip_archive(self):
        not_a_zip = os.path.join(DATA_DIR, 'not_a_zip.txt')
        with self.assertRaisesRegex(zipfile.BadZipFile,
                                    'File is not a zip file'):
            ProvDAG(Config(), not_a_zip)

    def test_is_digraph(self):
        for dag_version in self.dags:
            self.assertIsInstance(self.dags[dag_version], DiGraph)

    def test_has_nodes(self):
        for dag_version in self.dags:
            self.assertIn(TEST_DATA[dag_version]['uuid'],
                          self.dags[dag_version].nodes)

    def test_dag_attributes(self):
        for vz in self.dags:
            self.assertEqual(type(self.dags[vz].parser_results), ParserResults)
            self.assertEqual(type(self.dags[vz].parser_results.root_md),
                             _ResultMetadata)
            self.assertEqual(self.dags[vz].parser_results.root_md.uuid,
                             TEST_DATA[vz]['uuid'])
            self.assertEqual(self.dags[vz].parser_results.num_results,
                             TEST_DATA[vz]['n_res'])
            self.assertIs(
                type(self.dags[vz].parser_results.archive_contents),
                dict)
            self.assertEqual(self.dags[vz].provenance_is_valid,
                             TEST_DATA[vz]['prov_is_valid'])
            self.assertEqual(self.dags[vz].checksum_diff,
                             TEST_DATA[vz]['checksum'])

    def test_v5root_node_attributes(self):
        # Many of these attributes are being tested across version formats in
        # the ProvNode tests. We're not going to worry about all the details
        root_node = self.dags['5'].nodes[TEST_DATA['5']['uuid']]
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
        self.assertIn('metadata', root_node['metadata'])
        self.assertEqual(type(root_node['metadata']['metadata']), pd.DataFrame)

    def test_V5_has_edges(self):
        self.assertTrue(self.dags['5'].has_edge(
            '89af91c0-033d-4e30-8ac4-f29a3b407dc1',
            'ffb7cee3-2f1f-4988-90cc-efd5184ef003'))
        self.assertTrue(self.dags['5'].has_edge(
            'bce3d09b-e296-4f2b-9af4-834db6412429',
            'ffb7cee3-2f1f-4988-90cc-efd5184ef003'))

    def test_v5_edge_types(self):
        self.assertEqual('table',
                         self.dags['5']
                         ['89af91c0-033d-4e30-8ac4-f29a3b407dc1']
                         ['ffb7cee3-2f1f-4988-90cc-efd5184ef003']
                         ['type'])
        self.assertEqual('phylogeny',
                         self.dags['5']
                         ['bce3d09b-e296-4f2b-9af4-834db6412429']
                         ['ffb7cee3-2f1f-4988-90cc-efd5184ef003']
                         ['type'])

    def test_str(self):
        for dag_vzn in self.dags:
            uuid = TEST_DATA[dag_vzn]['uuid']
            self.assertRegex(str(self.dags[dag_vzn]),
                             f'(?s)UUID:\t\t{uuid}.*Type.*Data Format')

    def test_repr(self):
        for dag_vzn in self.dags:
            uuid = TEST_DATA[dag_vzn]['uuid']
            self.assertRegex(
                repr(self.dags[dag_vzn]),
                f'(?s)UUID:\t\t{uuid}.*Type.*Data Format.*Contains')

    def test_v5_captures_full_history(self):
        nodes = self.dags['5'].nodes
        self.assertEqual(len(nodes), 15)
        node_list = ['ffb7cee3-2f1f-4988-90cc-efd5184ef003',
                     '0af08fa8-48b7-4c6a-83c6-e0f766156343',
                     '3b7d36ff-37ab-4ac2-958b-6a547d442bcf',
                     '7ecf8954-e49a-4605-992e-99fcee397935',
                     '9cc3281a-fefb-408e-8cf0-10637a06d84a',
                     '025e723d-b367-4812-820a-ae8bf8b80af4',
                     '83a80bfd-8954-4571-8fc7-ac9e8435156e',
                     '89af91c0-033d-4e30-8ac4-f29a3b407dc1',
                     '99fa3670-aa1a-45f6-ba8e-803c976a1163',
                     '430a6575-86b3-4cf6-b72e-0f7fce3ed342',
                     'a35830e1-4535-47c6-aa23-be295a57ee1c',
                     'aea3994b-0888-41c1-8e8c-69f6615d07cf',
                     'bce3d09b-e296-4f2b-9af4-834db6412429',
                     'd32a5ea6-1ca1-4635-b522-2253568ae35b',
                     'f20cecd6-9f82-4bde-a013-eb327612dc4d',
                     ]
        self.assertEqual(len(nodes), 15)
        self.assertEqual(set(nodes), set(node_list))

        # Terminal/alias node
        root_parents = [
            {'table': '89af91c0-033d-4e30-8ac4-f29a3b407dc1'},
            {'phylogeny': 'bce3d09b-e296-4f2b-9af4-834db6412429'}]
        self.assertEqual(nodes[node_list[0]]['parents'], root_parents)
        # non-alias node
        n1_parents = [{'table': '89af91c0-033d-4e30-8ac4-f29a3b407dc1'},
                      ]
        self.assertEqual(nodes[node_list[1]]['parents'], n1_parents)
        # some other nodes
        n2_parents = [{'tree': 'd32a5ea6-1ca1-4635-b522-2253568ae35b'},
                      ]
        self.assertEqual(nodes[node_list[2]]['parents'], n2_parents)
        n3_parents = [{'demultiplexed_seqs':
                       '99fa3670-aa1a-45f6-ba8e-803c976a1163'}]
        self.assertEqual(nodes[node_list[3]]['parents'], n3_parents)
        # import node
        n10_parents = []
        self.assertEqual(nodes[node_list[10]]['parents'], n10_parents)

        # TODO: What do these nodes have in common beyond traversal?
        # Is the traversal algo a useful view at all?
        # ['ffb7cee3-2f1f-4988-90cc-efd5184ef003',
        #  '89af91c0-033d-4e30-8ac4-f29a3b407dc1',
        #  '99fa3670-aa1a-45f6-ba8e-803c976a1163',
        #  'a35830e1-4535-47c6-aa23-be295a57ee1c',
        #  'bce3d09b-e296-4f2b-9af4-834db6412429',
        #  '7ecf8954-e49a-4605-992e-99fcee397935',
        #  '99fa3670-aa1a-45f6-ba8e-803c976a1163',
        #  'a35830e1-4535-47c6-aa23-be295a57ee1c'

    # TODO NEXT: Consider the question above (is this traversal useful), and
    # then delete or relocate traversal, simplify repr, etc
    def test_v5_traverse_uuids(self):
        exp = {'ffb7cee3-2f1f-4988-90cc-efd5184ef003':
               {'89af91c0-033d-4e30-8ac4-f29a3b407dc1':
                {'99fa3670-aa1a-45f6-ba8e-803c976a1163':
                 {'a35830e1-4535-47c6-aa23-be295a57ee1c': None}},
                'bce3d09b-e296-4f2b-9af4-834db6412429':
                {'7ecf8954-e49a-4605-992e-99fcee397935':
                 {'99fa3670-aa1a-45f6-ba8e-803c976a1163':
                  {'a35830e1-4535-47c6-aa23-be295a57ee1c': None}}}}}
        root_uuid = TEST_DATA['5']['uuid']
        actual = self.dags['5'].traverse_uuids(root_uuid)
        self.assertEqual(actual, exp)

    def test_v5_repr_contains(self):
        self.assertRegex(repr(self.dags['5']),
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

    def test_invalid_provenance(self):
        """
        Mangle an intact v5 Archive so that its checksums.md5 is invalid,
        and then build a ProvDAG with it to confirm the ProvDAG constructor
        handles broken checksums appropriately

        Specifically:
        - remove the root `<uuid>/metadata.yaml`
        - add a new file called '<uuid>/tamper.txt`
        - overwrite `<uuid>/data/index.html` with '999\n'

        Modified from test_checksum_validator.test_checksums_mismatch
        """
        original_archive = TEST_DATA['5']['qzv_fp']
        drop_file = pathlib.Path('data') / 'emperor.html'
        root_uuid = TEST_DATA['5']['uuid']
        fp_pfx = pathlib.Path(root_uuid)
        with generate_archive_with_file_removed(
            qzv_fp=original_archive,
            root_uuid=root_uuid,
                file_to_drop=drop_file) as chopped_archive:

            # We'll also add a new file
            with zipfile.ZipFile(chopped_archive, 'a') as zf:
                new_fn = str(fp_pfx / 'tamper.txt')
                zf.writestr(new_fn, 'extra file')
                # and overwrite an existing file with junk
                extant_fn = str(fp_pfx / 'data' / 'index.html')

                # we expect a warning that we're overwriting the filename
                # this CM stops the warning from propagating up to stderr/out
                with self.assertWarnsRegex(UserWarning, 'Duplicate name'):
                    with zf.open(extant_fn, 'w') as myfile:
                        myfile.write(b'999\n')

            # Is our bad-checksums warning message correct?
            uuid = TEST_DATA['5']['uuid']
            expected = ('(?s)'
                        f'Checksums are invalid for Archive {uuid}.*\n'
                        'Archive may be corrupt.*\n'
                        'Files added.*tamper.*296583.*\n'
                        'Files removed.*emperor.*c42b3.*\n'
                        'Files changed.*data.*index.*065031.*f47bc3.*'
                        )
            with self.assertWarnsRegex(UserWarning, expected):
                a_dag = ProvDAG(Config(), chopped_archive)

            # Have we set provenance_is_valid correctly?
            self.assertEqual(a_dag.provenance_is_valid,
                             ValidationCodes.INVALID)

            # Is the diff correct?
            diff = a_dag.checksum_diff
            self.assertEqual(list(diff.removed.keys()),
                             ['data/emperor.html'])
            self.assertEqual(
                diff.added,
                {'tamper.txt': '296583001b00d2b811b5871b19e0ad28'})
            self.assertEqual(
                diff.changed,
                {'data/index.html': ('065031e17943cd0780f197874c4f011e',
                                     'f47bc36040d5c7db08e4b3a457dcfbb2')
                 })

    def test_v5_archive_has_invalid_checksums(self):
        """
        Remove a file from an intact v5 Archive so that its checksums.md5 is
        invalid, and then build a ProvDAG with it to confirm the ProvDAG
        constructor handles broken checksums appropriately
        """
        drop_file = pathlib.Path('data') / 'index.html'
        with generate_archive_with_file_removed(
            qzv_fp=TEST_DATA['5']['qzv_fp'],
            root_uuid=TEST_DATA['5']['uuid'],
                file_to_drop=drop_file) as chopped_archive:

            # Is our bad-checksums warning message correct?
            uuid = TEST_DATA['5']['uuid']
            expected = (f'(?s)Checksums are invalid for Archive {uuid}.*')
            with self.assertWarnsRegex(UserWarning, expected):
                a_dag = ProvDAG(Config(), chopped_archive)

            # Have we set provenance_is_valid correctly?
            self.assertEqual(a_dag.provenance_is_valid,
                             ValidationCodes.INVALID)

            # Is the diff correct?
            diff = a_dag.checksum_diff
            self.assertEqual(list(diff.removed.keys()),
                             ['data/index.html'])
            self.assertEqual(diff.added, {})
            self.assertEqual(diff.changed, {})

    def test_v5_with_missing_checksums_md5(self):
        drop_file = pathlib.Path('checksums.md5')
        with generate_archive_with_file_removed(
            qzv_fp=TEST_DATA['5']['qzv_fp'],
            root_uuid=TEST_DATA['5']['uuid'],
                file_to_drop=drop_file) as chopped_archive:

            # Is our bad-checksums warning message correct?
            uuid = TEST_DATA['5']['uuid']
            expected = (f'no item.*{uuid}.*Archive may be corrupt')
            with self.assertWarnsRegex(UserWarning, expected):
                a_dag = ProvDAG(Config(), chopped_archive)

            # Have we set provenance_is_valid correctly?
            self.assertEqual(a_dag.provenance_is_valid,
                             ValidationCodes.INVALID)

            # Is the diff correct?
            diff = a_dag.checksum_diff
            self.assertEqual(diff, None)

    def test_ProvDAG_error_if_missing_node_files(self):
        pfx = 'provenance/artifacts/'
        for archive_version in TEST_DATA:
            # V0 doesn't have root nodes
            if archive_version == '0':
                continue
            root_uuid = TEST_DATA[archive_version]['uuid']
            node_uuid = TEST_DATA[archive_version]['nonroot_node']
            parser = TEST_DATA[archive_version]['parser']
            fnames = parser.expected_files_in_all_nodes
            for name in fnames:
                drop_file = pathlib.Path(pfx) / node_uuid / name
                with generate_archive_with_file_removed(
                    qzv_fp=TEST_DATA[archive_version]['qzv_fp'],
                    root_uuid=root_uuid,
                        file_to_drop=drop_file) as chopped_archive:

                    # Fudging this to match what the user sees - 'action.yaml'
                    if name == 'action/action.yaml':
                        name = 'action.yaml'
                    expected = (
                        f"(?s)Malformed.*{name}.*{node_uuid}.*"
                        f"{root_uuid}.*corrupt"
                    )
                    with self.assertRaisesRegex(ValueError, expected):
                        # Only v5 warns on this, so an assert would be clunky
                        with warnings.catch_warnings():
                            warnings.filterwarnings(
                                'ignore',
                                f'Checksums.*invalid.*{root_uuid}',
                                UserWarning)
                            ProvDAG(Config(), chopped_archive)


class ProvDAGTestsNoChecksumValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.no_checksum_dags = dict()
        for archive_version in list(TEST_DATA):
            # supress warning from parsing provenance for a v0 provDag
            uuid = TEST_DATA['0']['uuid']
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore',  f'Art.*{uuid}.*prior')
                cls.no_checksum_dags[archive_version] = ProvDAG(
                    Config(perform_checksum_validation=False),
                    str(TEST_DATA[archive_version]['qzv_fp']))

    # This should only trigger if something fails in setup or above
    # e.g. if a ProvDag fails to initialize
    def test_smoke(self):
        self.assertTrue(True)

    def test_no_checksum_validation_intact_archives(self):
        dags = self.no_checksum_dags
        for vz in dags:
            self.assertEqual(type(dags[vz].parser_results), ParserResults)
            self.assertEqual(type(dags[vz].parser_results.root_md),
                             _ResultMetadata)
            self.assertEqual(dags[vz].parser_results.root_md.uuid,
                             TEST_DATA[vz]['uuid'])
            self.assertEqual(dags[vz].parser_results.num_results,
                             TEST_DATA[vz]['n_res'])
            self.assertIs(type(dags[vz].parser_results.archive_contents), dict)
            self.assertEqual(dags[vz].provenance_is_valid,
                             ValidationCodes.VALIDATION_OPTOUT)
            self.assertEqual(dags[vz].checksum_diff, None)

    def test_no_checksum_missing_checksums_md5(self):
        drop_file = pathlib.Path('checksums.md5')
        with generate_archive_with_file_removed(
            qzv_fp=TEST_DATA['5']['qzv_fp'],
            root_uuid=TEST_DATA['5']['uuid'],
                file_to_drop=drop_file) as chopped_archive:

            a_dag = ProvDAG(Config(perform_checksum_validation=False),
                            chopped_archive)

            # Have we set provenance_is_valid correctly?
            self.assertEqual(
                a_dag.provenance_is_valid, ValidationCodes.VALIDATION_OPTOUT)

            # Is the diff correct?
            diff = a_dag.checksum_diff
            self.assertEqual(diff, None)

    def test_no_checksum_validation_missing_node_files(self):
        pfx = 'provenance/artifacts/'
        for archive_version in TEST_DATA:
            # V0 doesn't have root nodes
            if archive_version == '0':
                continue
            root_uuid = TEST_DATA[archive_version]['uuid']
            node_uuid = TEST_DATA[archive_version]['nonroot_node']
            parser = TEST_DATA[archive_version]['parser']
            fnames = parser.expected_files_in_all_nodes
            for name in fnames:
                drop_file = pathlib.Path(pfx) / node_uuid / name
                with generate_archive_with_file_removed(
                    qzv_fp=TEST_DATA[archive_version]['qzv_fp'],
                    root_uuid=root_uuid,
                        file_to_drop=drop_file) as chopped_archive:

                    # Fudging this to match what the user sees - 'action.yaml'
                    if name == 'action/action.yaml':
                        name = 'action.yaml'
                    expected = (
                        f"(?s)Malformed.*{name}.*{node_uuid}.*"
                        f"{root_uuid}.*corrupt"
                    )
                    with self.assertRaisesRegex(ValueError, expected):
                        ProvDAG(Config(perform_checksum_validation=False),
                                chopped_archive)


class ParserVxTests(unittest.TestCase):
    def test_parse_root_md(self):
        for archive_version in TEST_DATA:
            fp = TEST_DATA[archive_version]['qzv_fp']
            root_uuid = TEST_DATA[archive_version]['uuid']
            with zipfile.ZipFile(fp) as zf:
                root_md = TEST_DATA[archive_version]['parser']._parse_root_md(
                    zf, root_uuid)
                self.assertEqual(root_md.uuid, root_uuid)
                self.assertEqual(root_md.type,  'Visualization')
                self.assertEqual(root_md.format, None)

    def test_parse_root_md_no_md_yaml(self):
        qzv_no_root_md = os.path.join(DATA_DIR, 'no_root_md_yaml.qzv')
        for archive_version in TEST_DATA:
            root_uuid = TEST_DATA[archive_version]['uuid']
            with zipfile.ZipFile(qzv_no_root_md) as zf:
                with self.assertRaisesRegex(ValueError, 'Malformed.*metadata'):
                    TEST_DATA[archive_version]['parser']._parse_root_md(
                        zf, root_uuid)

    def test_populate_archive(self):
        for archive_version in TEST_DATA:
            fp = TEST_DATA[archive_version]['qzv_fp']
            root_uuid = TEST_DATA[archive_version]['uuid']
            with zipfile.ZipFile(fp) as zf:
                if archive_version == '0':
                    with self.assertWarnsRegex(
                        UserWarning,
                            'Artifact 0b8b47.*prior to provenance'):
                        res = TEST_DATA[archive_version]['parser'].parse_prov(
                            Config(), zf)
                else:
                    res = TEST_DATA[archive_version]['parser'].parse_prov(
                        Config(), zf)
                # Did we capture result metadata correctly?
                root_md = res.root_md
                self.assertEqual(type(root_md), _ResultMetadata)
                self.assertEqual(root_md.uuid, root_uuid)
                self.assertEqual(root_md.type,  'Visualization')
                self.assertEqual(root_md.format, None)
                # Does this archive have the right number of Results?
                self.assertEqual(res.num_results,
                                 TEST_DATA[archive_version]['n_res'])
                # Is contents a dict?
                self.assertIs(type(res.archive_contents), dict)
                # Is the root UUID a key in the contents dict?
                self.assertIn(root_uuid, res.archive_contents)
                # Is contents keyed on uuids, containing ProvNodes?
                self.assertIs(type(res.archive_contents[root_uuid]), ProvNode)

    def test_get_nonroot_uuid(self):
        md_example = pathlib.Path(
            'arch_root/provenance/artifacts/uuid123/metadata.yaml')
        action_example = pathlib.Path(
            'arch_root/provenance/artifacts/uuid123/action/action.yaml')
        exp = 'uuid123'

        # Only parsers from v1 forward have this method
        parsers = [TEST_DATA[vrsn]['parser'] for vrsn in TEST_DATA
                   if vrsn != '0']

        for parser in parsers:
            self.assertEqual(parser._get_nonroot_uuid(md_example), exp)
            self.assertEqual(parser._get_nonroot_uuid(action_example), exp)

    def test_validate_checksums(self):
        for archive_version in TEST_DATA:
            with zipfile.ZipFile(TEST_DATA[archive_version]['qzv_fp']) as zf:
                parser = TEST_DATA[archive_version]['parser']
                is_valid, diff = parser._validate_checksums(zf)
                self.assertEqual(is_valid,
                                 TEST_DATA[archive_version]['prov_is_valid'])
                self.assertEqual(diff,
                                 TEST_DATA[archive_version]['checksum'])

    def test_correct_validate_checksums_method_called(self):
        # We want to confirm that parse_prov uses the local _validate_checksums
        # even when it calls super().parse_prov() internally
        for archive_version in TEST_DATA:
            parser = TEST_DATA[archive_version]['parser']
            parser._validate_checksums = MagicMock(
                # return values only here to facilitate normal execution
                return_value=(TEST_DATA[archive_version]['prov_is_valid'],
                              TEST_DATA[archive_version]['checksum']))
            with zipfile.ZipFile(TEST_DATA[archive_version]['qzv_fp']) as zf:
                if archive_version == '0':
                    # supress warning from parsing provenance for a v0 ProvDAG
                    uuid = TEST_DATA['0']['uuid']
                    with warnings.catch_warnings():
                        warnings.filterwarnings(
                            'ignore',  f'Art.*{uuid}.*prior')
                        parser.parse_prov(Config(), zf)
                        parser._validate_checksums.assert_called_once()
                else:
                    parser.parse_prov(Config(), zf)
                    parser._validate_checksums.assert_called_once()


class FormatHandlerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = Config()

    # Can we make a FormatHandler without anything blowing up?
    def test_smoke(self):
        for arch_ver in TEST_DATA:
            qzv = TEST_DATA[arch_ver]['qzv_fp']
            with zipfile.ZipFile(qzv) as zf:
                FormatHandler(self.cfg, zf)
        self.assertTrue(True)

    def test_archive_version(self):
        for arch_ver in TEST_DATA:
            qzv = TEST_DATA[arch_ver]['qzv_fp']
            with zipfile.ZipFile(qzv) as zf:
                handler = FormatHandler(self.cfg, zf)
                self.assertEqual(handler.archive_version,
                                 TEST_DATA[arch_ver]['av'])

    def test_framework_version(self):
        for arch_ver in TEST_DATA:
            qzv = TEST_DATA[arch_ver]['qzv_fp']
            with zipfile.ZipFile(qzv) as zf:
                handler = FormatHandler(self.cfg, zf)
                self.assertEqual(handler.framework_version,
                                 TEST_DATA[arch_ver]['fwv'])

    def test_correct_parser(self):
        for arch_ver in TEST_DATA:
            qzv = TEST_DATA[arch_ver]['qzv_fp']
            with zipfile.ZipFile(qzv) as zf:
                handler = FormatHandler(self.cfg, zf)
                self.assertEqual(handler.parser,
                                 TEST_DATA[arch_ver]['parser'])

    def test_parse(self):
        uuid = TEST_DATA['5']['uuid']
        with zipfile.ZipFile(TEST_DATA['5']['qzv_fp']) as zf:
            handler = FormatHandler(self.cfg, zf)
            parser_results = handler.parse(zf)
            md = parser_results.root_md
            self.assertIs(type(md), _ResultMetadata)
            self.assertEqual(md.uuid, uuid)
            self.assertEqual(md.type, 'Visualization')
            self.assertEqual(md.format, None)
            self.assertIs(type(parser_results.num_results), int)
            self.assertEqual(parser_results.num_results, 15)
            self.assertIn(uuid, parser_results.archive_contents)
            self.assertIs(
                type(parser_results.archive_contents[uuid]), ProvNode)


class ResultMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        v5_qzv = TEST_DATA['5']['qzv_fp']
        cls.v5_uuid = TEST_DATA['5']['uuid']
        md_fp = f'{cls.v5_uuid}/provenance/metadata.yaml'
        with zipfile.ZipFile(str(v5_qzv)) as zf:
            cls.v5_root_md = _ResultMetadata(zf, md_fp)

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
    @classmethod
    def setUpClass(cls):
        root_action_fp = os.path.join(DATA_DIR,
                                      'action_emperor_root_node_v5.zip')
        import_action_fp = os.path.join(DATA_DIR, 'action_import_v5.zip')
        with zipfile.ZipFile(root_action_fp) as zf:
            cls.act = _Action(zf, 'action.yaml')

        with zipfile.ZipFile(import_action_fp) as zf:
            cls.imp_act = _Action(zf, 'action.yaml')

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
        self.assertEqual(self.act.action_name, exp)

    def test_plugin(self):
        exp = 'diversity'
        self.assertEqual(self.act.plugin, exp)

    def test_repr(self):
        exp = ('_Action(action_id=5bc4b090-abbc-46b0-a219-346c8026f7d7, '
               'type=pipeline, plugin=diversity, '
               'action=core_metrics_phylogenetic)')
        self.assertEqual(repr(self.act), exp)

    # NOTE: Import is not handled by a plugin, so the parser provides values
    # for the action_name and plugin properties not present in action.yaml
    def test_action_for_import_node(self):
        exp = 'import'
        self.assertEqual(self.imp_act.action_name, exp)

    def test_plugin_for_import_node(self):
        exp = 'framework'
        self.assertEqual(self.imp_act.plugin, exp)


class CitationsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cite_strs = ['cite_none', 'cite_one', 'cite_many']
        cls.bibs = [bib+'.bib' for bib in cite_strs]
        cls.zips = [os.path.join(DATA_DIR, bib+'.zip') for bib in cite_strs]

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
    @classmethod
    def setUpClass(cls):
        # Build root nodes for all archive format versions
        cls.nodes = dict()
        for k in list(TEST_DATA):
            with zipfile.ZipFile(TEST_DATA[k]['qzv_fp']) as zf:
                all_filenames = zf.namelist()
                root_md_fnames = filter(is_root_provnode_data, all_filenames)
                root_md_fps = [pathlib.Path(fp) for fp in root_md_fnames]
                cls.nodes[k] = ProvNode(zf, root_md_fps)

        # Build a minimal node in which Artifacts are passed as metadata
        filename = pathlib.Path('minimal_v4_artifact_as_md.zip')
        pfx = pathlib.Path(TEST_DATA['5']['uuid'])
        artifact_as_md_fp = os.path.join(DATA_DIR, filename)
        with zipfile.ZipFile(artifact_as_md_fp) as zf:
            cls.art_as_md_node = ProvNode(
                zf,
                [pfx / 'VERSION',
                 pfx / 'metadata.yaml',
                 pfx / 'provenance/action/action.yaml']
                )

        # Build a nonroot node without study metadata
        with zipfile.ZipFile(TEST_DATA['5']['qzv_fp']) as zf:
            node_id = '3b7d36ff-37ab-4ac2-958b-6a547d442bcf'
            all_filenames = zf.namelist()
            node_fps = [
                pathlib.Path(fp) for fp in all_filenames if
                node_id in fp and
                ('metadata.yaml' in fp or 'action.yaml' in fp
                 or 'VERSION' in fp
                 )]
            cls.nonroot_non_md_node = ProvNode(zf, node_fps)

            # Build a nonroot node with study metadata
            node_id = '0af08fa8-48b7-4c6a-83c6-e0f766156343'
            all_filenames = zf.namelist()
            node_fps = [
                pathlib.Path(fp) for fp in all_filenames if
                node_id in fp and
                ('metadata.yaml' in fp or 'action.yaml' in fp
                 or 'VERSION' in fp
                 )]
            cls.nonroot_md_node = ProvNode(zf, node_fps)

    def test_smoke(self):
        self.assertTrue(True)
        for node_vzn in self.nodes:
            self.assertIs(type(self.nodes[node_vzn]), ProvNode)

    def test_properties_with_viz(self):
        for node in self.nodes:
            self.assertEqual(self.nodes[node].uuid, TEST_DATA[node]['uuid'])
            self.assertEqual(self.nodes[node].sem_type, 'Visualization')
            self.assertEqual(self.nodes[node].format, None)
            self.assertEqual(self.nodes[node].archive_version,
                             TEST_DATA[node]['av'])
            self.assertEqual(self.nodes[node].framework_version,
                             TEST_DATA[node]['fwv'])
            self.assertEqual(self.nodes[node].has_provenance,
                             TEST_DATA[node]['has_prov'])

    def test_self_eq(self):
        self.assertReallyEqual(self.nodes['5'], self.nodes['5'])

    def test_eq(self):
        # Mock has no matching UUID
        mock_node = MagicMock()
        self.assertNotEqual(self.nodes['5'], mock_node)

        # Mock has bad UUID
        mock_node.uuid = 'gerbil'
        self.assertReallyNotEqual(self.nodes['5'], mock_node)

        # Matching UUIDs insufficient if classes differ
        mock_node.uuid = TEST_DATA['5']['uuid']
        self.assertReallyNotEqual(self.nodes['5'], mock_node)
        mock_node.__class__ = ProvNode
        self.assertReallyEqual(self.nodes['5'], mock_node)

    def test_is_hashable(self):
        exp_hash = hash(TEST_DATA['5']['uuid'])
        self.assertReallyEqual(hash(self.nodes['5']), exp_hash)

    def test_str(self):
        for node_vzn in self.nodes:
            uuid = TEST_DATA[node_vzn]['uuid']
            self.assertEqual(str(self.nodes[node_vzn]), f'{uuid}')

    def test_repr(self):
        for node_vzn in self.nodes:
            uuid = TEST_DATA[node_vzn]['uuid']
            self.assertEqual(repr(self.nodes[node_vzn]),
                             f'ProvNode({uuid}, Visualization, fmt=None)')

    def test_archive_version(self):
        for node_vzn in self.nodes:
            self.assertEqual(self.nodes[node_vzn].archive_version,
                             TEST_DATA[node_vzn]['av'])

    def test_framework_version(self):
        for node_vzn in self.nodes:
            self.assertEqual(self.nodes[node_vzn].framework_version,
                             TEST_DATA[node_vzn]['fwv'])

    def test_get_metadata_from_action(self):
        find_md = self.nodes['5']._get_metadata_from_Action
        md1 = MetadataInfo([], 'some_metadata.tsv')
        md2 = MetadataInfo(['301b4'], 'other_metadata.tsv')
        md3 = MetadataInfo(['4154', '5555b'], 'merged_metadata.tsv')
        action_details = \
            {'parameters':
                [
                 {'some_param': 'foo'},
                 {'arbitrary_metadata_name': md1},
                 {'other_metadata': md2},
                 {'double_md': md3},
                 ]}
        all_md, artifacts_as_md = find_md(action_details)
        all_exp = {'arbitrary_metadata_name': 'some_metadata.tsv',
                   'other_metadata': 'other_metadata.tsv',
                   'double_md': 'merged_metadata.tsv',
                   }
        a_as_md_exp = [{'artifact_passed_as_metadata': '301b4'},
                       {'artifact_passed_as_metadata': '4154'},
                       {'artifact_passed_as_metadata': '5555b'},
                       ]
        self.assertEqual(all_md, all_exp)
        self.assertEqual(artifacts_as_md, a_as_md_exp)

    def test_get_metadata_from_action_with_actual_node(self):
        find_md = self.nodes['5']._get_metadata_from_Action
        all_md, artifacts_as_md = find_md(
            self.nodes['5'].action._action_details)
        exp = {'metadata': 'metadata.tsv'}
        self.assertEqual(all_md, exp)
        self.assertEqual(artifacts_as_md, [])

    def test_get_metadata_from_action_with_no_params(self):
        # Not sure which of these test data are possible in action.yaml, but
        # we'll check them both just in case
        find_md = self.nodes['5']._get_metadata_from_Action
        action_details = \
            {'parameters': []}
        all_md, artifacts_as_md = find_md(action_details)
        self.assertEqual(all_md, {})
        self.assertEqual(artifacts_as_md, [])

        action_details = {'non-parameters-key': 'here is a thing'}
        all_md, artifacts_as_md = find_md(action_details)
        self.assertEqual(all_md, {})
        self.assertEqual(artifacts_as_md, [])

    def test_metadata_available_in_property(self):
        self.assertEqual(type(self.nodes['5'].metadata), dict)
        self.assertIn('metadata', self.nodes['5'].metadata)
        self.assertEqual(type(self.nodes['5'].metadata['metadata']),
                         pd.DataFrame)

    def test_metadata_is_correct(self):
        # Were parameter names captured correctly?
        self.assertIn('sample_metadata', self.art_as_md_node.metadata)
        self.assertIn('feature_metadata', self.art_as_md_node.metadata)

        # Does sample metadata look right?
        s_m_data = {'sampleid': ['#q2:types', 's_id_123'],
                    'barcodeSequence': ['categorical', 'TACCGCTTCTTC'],
                    'isGerbil': ['categorical', 'totally']}
        s_m_exp = pd.DataFrame(s_m_data, columns=s_m_data.keys())
        pd.testing.assert_frame_equal(
            s_m_exp,
            self.art_as_md_node.metadata['sample_metadata'])

        # Does feature metadata look right?
        f_m_data = {'Feature ID': ['#q2:types', 'feature_id_123'],
                    'Taxon': ['categorical', 'd__Bacteria; p__Firmicutes'],
                    'Confidence': ['categorical', '0.9']}
        f_m_exp = pd.DataFrame(f_m_data, columns=f_m_data.keys())
        pd.testing.assert_frame_equal(
            f_m_exp,
            self.art_as_md_node.metadata['feature_metadata'])

    def test_has_no_provenance_so_no_metadata(self):
        self.assertEqual(self.nodes['0'].has_provenance, False)
        self.assertEqual(self.nodes['0'].metadata, None)

    def test_node_has_provenance_but_no_metadata(self):
        self.assertIn('3b7d36ff', self.nonroot_non_md_node.uuid)
        self.assertEqual(self.nonroot_non_md_node.has_provenance, True)
        self.assertEqual(self.nonroot_non_md_node.metadata, {})

    def test_parse_metadata_for_nonroot_node(self):
        self.assertIn('0af08fa8', self.nonroot_md_node.uuid)
        self.assertEqual(self.nonroot_md_node.has_provenance, True)
        self.assertIn('metadata', self.nonroot_md_node.metadata)

    def test_parents(self):
        exp = [{'table': '89af91c0-033d-4e30-8ac4-f29a3b407dc1'},
               {'phylogeny': 'bce3d09b-e296-4f2b-9af4-834db6412429'}]
        self.assertEqual(self.nodes['5'].parents, exp)

    def test_parents_with_artifact_passed_as_md(self):
        exp = [{'tree': 'e710bdc5-e875-4876-b238-5451e3e8eb46'},
               {'feature_table': 'abc22fdc-e7fa-4976-a980-8f2ff8c4bb58'},
               {'pcoa': '1ed04b10-d29c-495f-996e-3d4db89434d2'},
               {'artifact_passed_as_metadata':
                '415409a4-371d-4c69-9433-e3eaba5301b4'},
               ]
        actual = self.art_as_md_node.parents
        self.assertEqual(actual, exp)

    def test_parents_for_import_node(self):
        with zipfile.ZipFile(TEST_DATA['5']['qzv_fp']) as zf:
            import_node_id = 'a35830e1-4535-47c6-aa23-be295a57ee1c'
            reqd_fps = ('VERSION', 'metadata.yaml', 'action.yaml')
            import_node_fps = [
                pathlib.Path(fp) for fp in zf.namelist()
                if import_node_id in fp
                and any(map(lambda x: x in fp, reqd_fps))
                ]
            import_node = ProvNode(zf, import_node_fps)

        self.assertEqual(import_node.parents, [])
