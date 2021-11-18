import copy
import networkx as nx
import os
import pathlib
import unittest
import warnings
import zipfile

from networkx import DiGraph
from networkx.classes.reportviews import NodeView  # type: ignore

from ..checksum_validator import ChecksumDiff, ValidationCode
from ..parse import (
    ProvDAG, UnparseableDataError, ProvDAGParser, ParserDispatcher,
)
from ..util import UUID
from ..zipfile_parser import (
    ParserV0, ParserV1, ParserV2, ParserV3, ParserV4, ParserV5,
    Config, ProvNode, ParserResults,
)

from .testing_utilities import (
    is_root_provnode_data, generate_archive_with_file_removed,
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
          'prov_is_valid': ValidationCode.PREDATES_CHECKSUMS,
          # TODO: I think all of these checksum values are wrong but not
          # failing (and therefore untested). Should be ChecksumDiff({}, ...)
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
          'prov_is_valid': ValidationCode.PREDATES_CHECKSUMS,
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
           'prov_is_valid': ValidationCode.PREDATES_CHECKSUMS,
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
           'prov_is_valid': ValidationCode.PREDATES_CHECKSUMS,
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
          'prov_is_valid': ValidationCode.PREDATES_CHECKSUMS,
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
          'prov_is_valid': ValidationCode.PREDATES_CHECKSUMS,
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
          'prov_is_valid': ValidationCode.VALID,
          'checksum': ChecksumDiff({}, {}, {}),
          },
    }


