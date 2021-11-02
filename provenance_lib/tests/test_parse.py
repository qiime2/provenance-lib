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
                    archive_fp=str(TEST_DATA[archive_version]['qzv_fp']))

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
                node = ProvNode(Config(), zf, root_md_fps)
                self.assertEqual(node, self.dags[dag_version].root_node)

    def test_number_of_actions(self):
        for dag_version in self.dags:
            self.assertEqual(len(self.dags[dag_version]),
                             TEST_DATA[dag_version]['n_res'])

    def test_nonexistent_fp(self):
        fake_fp = os.path.join(DATA_DIR, 'not_a_filepath.qza')
        with self.assertRaisesRegex(FileNotFoundError, 'not_a_filepath.qza'):
            ProvDAG(archive_fp=fake_fp)

    def test_not_a_zip_archive(self):
        not_a_zip = os.path.join(DATA_DIR, 'not_a_zip.txt')
        with self.assertRaisesRegex(zipfile.BadZipFile,
                                    'File is not a zip file'):
            ProvDAG(archive_fp=not_a_zip)

    def test_has_digraph(self):
        for dag_version in self.dags:
            self.assertIsInstance(self.dags[dag_version].dag, DiGraph)

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
            self.assertEqual(len(self.dags[vz]),
                             TEST_DATA[vz]['n_res'])
            self.assertIs(
                type(self.dags[vz].parser_results.archive_contents),
                dict)
            self.assertEqual(self.dags[vz].provenance_is_valid,
                             TEST_DATA[vz]['prov_is_valid'])
            self.assertEqual(self.dags[vz].checksum_diff,
                             TEST_DATA[vz]['checksum'])

    def test_v5_root_node_attributes(self):
        dag = self.dags['5']
        root_uuid = TEST_DATA['5']['uuid']
        root_node = dag.get_node_data(root_uuid)
        # Check node at the dag level
        self.assertTrue(dag.node_has_provenance(root_uuid))
        # Check inner node attribute is the same
        self.assertTrue(root_node.has_provenance)
        self.assertEqual(type(root_node), ProvNode)
        # Smoke-test that this is actually the node we're looking for
        # Node attributes are tested properly in ProvNodeTests
        self.assertEqual(root_node.uuid, root_uuid)

    def test_V5_has_edges(self):
        self.assertTrue(self.dags['5'].has_edge(
            '89af91c0-033d-4e30-8ac4-f29a3b407dc1',
            'ffb7cee3-2f1f-4988-90cc-efd5184ef003'))
        self.assertTrue(self.dags['5'].has_edge(
            'bce3d09b-e296-4f2b-9af4-834db6412429',
            'ffb7cee3-2f1f-4988-90cc-efd5184ef003'))

    def test_repr(self):
        for dag_vzn in self.dags:
            uuid = TEST_DATA[dag_vzn]['uuid']
            self.assertRegex(str(self.dags[dag_vzn]),
                             f'(?s)UUID:\t\t{uuid}.*Type.*Data Format')

    def test_str(self):
        for dag_vzn in self.dags:
            uuid = TEST_DATA[dag_vzn]['uuid']
            self.assertRegex(str(self.dags[dag_vzn]),
                             f'(?s)UUID:\t\t{uuid}.*Type.*Data Format')

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
        self.assertEqual(nodes[node_list[0]]['node_data']._parents,
                         root_parents)
        # non-alias node
        n1_parents = [{'table': '89af91c0-033d-4e30-8ac4-f29a3b407dc1'},
                      ]
        self.assertEqual(nodes[node_list[1]]['node_data']._parents,
                         n1_parents)
        # some other nodes
        n2_parents = [{'tree': 'd32a5ea6-1ca1-4635-b522-2253568ae35b'},
                      ]
        self.assertEqual(nodes[node_list[2]]['node_data']._parents,
                         n2_parents)
        n3_parents = [{'demultiplexed_seqs':
                       '99fa3670-aa1a-45f6-ba8e-803c976a1163'}]
        self.assertEqual(nodes[node_list[3]]['node_data']._parents,
                         n3_parents)
        # import node
        n10_parents = []
        self.assertEqual(nodes[node_list[10]]['node_data']._parents,
                         n10_parents)

    def test_v5_get_nested_provenance_nodes(self):
        exp = {'ffb7cee3-2f1f-4988-90cc-efd5184ef003',
               'bce3d09b-e296-4f2b-9af4-834db6412429',
               '89af91c0-033d-4e30-8ac4-f29a3b407dc1',
               '7ecf8954-e49a-4605-992e-99fcee397935',
               '99fa3670-aa1a-45f6-ba8e-803c976a1163',
               'a35830e1-4535-47c6-aa23-be295a57ee1c',
               }
        root_uuid = TEST_DATA['5']['uuid']
        actual = self.dags['5'].get_nested_provenance_nodes(root_uuid)
        self.assertEqual(actual, exp)

    def test_v5_relabel_nodes(self):
        # This function modifies labels in place, so create a local ProvDAG
        # to protect our test data
        dag = ProvDAG(archive_fp=str(TEST_DATA['5']['qzv_fp']))
        # Test new node names
        exp_nodes = ['ffb7cee3',
                     '0af08fa8',
                     '3b7d36ff',
                     '7ecf8954',
                     '9cc3281a',
                     '025e723d',
                     '83a80bfd',
                     '89af91c0',
                     '99fa3670',
                     '430a6575',
                     'a35830e1',
                     'aea3994b',
                     'bce3d09b',
                     'd32a5ea6',
                     'f20cecd6',
                     ]
        new_labels = {node: node[:8] for node in dag.nodes}
        dag.relabel_nodes(new_labels)
        for node in exp_nodes:
            self.assertIn(node, dag.nodes)

        # Confirm root_uuid state is consistent with the relabeled node names
        self.assertEqual(dag.root_uuid, exp_nodes[0])

    def test_v5_nested_view(self):
        exp_nodes = {'ffb7cee3-2f1f-4988-90cc-efd5184ef003',
                     'bce3d09b-e296-4f2b-9af4-834db6412429',
                     '89af91c0-033d-4e30-8ac4-f29a3b407dc1',
                     '7ecf8954-e49a-4605-992e-99fcee397935',
                     '99fa3670-aa1a-45f6-ba8e-803c976a1163',
                     'a35830e1-4535-47c6-aa23-be295a57ee1c',
                     }
        view = self.dags['5'].nested_view
        self.assertIsInstance(view, DiGraph)
        self.assertEqual(len(view), 6)
        for node in exp_nodes:
            self.assertIn(node, view.nodes)

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
                a_dag = ProvDAG(archive_fp=chopped_archive)

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
                a_dag = ProvDAG(archive_fp=chopped_archive)

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
                a_dag = ProvDAG(archive_fp=chopped_archive)

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
                            ProvDAG(archive_fp=chopped_archive)

    def test_mixed_v0_v1_archive(self):
        mixed_archive_fp = os.path.join(DATA_DIR, 'mixed_v0_v1_uu_emperor.qzv')
        v1_uuid = TEST_DATA['1']['uuid']
        v0_uuid = '9f6a0f3e-22e6-4c39-8733-4e672919bbc7'

        with self.assertWarnsRegex(
                UserWarning, f'(:?)Art.*{v0_uuid}.*prior.*incomplete'):
            dag = ProvDAG(archive_fp=mixed_archive_fp)
            self.assertEqual(dag.node_has_provenance(v1_uuid), True)
            self.assertEqual(dag.get_node_data(v1_uuid).uuid, v1_uuid)

            self.assertEqual(dag.node_has_provenance(v0_uuid), False)
            self.assertEqual(dag.get_node_data(v0_uuid), None)


class ProvDAGUnionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # TODO: We'll need different test data now that this is Union
        filename = pathlib.Path('minimal_v4_artifact_as_md.zip')
        artifact_as_md_fp = os.path.join(DATA_DIR, filename)
        cls.dag = ProvDAG(artifact_as_md_fp)

    # This should only trigger if something fails in setup or above
    # e.g. if a ProvDag fails to initialize
    def test_smoke(self):
        self.assertTrue(True)

    def test_basic_union(self):
        pass

    def test_union_all_with_multiple_inputs(self):
        pass

    def test_one_artifact_supersets_another(self):
        pass

    def test_graphs_disjoint_same_analysis(self):
        """
        E.g. there are just qzvs missing from the set of unioned archives
        """
        pass

    def test_graphs_disjoint_different_analyses(self):
        """
        E.g. a stray archive got mixed in from an unrelated analysis
        """
        pass

    def test_dag_with_no_provenance(self):
        """
        "All" v0 archives
        """
        pass

    def test_dag_with_mixed_archives(self):
        """
        e.g. v0 and v3 archives in the same analysis
        """
        pass

    def test_dag_with_artifacts_passed_as_metadata(self):
        pass


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
                    archive_fp=str(TEST_DATA[archive_version]['qzv_fp']),
                    cfg=Config(perform_checksum_validation=False))

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
            self.assertEqual(len(dags[vz]),
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

            a_dag = ProvDAG(archive_fp=chopped_archive,
                            cfg=Config(perform_checksum_validation=False))

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
                        ProvDAG(archive_fp=chopped_archive,
                                cfg=Config(perform_checksum_validation=False))


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
                self.assertEqual(len(res.archive_contents),
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
            self.assertEqual(len(parser_results.archive_contents), 15)
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
        cfg = Config(parse_study_metadata=True)
        # Build root nodes for all archive format versions
        cls.nodes = dict()
        for k in list(TEST_DATA):
            with zipfile.ZipFile(TEST_DATA[k]['qzv_fp']) as zf:
                all_filenames = zf.namelist()
                root_md_fnames = filter(is_root_provnode_data, all_filenames)
                root_md_fps = [pathlib.Path(fp) for fp in root_md_fnames]
                cls.nodes[k] = ProvNode(cfg, zf, root_md_fps)

        # Build a minimal node in which Artifacts are passed as metadata
        filename = pathlib.Path('minimal_v4_artifact_as_md.zip')
        # This manufactured v4 test archive "happens" to have the same root
        # UUID as the standard v5 archive
        pfx = pathlib.Path(TEST_DATA['5']['uuid'])
        artifact_as_md_fp = os.path.join(DATA_DIR, filename)
        with zipfile.ZipFile(artifact_as_md_fp) as zf:
            cls.art_as_md_node = ProvNode(
                cfg,
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
            cls.nonroot_non_md_node = ProvNode(cfg, zf, node_fps)

            # Build a nonroot node with study metadata
            node_id = '0af08fa8-48b7-4c6a-83c6-e0f766156343'
            all_filenames = zf.namelist()
            node_fps = [
                pathlib.Path(fp) for fp in all_filenames if
                node_id in fp and
                ('metadata.yaml' in fp or 'action.yaml' in fp
                 or 'VERSION' in fp
                 )]
            cls.nonroot_md_node = ProvNode(cfg, zf, node_fps)

            # Build a root node and don't parse study metadata files
            node_id = TEST_DATA['5']['uuid']
            root_md_fnames = filter(is_root_provnode_data, zf.namelist())
            root_md_fps = [pathlib.Path(fp) for fp in root_md_fnames]
            cfg = Config(parse_study_metadata=False)
            cls.dont_parse_md_files_node = ProvNode(cfg, zf, root_md_fps)

    def test_smoke(self):
        self.assertTrue(True)
        for node_vzn in self.nodes:
            self.assertIs(type(self.nodes[node_vzn]), ProvNode)

    def test_properties_with_viz(self):
        for node in self.nodes:
            self.assertEqual(self.nodes[node].uuid, TEST_DATA[node]['uuid'])
            self.assertEqual(self.nodes[node].type, 'Visualization')
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

    def test_metadata_not_available_in_property_w_opt_out(self):
        self.assertEqual(self.dont_parse_md_files_node.metadata, None)

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
        self.assertEqual(self.nodes['5']._parents, exp)

    def test_parents_no_prov(self):
        no_prov_node = self.nodes['0']
        self.assertFalse(no_prov_node.has_provenance)
        self.assertEqual(no_prov_node._parents, None)

    def test_parents_with_artifact_passed_as_md(self):
        exp = [{'tree': 'e710bdc5-e875-4876-b238-5451e3e8eb46'},
               {'feature_table': 'abc22fdc-e7fa-4976-a980-8f2ff8c4bb58'},
               {'pcoa': '1ed04b10-d29c-495f-996e-3d4db89434d2'},
               {'artifact_passed_as_metadata':
                '415409a4-371d-4c69-9433-e3eaba5301b4'},
               ]
        actual = self.art_as_md_node._parents
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
            import_node = ProvNode(Config(), zf, import_node_fps)

        self.assertEqual(import_node._parents, [])
