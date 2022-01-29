import networkx as nx
import os
import unittest

from qiime2 import Artifact
from qiime2.sdk import PluginManager
from qiime2.sdk.usage import Usage, UsageVariable

from ..parse import ProvDAG
from ..replay import (
    camel_to_snake, group_by_action, UsageVarsDict, uniquify_action_name)
from .test_parse import DATA_DIR, TEST_DATA

# Create a PM Instance once and use it throughout - expensive!
pm = PluginManager()


class UsageVarsDictTests(unittest.TestCase):
    def test_uniquify(self):
        collision_val = 'emp_single_end_sequences'
        unique_val = 'some_prime'
        ns = UsageVarsDict({'123': collision_val})
        self.assertEqual(ns.data, {'123': 'emp_single_end_sequences_0'})

        # We can update w/ multiple values. Also, if the same value has been
        # repatedly added to the namespace, we expect n to increment each time.
        ns.update({'456': collision_val, 'unique': unique_val})
        self.assertEqual(ns['456'], 'emp_single_end_sequences_1')
        self.assertEqual(ns['unique'], 'some_prime_0')
        ns['789'] = collision_val
        self.assertEqual(ns.pop('789'), 'emp_single_end_sequences_2')

    def test_add_usage_var_flow(self):
        """
        Smoke tests a common workflow with this data structure
        - Create a unique variable name by adding to dict
        - Create a UsageVariable with that name
        - use the name to get the UUID (when we have Results, we have no UUIDs)
        - Replace the name with the correctly-named UsageVariable
        """
        use = Usage()
        uuid = '89af91c0-033d-4e30-8ac4-f29a3b407dc1'
        base_name = 'v5_table'
        exp_name = base_name + '_0'
        ns = UsageVarsDict({uuid: base_name})
        self.assertEqual(ns[uuid], exp_name)

        def factory():
            # TODO: Pytest-cov thinks this lil dude is not executed. ???
            return Artifact.load(os.path.join(DATA_DIR, 'v5_table.qza'))
        u_var = use.init_artifact(ns[uuid], factory)
        self.assertEqual(u_var.name, exp_name)

        actual_uuid = ns.get_key(u_var.name)
        self.assertEqual(actual_uuid, uuid)

        ns[uuid] = u_var
        self.assertIsInstance(ns[uuid], UsageVariable)
        self.assertEqual(ns[uuid].name, exp_name)

    def test_get_key(self):
        ns = UsageVarsDict({'123': 'some_name'})
        # some_name is uniquified to some_name_0
        self.assertEqual('123', ns.get_key('some_name_0'))
        with self.assertRaisesRegex(KeyError,
                                    "passed value 'fake_key' does not exist"):
            ns.get_key('fake_key')


class MiscHelperFnTests(unittest.TestCase):
    def test_camel_to_snake(self):
        some_types_n_formats = [
            'Hierarchy',  # simple
            'DistanceMatrix',  # compound
            'Bowtie2Index',  # compound w numeral
            'EMPPairedEndSequences',  # acronym
            'BIOMV210DirFmt',  # acronym w numeral
            'PCoAResults',  # weird acronym
            'PairedEndFastqManifestPhred64V2',  # compound with acronym and num
            'SampleData[Sequences]',  # bracket notation
            'FeatureData[BLAST6]',  # bracket with acronym and numeral
            'SampleData[DADA2Stats]',  # bracket complex acronym
            'FeatureData[AlignedRNASequence]',  # bracket complex acronym
            'List[FeatureTable[RelativeFrequency]]',  # made-up nested example
        ]
        exp = [
            'hierarchy',
            'distance_matrix',
            'bowtie2_index',
            'emp_paired_end_sequences',
            'biomv210_dir_fmt',
            'p_co_a_results',
            'paired_end_fastq_manifest_phred64_v2',
            'sample_data_sequences',
            'feature_data_blast6',
            'sample_data_dada2_stats',
            'feature_data_aligned_rna_sequence',
            'list_feature_table_relative_frequency',  # made-up nested example
        ]
        for og_str, exp_str in zip(some_types_n_formats, exp):
            print(og_str, exp_str)
            self.assertEqual(camel_to_snake(og_str), exp_str)

    def test_uniquify_action_name(self):
        ns = set()
        p1 = 'dummy_plugin'
        a1 = 'action_jackson'
        p2 = 'dummy_plugin'
        a2 = 'missing_in_action'
        unique1 = uniquify_action_name(p1, a1, ns)
        self.assertEqual(unique1, 'dummy_plugin_action_jackson_0')
        unique2 = uniquify_action_name(p2, a2, ns)
        self.assertEqual(unique2, 'dummy_plugin_missing_in_action_0')
        duplicate = uniquify_action_name(p1, a1, ns)
        self.assertEqual(duplicate, 'dummy_plugin_action_jackson_1')
        print(unique1, unique2, duplicate)

    def test_group_by_action_w_provenance(self):
        self.maxDiff = None
        v5_dag = ProvDAG(str(TEST_DATA['5']['qzv_fp']))
        sorted_nodes = nx.topological_sort(v5_dag.collapsed_view)
        actual = group_by_action(v5_dag, sorted_nodes)
        exp = {
            '5cf3fd87-22ac-47ea-936d-576cc12f9110':
                {'a35830e1-4535-47c6-aa23-be295a57ee1c':
                    'emp_single_end_sequences', },
            '3d69c8d1-a1fa-4ab3-ac88-3a98da15b2d5':
                {'99fa3670-aa1a-45f6-ba8e-803c976a1163':
                    'per_sample_sequences', },
            'c0f74c1c-d596-4b1b-9aad-50101b4a9950':
                {'89af91c0-033d-4e30-8ac4-f29a3b407dc1': 'table',
                 '7ecf8954-e49a-4605-992e-99fcee397935':
                    'representative_sequences', },
            '4779bf7d-cae8-4ff2-a27d-4c97f581803f':
                {'bce3d09b-e296-4f2b-9af4-834db6412429': 'rooted_tree', },
            'aefba6e7-3dd1-45e5-8e6b-60e784062a5e':
                {'ffb7cee3-2f1f-4988-90cc-efd5184ef003':
                    'unweighted_unifrac_emperor', },
        }
        self.assertEqual(actual, exp)

    def test_group_by_action_no_provenance(self):
        # TODO: NEXT
        raise NotImplementedError