class ProvDAGTests(unittest.TestCase):
    # Remove the character limit when reporting failing tests for this class
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.dags = dict()
        for archive_version in TEST_DATA:
            # supress warning from parsing provenance for a v0 provDag
            uuid = TEST_DATA['0']['uuid']
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore',  f'Art.*{uuid}.*prior')
                cls.dags[archive_version] = ProvDAG(
                    str(TEST_DATA[archive_version]['qzv_fp']))

    # This should only trigger if something fails in setup or above
    # e.g. if a ProvDag fails to initialize
    def test_smoke(self):
        self.assertTrue(True)

    def test_terminal_uuid_correct(self):
        for dag_version in self.dags:
            self.assertEqual(len(self.dags[dag_version].terminal_uuids), 1)
            # This is deterministic because there is one uuid in the set:
            terminal_uuid, *_ = self.dags[dag_version].terminal_uuids
            self.assertEqual(terminal_uuid, TEST_DATA[dag_version]['uuid'])

    def test_root_node_is_archive_root(self):
        for dag_version in self.dags:
            with zipfile.ZipFile(TEST_DATA[dag_version]['qzv_fp']) as zf:
                all_filenames = zf.namelist()
                root_md_fnames = filter(is_root_provnode_data, all_filenames)
                root_md_fps = [pathlib.Path(fp) for fp in root_md_fnames]
                exp_node = ProvNode(Config(), zf, root_md_fps)
                self.assertEqual(len(self.dags[dag_version].terminal_uuids), 1)
                # This is deterministic because there is one uuid in the set:
                act_terminal_node, *_ = self.dags[dag_version].terminal_nodes
                self.assertEqual(exp_node, act_terminal_node)

    def test_number_of_actions(self):
        for dag_version in self.dags:
            self.assertEqual(len(self.dags[dag_version]),
                             TEST_DATA[dag_version]['n_res'])

    def test_nonexistent_fp(self):
        fn = 'not_a_filepath.qza'
        fp = os.path.join(DATA_DIR, fn)
        with self.assertRaisesRegex(
            UnparseableDataError,
                f'FileNotFoundError.*ArtifactParser.*{fn}'):
            ProvDAG(fp)

    def test_insufficient_permissions(self):
        fn = 'not_a_zip.txt'
        fp = os.path.join(DATA_DIR, fn)
        # HACK: git can't commit a file with 0 read perms, so...
        os.chmod(fp, 0o000)
        with self.assertRaisesRegex(
            UnparseableDataError,
                f"PermissionError.*ArtifactParser.*denied.*{fn}"):
            ProvDAG(fp)
        os.chmod(fp, 0o644)

    def test_not_a_zip_archive(self):
        fp = os.path.join(DATA_DIR, 'not_a_zip.txt')
        with self.assertRaisesRegex(
            UnparseableDataError,
                "zipfile.BadZipFile.*ArtifactParser.*File is not a zip file"):
            ProvDAG(fp)

    def test_has_digraph(self):
        for dag_version in self.dags:
            self.assertIsInstance(self.dags[dag_version].dag, DiGraph)

    def test_has_nodes(self):
        for dag_version in self.dags:
            self.assertIn(TEST_DATA[dag_version]['uuid'],
                          self.dags[dag_version].nodes)

    def test_dag_attributes(self):
        for vz in self.dags:
            self.assertEqual(len(self.dags[vz].terminal_uuids), 1)
            # This is deterministic because there is one uuid in the set:
            terminal_uuid, *_ = self.dags[vz].terminal_uuids
            self.assertEqual(terminal_uuid,
                             TEST_DATA[vz]['uuid'])
            terminal_node, *_ = self.dags[vz].terminal_nodes
            self.assertEqual(type(terminal_node), ProvNode)
            self.assertEqual(terminal_node.uuid, TEST_DATA[vz]['uuid'])
            self.assertEqual(self.dags[vz].provenance_is_valid,
                             TEST_DATA[vz]['prov_is_valid'])
            self.assertEqual(self.dags[vz].checksum_diff,
                             TEST_DATA[vz]['checksum'])
            self.assertEqual(type(self.dags[vz].nodes), NodeView)
            # Node count acts as a proxy test for completeness here
            self.assertEqual(len(self.dags[vz].nodes), TEST_DATA[vz]['n_res'])
            self.assertEqual(type(self.dags[vz].dag), DiGraph)
            self.assertEqual(len(self.dags[vz]),
                             TEST_DATA[vz]['n_res'])

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
            self.assertRegex(repr(self.dags[dag_vzn]),
                             (f'ProvDAG.*Artifacts.*{uuid}'))

    def test_str(self):
        for dag_vzn in self.dags:
            uuid = TEST_DATA[dag_vzn]['uuid']
            self.assertRegex(repr(self.dags[dag_vzn]),
                             (f'ProvDAG.*Artifacts.*{uuid}'))

    def test_eq_identity(self):
        self.assertEqual(self.dags['5'], self.dags['5'])

    def test_eq_same_origin_data_but_not_identity(self):
        dag_5_rebuilt = ProvDAG(str(TEST_DATA['5']['qzv_fp']))
        self.assertEqual(self.dags['5'], dag_5_rebuilt)

    def test_not_eq(self):
        dag_5_copied = ProvDAG(self.dags['5'])
        self.assertIsNot(dag_5_copied, self.dags['5'])

        # Test same nodes, different types are not equal
        self.assertNotEqual(dag_5_copied, dag_5_copied.dag)

        # Test with different lengths
        dag_5_copied.dag.remove_node(TEST_DATA['5']['uuid'])
        self.assertNotEqual(self.dags['5'], dag_5_copied)

        # Test with same lengths but mismatched nodes
        dag_5_copied.dag.add_node(
            'this_node_is_not_in_the_original_but_satisfies_len_requirement')
        self.assertNotEqual(self.dags['5'], dag_5_copied)

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

    def test_v5_get_outer_provenance_nodes(self):
        exp = {'ffb7cee3-2f1f-4988-90cc-efd5184ef003',
               'bce3d09b-e296-4f2b-9af4-834db6412429',
               '89af91c0-033d-4e30-8ac4-f29a3b407dc1',
               '7ecf8954-e49a-4605-992e-99fcee397935',
               '99fa3670-aa1a-45f6-ba8e-803c976a1163',
               'a35830e1-4535-47c6-aa23-be295a57ee1c',
               }
        root_uuid = TEST_DATA['5']['uuid']
        actual = self.dags['5'].get_outer_provenance_nodes(root_uuid)
        self.assertEqual(actual, exp)

    def test_v5_relabel_nodes(self):
        # This function modifies labels in place, so create a local ProvDAG
        # to protect our test data
        dag = ProvDAG(str(TEST_DATA['5']['qzv_fp']))
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

        # Confirm terminal_uuids state is consistent with the relabeled node
        # names
        print(dag._parsed_artifact_uuids)
        print(dag.terminal_uuids)
        self.assertEqual(len(dag.terminal_uuids), 1)
        # This is deterministic because there is one uuid in the set:
        terminal_uuid, *_ = dag.terminal_uuids
        self.assertEqual(terminal_uuid, exp_nodes[0])

    def test_v5_collapsed_view(self):
        exp_nodes = {'ffb7cee3-2f1f-4988-90cc-efd5184ef003',
                     'bce3d09b-e296-4f2b-9af4-834db6412429',
                     '89af91c0-033d-4e30-8ac4-f29a3b407dc1',
                     '7ecf8954-e49a-4605-992e-99fcee397935',
                     '99fa3670-aa1a-45f6-ba8e-803c976a1163',
                     'a35830e1-4535-47c6-aa23-be295a57ee1c',
                     }
        view = self.dags['5'].collapsed_view
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
                a_dag = ProvDAG(chopped_archive)

            # Have we set provenance_is_valid correctly?
            self.assertEqual(a_dag.provenance_is_valid,
                             ValidationCode.INVALID)

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
                a_dag = ProvDAG(chopped_archive)

            # Have we set provenance_is_valid correctly?
            self.assertEqual(a_dag.provenance_is_valid,
                             ValidationCode.INVALID)

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
                a_dag = ProvDAG(chopped_archive)

            # Have we set provenance_is_valid correctly?
            self.assertEqual(a_dag.provenance_is_valid,
                             ValidationCode.INVALID)

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
                            ProvDAG(chopped_archive)

    def test_mixed_v0_v1_archive(self):
        mixed_archive_fp = os.path.join(DATA_DIR, 'mixed_v0_v1_uu_emperor.qzv')
        v1_uuid = TEST_DATA['1']['uuid']
        v0_uuid = '9f6a0f3e-22e6-4c39-8733-4e672919bbc7'

        with self.assertWarnsRegex(
                UserWarning, f'(:?)Art.*{v0_uuid}.*prior.*incomplete'):
            dag = ProvDAG(mixed_archive_fp)
            self.assertEqual(dag.node_has_provenance(v1_uuid), True)
            self.assertEqual(dag.get_node_data(v1_uuid).uuid, v1_uuid)

            self.assertEqual(dag.node_has_provenance(v0_uuid), False)
            self.assertEqual(dag.get_node_data(v0_uuid), None)

    def test_artifact_passed_as_metadata_archive(self):
        """
        Tests:
        - smoke
        - does the parser find the captured provenance?
        - is the UUID parsed correctly?
        - is the node's type correct? (critical, because we use a dummy type
          when capturing parentage for artifacts passed as metadata. This
          dummy type should never appear in the finished DAG.)
        """
        a_as_md_fp = os.path.join(DATA_DIR, 'artifact_as_md_v5.qzv')
        a_as_md_uuid = 'd1d36ada-29a5-436e-9136-304a8b25ff10'

        dag = ProvDAG(a_as_md_fp)
        self.assertEqual(dag.node_has_provenance(a_as_md_uuid), True)
        self.assertEqual(dag.get_node_data(a_as_md_uuid).uuid, a_as_md_uuid)
        self.assertEqual(dag.get_node_data(a_as_md_uuid).type,
                         'FeatureData[Taxonomy]')

    def test_provdag_initialized_from_a_provdag(self):
        for dag in self.dags.values():
            copied = ProvDAG(dag)
            self.assertEqual(dag, copied)
            self.assertIsNot(dag, copied)


class ProvDAGUnionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """
        Use this when we have a copy-based union, for all tests which copy.
        In-place union will modify any dags we build here, so this is invalid.
        """
        pass

    def test_inplace_union_one(self):
        """
        Tests union of dag with zero other dags.
        """
        dag = ProvDAG(str(TEST_DATA['5']['qzv_fp']))
        v5_uuid = TEST_DATA['5']['uuid']
        og_dag = copy.copy(dag.dag)

        # In-place union
        dag.union([])
        unioned_dag = dag

        self.assertIn(v5_uuid, unioned_dag._parsed_artifact_uuids)
        self.assertEqual(len(unioned_dag._parsed_artifact_uuids), 1)

        self.assertEqual(dag.provenance_is_valid, ValidationCode.VALID)

        self.assertRegex(repr(unioned_dag),
                         f'ProvDAG representing these Artifacts.*{v5_uuid}')

        # There should be one fully-connected tree
        self.assertEqual(
            nx.number_weakly_connected_components(unioned_dag.dag), 1)

        # G == H tests identity of objects in memory, so we need is_isomorphic
        self.assertTrue(nx.is_isomorphic(og_dag, unioned_dag.dag))

    def test_inplace_union_identity(self):
        """
        Tests union of dag with itself.
        """
        dag = ProvDAG(str(TEST_DATA['5']['qzv_fp']))
        og_dag = copy.copy(dag.dag)
        v5_uuid = TEST_DATA['5']['uuid']

        # In-place union
        dag.union([dag])
        unioned_dag = dag

        self.assertIn(v5_uuid, unioned_dag._parsed_artifact_uuids)
        self.assertEqual(len(unioned_dag._parsed_artifact_uuids), 1)

        self.assertEqual(unioned_dag.provenance_is_valid, ValidationCode.VALID)

        self.assertRegex(repr(unioned_dag),
                         f'ProvDAG representing these Artifacts.*{v5_uuid}')

        # There should be one fully-connected tree
        self.assertEqual(
            nx.number_weakly_connected_components(unioned_dag.dag), 1)

        # G == H tests identity of objects in memory, so we need is_isomorphic
        self.assertTrue(nx.is_isomorphic(og_dag, unioned_dag.dag))

    def test_inplace_union_two(self):
        """
        Tests union of dag with another dag.
        Also checks that provenance_is_valid retains the lesser of the
        ValidationCodes from the v4- and v5+ dags.
        """
        v4_dag = ProvDAG(str(TEST_DATA['4']['qzv_fp']))
        v5_dag = ProvDAG(str(TEST_DATA['5']['qzv_fp']))
        v4_uuid = TEST_DATA['4']['uuid']
        v5_uuid = TEST_DATA['5']['uuid']

        # In-place union
        v5_dag.union([v4_dag])
        unioned_dag = v5_dag

        self.assertIn(v4_uuid, unioned_dag._parsed_artifact_uuids)
        self.assertIn(v5_uuid, unioned_dag._parsed_artifact_uuids)
        self.assertEqual(len(unioned_dag._parsed_artifact_uuids), 2)

        self.assertEqual(unioned_dag.provenance_is_valid,
                         ValidationCode.PREDATES_CHECKSUMS)

        rep = repr(unioned_dag)
        self.assertRegex(rep, 'ProvDAG representing these Artifacts {')
        self.assertRegex(rep, f'{v4_uuid}')
        self.assertRegex(rep, f'{v5_uuid}')

        # There should be two disconnected trees
        self.assertEqual(
            nx.number_weakly_connected_components(unioned_dag.dag), 2)

    def test_inplace_union_many(self):
        """
        Tests union of dag with multiple other dags.
        Also checks that we have the correct number of disconnected trees
        (these three dags come from unrelated analyses, so should be disjoint)
        """
        v3_dag = ProvDAG(str(TEST_DATA['3']['qzv_fp']))
        v4_dag = ProvDAG(str(TEST_DATA['4']['qzv_fp']))
        v5_dag = ProvDAG(str(TEST_DATA['5']['qzv_fp']))
        v3_uuid = TEST_DATA['3']['uuid']
        v4_uuid = TEST_DATA['4']['uuid']
        v5_uuid = TEST_DATA['5']['uuid']

        # In-place union
        v5_dag.union([v4_dag, v3_dag])
        unioned_dag = v5_dag

        self.assertIn(v3_uuid, unioned_dag._parsed_artifact_uuids)
        self.assertIn(v4_uuid, unioned_dag._parsed_artifact_uuids)
        self.assertIn(v5_uuid, unioned_dag._parsed_artifact_uuids)
        self.assertEqual(len(unioned_dag._parsed_artifact_uuids), 3)

        self.assertEqual(unioned_dag.provenance_is_valid,
                         ValidationCode.PREDATES_CHECKSUMS)

        rep = repr(unioned_dag)
        self.assertRegex(rep, 'ProvDAG representing these Artifacts {')
        self.assertRegex(rep, f'{v3_uuid}')
        self.assertRegex(rep, f'{v4_uuid}')
        self.assertRegex(rep, f'{v5_uuid}')

        # There should be three disconnected trees
        self.assertEqual(
            nx.number_weakly_connected_components(unioned_dag.dag), 3)

    def test_union_self_missing_checksums_md5(self):
        """
        Tests unions of v5 dags where the calling ProvDAG is missing its
        checksums.md5 but the other is not

        TODO: Consolidate the following tests once we can copy-union.
        """
        drop_file = pathlib.Path('checksums.md5')
        with generate_archive_with_file_removed(
            qzv_fp=TEST_DATA['5']['qzv_fp'],
            root_uuid=TEST_DATA['5']['uuid'],
                file_to_drop=drop_file) as chopped_archive:
            with self.assertWarnsRegex(UserWarning, 'no item.*checksums'):
                bad_dag = ProvDAG(chopped_archive)

        good_dag = ProvDAG(str(TEST_DATA['5']['qzv_fp']))
        v5_uuid = TEST_DATA['5']['uuid']

        # In-place union
        bad_dag.union([good_dag])
        unioned_dag = bad_dag

        self.assertRegex(repr(unioned_dag),
                         f'ProvDAG representing these Artifacts.*{v5_uuid}')

        # The ChecksumDiff==None from the tinkered dag gets ignored...
        self.assertEqual(unioned_dag.checksum_diff, ChecksumDiff({}, {}, {}))

        # ...but this should make clear that the provenance is bad
        # (or that the user opted out of validation).
        self.assertEqual(unioned_dag.provenance_is_valid,
                         ValidationCode.INVALID)

        # There should be one fully-connected tree
        self.assertEqual(
            nx.number_weakly_connected_components(unioned_dag.dag), 1)

    def test_union_other_missing_checksums_md5(self):
        """
        Tests unions of v5 dags where the other ProvDAG is missing its
        checksums.md5 but the calling ProvDAG is not
        """
        drop_file = pathlib.Path('checksums.md5')
        with generate_archive_with_file_removed(
            qzv_fp=TEST_DATA['5']['qzv_fp'],
            root_uuid=TEST_DATA['5']['uuid'],
                file_to_drop=drop_file) as chopped_archive:
            with self.assertWarnsRegex(UserWarning, 'no item.*checksums'):
                bad_dag = ProvDAG(chopped_archive)

        good_dag = ProvDAG(str(TEST_DATA['5']['qzv_fp']))
        v5_uuid = TEST_DATA['5']['uuid']

        # In-place union
        good_dag.union([bad_dag])
        unioned_dag = good_dag

        self.assertRegex(repr(unioned_dag),
                         f'ProvDAG representing these Artifacts.*{v5_uuid}')

        # The ChecksumDiff==None from the tinkered dag gets ignored...
        self.assertEqual(unioned_dag.checksum_diff, ChecksumDiff({}, {}, {}))

        # ...but this should make clear that the provenance is bad
        # (or that the user opted out of validation).
        self.assertEqual(unioned_dag.provenance_is_valid,
                         ValidationCode.INVALID)

        # There should be one fully-connected tree
        self.assertEqual(
            nx.number_weakly_connected_components(unioned_dag.dag), 1)

    def test_union_both_missing_checksums_md5(self):
        """
        Tests unions of v5 dags where both artifacts are missing their
        checksums.md5 files.
        """
        drop_file = pathlib.Path('checksums.md5')
        with generate_archive_with_file_removed(
            qzv_fp=TEST_DATA['5']['qzv_fp'],
            root_uuid=TEST_DATA['5']['uuid'],
                file_to_drop=drop_file) as chopped_archive:
            with self.assertWarnsRegex(UserWarning, 'no item.*checksums'):
                bad_dag = ProvDAG(chopped_archive)

        v5_uuid = TEST_DATA['5']['uuid']

        # In-place union
        bad_dag.union([bad_dag])
        unioned_dag = bad_dag

        self.assertRegex(repr(unioned_dag),
                         f'ProvDAG representing these Artifacts.*{v5_uuid}')

        # Both DAGs have NoneType checksum_diffs, so the ChecksumDiff==None
        self.assertEqual(unioned_dag.checksum_diff, None)
        self.assertEqual(unioned_dag.provenance_is_valid,
                         ValidationCode.INVALID)

        # There should be one fully-connected tree
        self.assertEqual(
            nx.number_weakly_connected_components(unioned_dag.dag), 1)

    def test_one_dag_is_true_superset(self):
        """
        Tests union of three dags, where one dag is a true superset of the
        others. We expect three _parsed_artifact_uuids, one terminal uuid,
        and one weakly_connected_component.
        """
        v5_qzv = ProvDAG(str(TEST_DATA['5']['qzv_fp']))
        qzv_dag = copy.copy(v5_qzv.dag)
        v5_table = ProvDAG(os.path.join(DATA_DIR, 'v5_table.qza'))
        v5_tree = ProvDAG(os.path.join(DATA_DIR, 'v5_rooted_tree.qza'))
        qzv_uuid = TEST_DATA['5']['uuid']
        table_uuid = '89af91c0-033d-4e30-8ac4-f29a3b407dc1'
        tree_uuid = 'bce3d09b-e296-4f2b-9af4-834db6412429'

        # In-place union
        v5_qzv.union([v5_table, v5_tree])
        unioned_dag = v5_qzv

        self.assertIn(qzv_uuid, unioned_dag._parsed_artifact_uuids)
        self.assertIn(table_uuid, unioned_dag._parsed_artifact_uuids)
        self.assertIn(tree_uuid, unioned_dag._parsed_artifact_uuids)
        self.assertEqual(len(unioned_dag._parsed_artifact_uuids), 3)

        self.assertEqual(len(unioned_dag.terminal_uuids), 1)
        self.assertEqual(unioned_dag.terminal_uuids, {qzv_uuid})

        self.assertEqual(
            nx.number_weakly_connected_components(unioned_dag.dag), 1)

        # G == H tests identity of objects in memory, so we need is_isomorphic
        self.assertTrue(nx.is_isomorphic(qzv_dag, unioned_dag.dag))

    def test_three_artifacts_two_terminal_uuids(self):
        """
        Tests union of three dags, where the v5_qzv is downstream of the table,
        but not downstream of the unrooted tree. We expect three
        _parsed_artifact_uuids, two terminal uuids, and one
        weakly_connected_component.
        """
        v5_qzv = ProvDAG(str(TEST_DATA['5']['qzv_fp']))
        v5_table = ProvDAG(os.path.join(DATA_DIR, 'v5_table.qza'))
        v5_unr_tree = ProvDAG(os.path.join(DATA_DIR, 'v5_unrooted_tree.qza'))
        qzv_uuid = TEST_DATA['5']['uuid']
        table_uuid = '89af91c0-033d-4e30-8ac4-f29a3b407dc1'
        tree_uuid = '12e012d5-b01c-40b7-b825-a17f0478a02f'

        # In-place union
        v5_qzv.union([v5_table, v5_unr_tree])
        unioned_dag = v5_qzv

        self.assertIn(qzv_uuid, unioned_dag._parsed_artifact_uuids)
        self.assertIn(table_uuid, unioned_dag._parsed_artifact_uuids)
        self.assertIn(tree_uuid, unioned_dag._parsed_artifact_uuids)
        self.assertEqual(len(unioned_dag._parsed_artifact_uuids), 3)

        self.assertEqual(len(unioned_dag.terminal_uuids), 2)
        self.assertEqual(unioned_dag.terminal_uuids,
                         set([qzv_uuid, tree_uuid]))

        self.assertEqual(
            nx.number_weakly_connected_components(unioned_dag.dag), 1)

    def test_graphs_same_analysis_missing_artifacts(self):
        """
        In this set of test archives, both .qzvs are derived from the same
        feature table, so should produce one connected DAG even though we are
        missing the rarefied_table.qza used to create the rarefied_table.qzv
        """
        v5_qzv = ProvDAG(str(TEST_DATA['5']['qzv_fp']))
        v5_table = ProvDAG(os.path.join(DATA_DIR, 'v5_table.qza'))
        rar_qzv = ProvDAG(os.path.join(DATA_DIR, 'v5_rarefied_table.qzv'))
        qzv_uuid = TEST_DATA['5']['uuid']
        table_uuid = '89af91c0-033d-4e30-8ac4-f29a3b407dc1'
        rar_uuid = '79a0d2ea-ea01-40c0-a4a4-0beab7c1f244'

        # In-place union
        v5_qzv.union([v5_table, rar_qzv])
        unioned_dag = v5_qzv

        self.assertIn(qzv_uuid, unioned_dag._parsed_artifact_uuids)
        self.assertIn(table_uuid, unioned_dag._parsed_artifact_uuids)
        self.assertIn(rar_uuid, unioned_dag._parsed_artifact_uuids)
        self.assertEqual(len(unioned_dag._parsed_artifact_uuids), 3)

        self.assertEqual(len(unioned_dag.terminal_uuids), 2)
        self.assertEqual(unioned_dag.terminal_uuids, {qzv_uuid, rar_uuid})

        self.assertEqual(
            nx.number_weakly_connected_components(unioned_dag.dag), 1)


class ProvDAGTestsNoChecksumValidation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.no_checksum_dags = dict()
        for archive_version in TEST_DATA:
            # supress warning from parsing provenance for a v0 provDag
            uuid = TEST_DATA['0']['uuid']
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore',  f'Art.*{uuid}.*prior')
                cls.no_checksum_dags[archive_version] = ProvDAG(
                    str(TEST_DATA[archive_version]['qzv_fp']),
                    cfg=Config(perform_checksum_validation=False))

    # This should only trigger if something fails in setup or above
    # e.g. if a ProvDag fails to initialize
    def test_smoke(self):
        self.assertTrue(True)

    def test_no_checksum_validation_on_intact_artifact(self):
        dags = self.no_checksum_dags
        for vz in dags:
            self.assertEqual(len(dags[vz].terminal_uuids), 1)
            # This is deterministic because there is one uuid in the set:
            terminal_uuid, *_ = dags[vz].terminal_uuids
            self.assertEqual(terminal_uuid,
                             TEST_DATA[vz]['uuid'])
            # Node count acts as a proxy test for completeness here
            self.assertEqual(len(dags[vz]),
                             TEST_DATA[vz]['n_res'])
            self.assertEqual(dags[vz].provenance_is_valid,
                             ValidationCode.VALIDATION_OPTOUT)
            self.assertEqual(dags[vz].checksum_diff, None)

    def test_no_checksum_missing_checksums_md5(self):
        drop_file = pathlib.Path('checksums.md5')
        with generate_archive_with_file_removed(
            qzv_fp=TEST_DATA['5']['qzv_fp'],
            root_uuid=TEST_DATA['5']['uuid'],
                file_to_drop=drop_file) as chopped_archive:

            a_dag = ProvDAG(chopped_archive,
                            cfg=Config(perform_checksum_validation=False))

            # Have we set provenance_is_valid correctly?
            self.assertEqual(
                a_dag.provenance_is_valid, ValidationCode.VALIDATION_OPTOUT)

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
                        ProvDAG(chopped_archive,
                                cfg=Config(perform_checksum_validation=False))


class ProvDAGParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # TODO: If we make a module-global set of dags, we can replace this
        # with test_get_parser
        cls.dags = dict()
        for archive_version in TEST_DATA:
            # supress warning from parsing provenance for a v0 provDag
            uuid = TEST_DATA['0']['uuid']
            with warnings.catch_warnings():
                warnings.filterwarnings('ignore',  f'Art.*{uuid}.*prior')
                cls.dags[archive_version] = ProvDAG(
                    str(TEST_DATA[archive_version]['qzv_fp']))

    def test_get_parser(self):
        for version in TEST_DATA:
            parser = ProvDAGParser.get_parser(self.dags[version])
            self.assertIsInstance(parser, ProvDAGParser)

    def test_get_parser_input_data_not_a_provdag(self):
        fn = 'not_a_zip.txt'
        fp = os.path.join(DATA_DIR, fn)
        with self.assertRaisesRegex(
                TypeError, f"ProvDAGParser.*{fn} is not a ProvDAG"):
            ProvDAGParser.get_parser(fp)

    def test_parse_a_provdag(self):
        parser = ProvDAGParser()
        for dag in self.dags.values():
            parsed = parser.parse_prov(Config(), dag)
            self.assertIsInstance(parsed, ParserResults)
            self.assertEqual(parsed.parsed_artifact_uuids,
                             dag._parsed_artifact_uuids)
            # NOTE: networkx thinks about graph equality in terms of object
            # identity. Because this parser creates a deep copy of pdag,
            # we must use nx.is_isomorphic to confirm "equality"
            self.assertTrue(nx.is_isomorphic(parsed.prov_digraph, dag.dag))
            self.assertEqual(parsed.provenance_is_valid,
                             dag.provenance_is_valid)
            self.assertEqual(parsed.checksum_diff, dag.checksum_diff)


class ParserDispatcherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = Config()

    # Can we make a ParserDispatcher without anything blowing up?
    def test_smoke(self):
        for arch_ver in TEST_DATA:
            qzv_fp = TEST_DATA[arch_ver]['qzv_fp']
            ParserDispatcher(self.cfg, qzv_fp)
        self.assertTrue(True)

    # TODO NEXT These tests
    # TODO: Rename to test_correct_format_version?
    def test_correct_parser(self):
        for arch_ver in TEST_DATA:
            qzv_fp = TEST_DATA[arch_ver]['qzv_fp']
            handler = ParserDispatcher(self.cfg, qzv_fp)
            self.assertIsInstance(handler.parser,
                                  TEST_DATA[arch_ver]['parser'])

    def test_correct_parser_type(self):
        # Confirm we're getting ProvDAGParser v ArtifactParser
        # Import the types first
        pass

    def test_parse_with_provdag_parser(self):
        pass

    def test_parse_with_artifact_parser(self):
        uuid = TEST_DATA['5']['uuid']
        qzv_fp = TEST_DATA['5']['qzv_fp']
        handler = ParserDispatcher(self.cfg, qzv_fp)
        parser_results = handler.parse(qzv_fp)
        self.assertIsInstance(parser_results, ParserResults)
        p_a_uuids = parser_results.parsed_artifact_uuids
        self.assertIsInstance(p_a_uuids, set)
        self.assertIsInstance(next(iter(p_a_uuids)), UUID)
        self.assertEqual(len(parser_results.prov_digraph), 15)
        self.assertIn(uuid, parser_results.prov_digraph)
        self.assertIsInstance(
            parser_results.prov_digraph.nodes[uuid]['node_data'],
            ProvNode)
        self.assertEqual(parser_results.provenance_is_valid,
                         TEST_DATA['5']['prov_is_valid'])
        self.assertEqual(parser_results.checksum_diff,
                         TEST_DATA['5']['checksum'])

    def test_no_correct_parser_found_error(self):
        """
        Nothing blows up here, it's just not the right kind of filepath
        e.g. not a zipfile?
        """

    def test_error_from_one_parser(self):
        pass

    def test_error_from_two_parsers(self):
        pass
