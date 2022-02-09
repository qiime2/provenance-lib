import bibtexparser as bp
import networkx as nx
import os
import pandas as pd
import pathlib
import re
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from qiime2 import Artifact
from qiime2.sdk import PluginManager
from qiime2.sdk.usage import Usage, UsageVariable
from q2cli.core.usage import CLIUsageVariable
from qiime2.plugins import ArtifactAPIUsageVariable

from ..parse import ProvDAG
from ..replay import (
    ActionCollections, ReplayConfig, UsageVarsDict, SUPPORTED_USAGE_DRIVERS,
    build_no_provenance_node_usage, build_import_usage, build_action_usage,
    build_usage_examples, camel_to_snake, collect_citations, dedupe_citations,
    dump_recorded_md_file, group_by_action, init_md_from_artifacts,
    init_md_from_md_file, init_md_from_recorded_md, param_is_metadata_column,
    replay_fp, replay_provdag, uniquify_action_name, write_citations,
    )
from .test_parse import DATA_DIR, TEST_DATA
from .testing_utilities import CustomAssertions
from ..yaml_constructors import MetadataInfo

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

        def factory():  # pragma: no cover
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


class ReplayFPTests(unittest.TestCase):
    def test_replay_fp(self):
        in_fn = TEST_DATA['5']['qzv_fp']
        with tempfile.TemporaryDirectory() as tmpdir:
            out_fp = pathlib.Path(tmpdir) / 'rendered.txt'
            out_fn = str(out_fp)
            replay_fp(in_fn, out_fn, 'python3')

            self.assertTrue(out_fp.is_file())

            with open(out_fn, 'r') as fp:
                rendered = fp.read()
            self.assertIn('from qiime2 import Artifact', rendered)
            self.assertIn('from qiime2 import Metadata', rendered)
            self.assertIn(
                'import qiime2.plugins.dada2.actions as dada2_actions',
                rendered)
            self.assertIn('emp_single_end_sequences_0 = Artifact.import_data(',
                          rendered)

            self.assertRegex(rendered,
                             'The following command.*additional metadata')
            self.assertIn('barcodes_0_md = Metadata.load', rendered)
            self.assertIn('barcodes_0_md.get_column(', rendered)
            self.assertIn('dada2_actions.denoise_single', rendered)
            self.assertIn('phylogeny_actions.align_to_tree_mafft_fasttree',
                          rendered)
            self.assertIn('diversity_actions.core_metrics_phylogenetic',
                          rendered)

    def test_replay_fp_use_md_without_parse(self):
        in_fp = TEST_DATA['5']['qzv_fp']
        with self.assertRaisesRegex(
                ValueError, "Metadata not parsed for replay. Re-run"):
            replay_fp(in_fp, 'unused_fp', 'python3',
                      parse_metadata=False, use_recorded_metadata=True)


class ReplayProvDAGTests(unittest.TestCase):
    def test_replay_provdag(self):
        v5_dag = ProvDAG(TEST_DATA['5']['qzv_fp'])
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = pathlib.Path(tmpdir) / 'rendered.txt'
            replay_provdag(v5_dag, out_path, 'python3')

            self.assertTrue(out_path.is_file())

            with open(out_path, 'r') as fp:
                rendered = fp.read()
            self.assertIn('from qiime2 import Artifact', rendered)
            self.assertIn('from qiime2 import Metadata', rendered)
            self.assertIn(
                'import qiime2.plugins.dada2.actions as dada2_actions',
                rendered)
            self.assertIn('emp_single_end_sequences_0 = Artifact.import_data(',
                          rendered)

            self.assertRegex(rendered,
                             'The following command.*additional metadata')
            self.assertIn('barcodes_0_md = Metadata.load', rendered)
            self.assertIn('barcodes_0_md.get_column(', rendered)
            self.assertIn('dada2_actions.denoise_single', rendered)
            self.assertIn('phylogeny_actions.align_to_tree_mafft_fasttree',
                          rendered)
            self.assertIn('diversity_actions.core_metrics_phylogenetic',
                          rendered)

    def test_replay_provdag_use_md_without_parse(self):
        v5_dag = ProvDAG(TEST_DATA['5']['qzv_fp'],
                         validate_checksums=False,
                         parse_metadata=False)
        with self.assertRaisesRegex(
                ValueError, "Metadata not captured for replay"):
            replay_provdag(v5_dag, 'unused', 'python3',
                           use_recorded_metadata=True)


class BuildUsageExamplesTests(unittest.TestCase):
    @patch('provenance_lib.replay.build_action_usage')
    @patch('provenance_lib.replay.build_import_usage')
    @patch('provenance_lib.replay.build_no_provenance_node_usage')
    def test_build_usage_examples(self, n_p_builder, imp_builder, act_builder):
        v5_dag = ProvDAG(TEST_DATA['5']['qzv_fp'])
        cfg = ReplayConfig(use=SUPPORTED_USAGE_DRIVERS['python3'](),
                           use_recorded_metadata=False, pm=pm)
        build_usage_examples(v5_dag, cfg)
        # This is an intact v5 dag, with one import and four following actions
        n_p_builder.assert_not_called()
        imp_builder.assert_called_once()
        self.assertEqual(act_builder.call_count, 4)

    @patch('provenance_lib.replay.build_action_usage')
    @patch('provenance_lib.replay.build_import_usage')
    @patch('provenance_lib.replay.build_no_provenance_node_usage')
    def test_build_usage_examples_lone_v0(
            self, n_p_builder, imp_builder, act_builder):
        v0_uuid = '0b8b47bd-f2f8-4029-923c-0e37a68340c3'
        with self.assertWarnsRegex(
                UserWarning, f'(:?)Art.*{v0_uuid}.*prior.*incomplete'):
            v0_dag = ProvDAG(TEST_DATA['0']['qzv_fp'])
        cfg = ReplayConfig(use=SUPPORTED_USAGE_DRIVERS['python3'](),
                           use_recorded_metadata=False, pm=pm)
        build_usage_examples(v0_dag, cfg)
        # This is a single v0 archive, so should have only one np node
        n_p_builder.assert_called_once()
        imp_builder.assert_not_called()
        act_builder.assert_not_called()

    @patch('provenance_lib.replay.build_action_usage')
    @patch('provenance_lib.replay.build_import_usage')
    @patch('provenance_lib.replay.build_no_provenance_node_usage')
    def test_build_usage_examples_joined_v0s(
            self, n_p_builder, imp_builder, act_builder):
        cfg = ReplayConfig(use=SUPPORTED_USAGE_DRIVERS['python3'](),
                           use_recorded_metadata=False, pm=pm)

        # Multiple no-prov nodes glued together into a single DAG
        v0_uuid = '0b8b47bd-f2f8-4029-923c-0e37a68340c3'
        with self.assertWarnsRegex(
                UserWarning, f'(:?)Art.*{v0_uuid}.*prior.*incomplete'):
            single_no_prov = ProvDAG(os.path.join(DATA_DIR,
                                     'v0_uu_emperor.qzv'))

        tbl_uuid = '89af91c0-033d-4e30-8ac4-f29a3b407dc1'
        with self.assertWarnsRegex(
                UserWarning, f'(:?)Art.*{tbl_uuid}.*prior.*incomplete'):
            v0_tbl = ProvDAG(os.path.join(DATA_DIR, 'v0_table.qza'))
        joined = ProvDAG.union([single_no_prov, v0_tbl])

        build_usage_examples(joined, cfg)
        # This is a pair of v0 archives, so should have two np nodes
        self.assertEqual(n_p_builder.call_count, 2)
        imp_builder.assert_not_called()
        act_builder.assert_not_called()

    @patch('provenance_lib.replay.build_action_usage')
    @patch('provenance_lib.replay.build_import_usage')
    @patch('provenance_lib.replay.build_no_provenance_node_usage')
    def test_build_usage_examples_mixed(
            self, n_p_builder, imp_builder, act_builder):
        mixed_uuid = '9f6a0f3e-22e6-4c39-8733-4e672919bbc7'
        with self.assertWarnsRegex(
                UserWarning, f'(:?)Art.*{mixed_uuid}.*prior.*incomplete'):
            mixed = ProvDAG(os.path.join(DATA_DIR,
                            'mixed_v0_v1_uu_emperor.qzv'))
        cfg = ReplayConfig(use=SUPPORTED_USAGE_DRIVERS['python3'](),
                           use_recorded_metadata=False, pm=pm)
        build_usage_examples(mixed, cfg)
        # This is a mixed v0, v1 archive, so no imports but np and action
        n_p_builder.assert_called_once()
        imp_builder.assert_not_called()
        act_builder.assert_called_once()

    @patch('provenance_lib.replay.build_action_usage')
    @patch('provenance_lib.replay.build_import_usage')
    @patch('provenance_lib.replay.build_no_provenance_node_usage')
    def test_build_usage_examples_big(
            self, n_p_builder, imp_builder, act_builder):
        big = ProvDAG(os.path.join(DATA_DIR, 'artifact_as_md_v5.qzv'))
        cfg = ReplayConfig(use=SUPPORTED_USAGE_DRIVERS['python3'](),
                           use_recorded_metadata=False, pm=pm)
        build_usage_examples(big, cfg)
        # This is a fairly large empress plot with multiple imports
        n_p_builder.assert_not_called()
        self.assertEqual(imp_builder.call_count, 3)
        self.assertEqual(act_builder.call_count, 7)


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

    def test_param_is_metadata_col(self):
        """
        Assumes q2-demux and q2-diversity are installed in the active env.
        TODO: replace with dummy plugin if we integrate this into the framework
        """
        cfg = ReplayConfig(use=SUPPORTED_USAGE_DRIVERS['cli'](),
                           use_recorded_metadata=False, pm=pm)
        # Is a MDC
        actual = param_is_metadata_column(
            cfg, 'barcodes', 'demux', 'emp_single')
        self.assertTrue(actual)

        # Isn't an MDC
        not_md = param_is_metadata_column(
            cfg, 'custom_axes', 'emperor', 'plot')
        self.assertFalse(not_md)

        # Action doesn't exist
        with self.assertRaisesRegex(KeyError, "No param.*registered.*fake"):
            param_is_metadata_column(
                cfg, 'fake_param', 'emperor', 'plot')

        # Parameter doesn't exist
        with self.assertRaisesRegex(KeyError, "No action.*registered.*fake"):
            param_is_metadata_column(
                cfg, 'custom_axes', 'emperor', 'fake_action')

        # Plugin doesn't exist
        with self.assertRaisesRegex(KeyError, "No plugin.*registered.*prince"):
            param_is_metadata_column(
                cfg, 'custom_axes', 'princeling', 'plot')

    def test_dump_recorded_md_file(self):
        mixed_uuid = '9f6a0f3e-22e6-4c39-8733-4e672919bbc7'
        with self.assertWarnsRegex(
                UserWarning, f'(:?)Art.*{mixed_uuid}.*prior.*incomplete'):
            mixed = ProvDAG(os.path.join(DATA_DIR,
                                         'mixed_v0_v1_uu_emperor.qzv'))
        root_uuid = '0b8b47bd-f2f8-4029-923c-0e37a68340c3'
        out_dir = 'recorded_metadata'
        provnode = mixed.get_node_data(root_uuid)
        og_md = provnode.metadata['metadata']
        act_nm = 'emperor_plot_0'
        md_id = 'metadata'
        fn = 'metadata_0.tsv'

        with tempfile.TemporaryDirectory() as tmpdir:
            pathlib.Path.cwd = MagicMock(return_value=pathlib.Path(tmpdir))
            dump_recorded_md_file(provnode, act_nm, md_id, fn)
            out_path = pathlib.Path(tmpdir) / out_dir / act_nm / fn

            # was the file written where expected?
            self.assertTrue(out_path.is_file())

            # is it the same df?
            dumped_df = pd.read_csv(out_path, sep='\t')
            pd.testing.assert_frame_equal(dumped_df, og_md)

            # If we run it again, it shouldn't overwrite 'recorded_metadata',
            # so we should have two files
            act_nm2 = 'emperor_plot_1'
            md_id2 = 'metadata'
            fn2 = 'metadata_1.tsv'
            dump_recorded_md_file(provnode, act_nm2, md_id2, fn2)
            out_path2 = pathlib.Path(tmpdir) / out_dir / act_nm2 / fn2

            # are both files where expected?
            self.assertTrue(out_path.is_file())
            self.assertTrue(out_path2.is_file())

    def test_dump_recorded_md_file_no_md(self):
        # V0 archives never have metadata
        v0_uuid = '0b8b47bd-f2f8-4029-923c-0e37a68340c3'
        with self.assertWarnsRegex(
                UserWarning, f'(:?)Art.*{v0_uuid}.*prior.*incomplete'):
            v0 = ProvDAG(os.path.join(DATA_DIR, 'v0_uu_emperor.qzv'))
        root_uuid = '0b8b47bd-f2f8-4029-923c-0e37a68340c3'
        provnode = v0.get_node_data(root_uuid)
        act_nm = 'emperor_plot_0'
        md_id = 'metadata'
        fn = 'metadata_0.tsv'

        with self.assertRaisesRegex(ValueError,
                                    "should only be called.*if.*metadata"):
            dump_recorded_md_file(provnode, act_nm, md_id, fn)


class GroupByActionTests(unittest.TestCase):
    def test_g_b_a_w_provenance(self):
        self.maxDiff = None
        v5_dag = ProvDAG(TEST_DATA['5']['qzv_fp'])
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
        self.assertEqual(actual.std_actions, exp)
        self.assertEqual(actual.no_provenance_nodes, [])

    def test_g_b_a_no_provenance(self):
        # one v0 node
        v0_uuid = '0b8b47bd-f2f8-4029-923c-0e37a68340c3'
        with self.assertWarnsRegex(
                UserWarning, f'(:?)Art.*{v0_uuid}.*prior.*incomplete'):
            single_no_prov = ProvDAG(
                os.path.join(DATA_DIR, 'v0_uu_emperor.qzv'))
        sorted_nodes = nx.topological_sort(single_no_prov.collapsed_view)
        action_collections = group_by_action(single_no_prov, sorted_nodes)
        self.assertEqual(action_collections.std_actions, {})
        self.assertEqual(action_collections.no_provenance_nodes, [v0_uuid])

    def test_g_b_a_two_joined_no_prov_nodes(self):
        # Multiple no-prov nodes glued together into a single DAG
        v0_uuid = '0b8b47bd-f2f8-4029-923c-0e37a68340c3'
        with self.assertWarnsRegex(
                UserWarning, f'(:?)Art.*{v0_uuid}.*prior.*incomplete'):
            single_no_prov = ProvDAG(os.path.join(DATA_DIR,
                                     'v0_uu_emperor.qzv'))

        tbl_uuid = '89af91c0-033d-4e30-8ac4-f29a3b407dc1'
        with self.assertWarnsRegex(
                UserWarning, f'(:?)Art.*{tbl_uuid}.*prior.*incomplete'):
            v0_tbl = ProvDAG(os.path.join(DATA_DIR, 'v0_table.qza'))
        joined = ProvDAG.union([single_no_prov, v0_tbl])
        sorted_nodes = nx.topological_sort(joined.collapsed_view)
        action_collections = group_by_action(joined, sorted_nodes)
        self.assertEqual(action_collections.std_actions, {})
        self.assertEqual(action_collections.no_provenance_nodes,
                         [v0_uuid, tbl_uuid])

    def test_g_b_a_some_nodes_missing_provenance(self):
        # A dag parsed from a v1 archive with a v0 predecessor node
        act_id = 'c147dfbc-139a-4db0-ac17-b11948247f93'
        v1_uuid = '0b8b47bd-f2f8-4029-923c-0e37a68340c3'
        v0_uuid = '9f6a0f3e-22e6-4c39-8733-4e672919bbc7'
        with self.assertWarnsRegex(
                UserWarning, f'(:?)Art.*{v0_uuid}.*prior.*incomplete'):
            mixed = ProvDAG(os.path.join(DATA_DIR,
                            'mixed_v0_v1_uu_emperor.qzv'))
        sorted_nodes = nx.topological_sort(mixed.collapsed_view)
        action_collections = group_by_action(mixed, sorted_nodes)
        self.assertEqual(action_collections.std_actions,
                         {act_id: {v1_uuid: 'visualization'}})
        self.assertEqual(action_collections.no_provenance_nodes, [v0_uuid])


class InitializerTests(unittest.TestCase):
    def test_init_md_from_recorded_md(self):
        no_md_id = '89af91c0-033d-4e30-8ac4-f29a3b407dc1'
        has_md_id = '99fa3670-aa1a-45f6-ba8e-803c976a1163'
        dag = ProvDAG(os.path.join(DATA_DIR, 'v5_table.qza'))
        no_md_node = dag.get_node_data(no_md_id)
        md_node = dag.get_node_data(has_md_id)
        var_nm = 'per_sample_sequences_0_barcodes'
        param_nm = 'barcodes'
        # We expect the variable name has already been added to the namespace
        ns = UsageVarsDict({var_nm: param_nm})
        cfg = ReplayConfig(use=SUPPORTED_USAGE_DRIVERS['python3'](),
                           use_recorded_metadata=False, pm=pm)

        with self.assertRaisesRegex(ValueError, 'only.*call.*if.*metadata'):
            init_md_from_recorded_md(no_md_node, var_nm, ns, cfg)

        var = init_md_from_recorded_md(md_node, var_nm, ns, cfg)
        self.assertIsInstance(var, UsageVariable)
        self.assertEqual(var.var_type, 'metadata')

        # NOTE: This tests against current expected behavior, which is pretty
        # janky and will probably be updated per the comment in the docstring
        rendered = cfg.use.render()
        self.assertRegex(rendered, 'from qiime2 import Metadata')
        self.assertRegex(
            rendered,
            r"barcodes_0_md = Metadata.load\(\<your metadata filepath\>\)")

    def test_init_md_from_artifacts_no_artifacts(self):
        cfg = ReplayConfig(use=SUPPORTED_USAGE_DRIVERS['python3'](),
                           use_recorded_metadata=False, pm=pm)
        ns = UsageVarsDict()
        md_info = MetadataInfo([], relative_fp='hmm.tsv')
        with self.assertRaisesRegex(ValueError,
                                    "not.*used.*input_artifact_uuids.*empty"):
            init_md_from_artifacts(md_info, ns, cfg)

    def test_init_md_from_artifacts_one_art(self):
        # This helper doesn't capture real data, so we're only smoke testing,
        # checking type, and confirming the repr looks reasonable.
        cfg = ReplayConfig(use=SUPPORTED_USAGE_DRIVERS['python3'](),
                           use_recorded_metadata=False, pm=pm)

        # We expect artifact vars have already been added to the namespace, so:
        a1 = cfg.use.init_artifact(name='thing1', factory=lambda: None)
        ns = UsageVarsDict({'uuid1': a1})

        md_info = MetadataInfo(['uuid1'], relative_fp='hmm.tsv')
        var = init_md_from_artifacts(md_info, ns, cfg)
        self.assertIsInstance(var, UsageVariable)
        self.assertEqual(var.var_type, 'metadata')
        rendered = var.use.render()
        exp = """from qiime2 import Metadata

thing1_md = thing1.view(Metadata)"""
        self.assertEqual(rendered, exp)

    def test_init_md_from_artifacts_many(self):
        # This helper doesn't capture real data, so we're only smoke testing,
        # checking type, and confirming the repr looks reasonable.
        cfg = ReplayConfig(use=SUPPORTED_USAGE_DRIVERS['python3'](),
                           use_recorded_metadata=False, pm=pm)

        # We expect artifact vars have already been added to the namespace, so:
        a1 = cfg.use.init_artifact(name='thing1', factory=lambda: None)
        a2 = cfg.use.init_artifact(name='thing2', factory=lambda: None)
        a3 = cfg.use.init_artifact(name='thing3', factory=lambda: None)
        ns = UsageVarsDict({'uuid1': a1, 'uuid2': a2, 'uuid3': a3})

        md_info = MetadataInfo(['uuid1', 'uuid2', 'uuid3'],
                               relative_fp='hmm.tsv')
        var = init_md_from_artifacts(md_info, ns, cfg)
        self.assertIsInstance(var, UsageVariable)
        self.assertEqual(var.var_type, 'metadata')
        rendered = var.use.render()
        exp = """from qiime2 import Metadata

thing1_md = thing1.view(Metadata)
thing2_md = thing2.view(Metadata)
thing3_md = thing3.view(Metadata)
merged_artifacts_md = thing1_md.merge(thing2_md, thing3_md)"""
        self.assertEqual(rendered, exp)

    def test_init_md_from_md_file_not_mdc(self):
        v0_uuid = '9f6a0f3e-22e6-4c39-8733-4e672919bbc7'
        v1_uuid = '0b8b47bd-f2f8-4029-923c-0e37a68340c3'
        with self.assertWarnsRegex(
                UserWarning, f'(:?)Art.*{v0_uuid}.*prior.*incomplete'):
            mixed = ProvDAG(os.path.join(DATA_DIR,
                            'mixed_v0_v1_uu_emperor.qzv'))
        v1_node = mixed.get_node_data(v1_uuid)
        md_id = 'whatevs'
        param_name = 'metadata'
        ns = UsageVarsDict({md_id: param_name})
        cfg = ReplayConfig(use=SUPPORTED_USAGE_DRIVERS['python3'](),
                           use_recorded_metadata=False, pm=pm)

        var = init_md_from_md_file(v1_node, param_name, md_id, ns, cfg)

        rendered = var.use.render()
        self.assertRegex(rendered, 'from qiime2 import Metadata')
        self.assertRegex(
            rendered,
            r'metadata_0_md = Metadata.load\(\<your metadata filepath\>\)')

    def test_init_md_from_md_file_md_is_mdc(self):
        dag = ProvDAG(os.path.join(DATA_DIR, 'v5_table.qza'))
        n_id = '99fa3670-aa1a-45f6-ba8e-803c976a1163'
        demux_node = dag.get_node_data(n_id)
        md_id = 'per_sample_sequences_0_barcodes'
        # We expect the variable name has already been added to the namespace
        ns = UsageVarsDict({md_id: 'barcodes'})
        cfg = ReplayConfig(use=SUPPORTED_USAGE_DRIVERS['python3'](),
                           use_recorded_metadata=False, pm=pm)

        var = init_md_from_md_file(demux_node, 'barcodes', md_id, ns, cfg)
        self.assertIsInstance(var, UsageVariable)
        self.assertEqual(var.var_type, 'column')
        rendered = var.use.render()
        self.assertRegex(rendered, 'from qiime2 import Metadata')
        self.assertRegex(
            rendered,
            r"barcodes_0_md = Metadata.load\(\<your metadata filepath\>\)")
        self.assertRegex(
            rendered,
            r"some_mdc = barcodes_0_md.get_column\('\<column_name\>'\)")


class BuildNoProvenanceUsageTests(CustomAssertions):
    def test_build_no_provenance_node_usage_w_complete_node(self):
        ns = UsageVarsDict()
        cfg = ReplayConfig(use=SUPPORTED_USAGE_DRIVERS['python3'](),
                           use_recorded_metadata=False, pm=pm)
        v0_uuid = '0b8b47bd-f2f8-4029-923c-0e37a68340c3'
        with self.assertWarnsRegex(
                UserWarning, f'(:?)Art.*{v0_uuid}.*prior.*incomplete'):
            single_no_prov = ProvDAG(os.path.join(DATA_DIR,
                                     'v0_uu_emperor.qzv'))
        v0 = single_no_prov.get_node_data(v0_uuid)
        build_no_provenance_node_usage(v0, v0_uuid, ns, cfg)
        out_var_name = 'visualization_0'
        self.assertEqual(ns, {v0_uuid: out_var_name})
        rendered = cfg.use.render()
        # Confirm the initial context comment is present once.
        self.assertREAppearsOnlyOnce(rendered, 'nodes have no provenance')
        header = '# Original Node ID                       String Description'
        self.assertREAppearsOnlyOnce(rendered, header)

        # Confirm expected values have been rendered
        exp_v0 = f'# {v0_uuid}   {out_var_name}'
        self.assertRegex(rendered, exp_v0)

    def test_build_no_provenance_node_usage_uuid_only_node(self):
        ns = UsageVarsDict()
        cfg = ReplayConfig(use=SUPPORTED_USAGE_DRIVERS['python3'](),
                           use_recorded_metadata=False, pm=pm)
        v0_uuid = '9f6a0f3e-22e6-4c39-8733-4e672919bbc7'
        with self.assertWarnsRegex(
                UserWarning, f'(:?)Art.*{v0_uuid}.*prior.*incomplete'):
            mixed = ProvDAG(os.path.join(DATA_DIR,
                            'mixed_v0_v1_uu_emperor.qzv'))
        # This node is only a parent UUID captured in the v1 node's action.yaml
        node = mixed.get_node_data(v0_uuid)
        self.assertEqual(node, None)
        build_no_provenance_node_usage(node, v0_uuid, ns, cfg)

        out_var_name = 'no-provenance-node_0'
        self.assertEqual(ns, {v0_uuid: out_var_name})

        rendered = cfg.use.render()
        # Confirm the initial context comment is present once.
        self.assertREAppearsOnlyOnce(rendered, 'nodes have no provenance')
        header = '# Original Node ID                       String Description'
        self.assertREAppearsOnlyOnce(rendered, header)

        # Confirm expected values have been rendered
        exp_v0 = f'# {v0_uuid}   {out_var_name}'
        self.assertRegex(rendered, exp_v0)

    def test_build_no_provenance_node_usage_many_x(self):
        """
        Context should only be logged once.
        """
        ns = UsageVarsDict()
        cfg = ReplayConfig(use=SUPPORTED_USAGE_DRIVERS['python3'](),
                           use_recorded_metadata=False, pm=pm)

        # This function doesn't actually know about the DAG, so no need to join
        v0_uuid = '0b8b47bd-f2f8-4029-923c-0e37a68340c3'
        with self.assertWarnsRegex(
                UserWarning, f'(:?)Art.*{v0_uuid}.*prior.*incomplete'):
            single_no_prov = ProvDAG(os.path.join(DATA_DIR,
                                     'v0_uu_emperor.qzv'))
        v0_viz = single_no_prov.get_node_data(v0_uuid)

        dummy_viz_uuid = v0_uuid + '-dummy'
        # Will return the same type as v0
        dummy_viz = single_no_prov.get_node_data(v0_uuid)

        tbl_uuid = '89af91c0-033d-4e30-8ac4-f29a3b407dc1'
        with self.assertWarnsRegex(
                UserWarning, f'(:?)Art.*{tbl_uuid}.*prior.*incomplete'):
            v0_tbl = ProvDAG(os.path.join(DATA_DIR, 'v0_table.qza'))
        tbl = v0_tbl.get_node_data(tbl_uuid)
        build_no_provenance_node_usage(v0_viz, v0_uuid, ns, cfg)
        build_no_provenance_node_usage(tbl, tbl_uuid, ns, cfg)
        build_no_provenance_node_usage(dummy_viz, dummy_viz_uuid, ns, cfg)
        self.assertIn(v0_uuid, ns)
        self.assertIn(tbl_uuid, ns)
        self.assertIn(dummy_viz_uuid, ns)
        self.assertEqual(ns[v0_uuid], 'visualization_0')
        self.assertEqual(ns[tbl_uuid], 'feature_table_frequency_0')
        self.assertEqual(ns[dummy_viz_uuid], 'visualization_1')
        rendered = cfg.use.render()
        # Confirm the initial context isn't repeated.
        self.assertREAppearsOnlyOnce(rendered, 'nodes have no provenance')
        header = '# Original Node ID                       String Description'
        self.assertREAppearsOnlyOnce(rendered, header)

        # Confirm expected values have been rendered
        exp_v0 = '# 0b8b47bd-f2f8-4029-923c-0e37a68340c3   visualization_0'
        exp_t = ('# 89af91c0-033d-4e30-8ac4-f29a3b407dc1   '
                 'feature_table_frequency_0')
        exp_v1 = ('# 0b8b47bd-f2f8-4029-923c-0e37a68340c3-dummy   '
                  'visualization_1')
        self.assertRegex(rendered, exp_v0)
        self.assertRegex(rendered, exp_t)
        self.assertRegex(rendered, exp_v1)


class BuildImportUsageTests(CustomAssertions):
    def test_build_import_usage_python(self):
        ns = UsageVarsDict()
        cfg = ReplayConfig(use=SUPPORTED_USAGE_DRIVERS['python3'](),
                           use_recorded_metadata=False, pm=pm)
        dag = ProvDAG(os.path.join(DATA_DIR, 'v5_table.qza'))
        n_id = 'a35830e1-4535-47c6-aa23-be295a57ee1c'
        imp_node = dag.get_node_data(n_id)
        c_to_s_type = camel_to_snake(imp_node.type)
        unq_var_nm = c_to_s_type + '_0'
        build_import_usage(imp_node, ns, cfg)
        rendered = cfg.use.render()
        out_name = ns[n_id].to_interface_name()

        self.assertIsInstance(ns[n_id], UsageVariable)
        self.assertEqual(ns[n_id].var_type, 'artifact')
        self.assertEqual(ns[n_id].name, unq_var_nm)
        self.assertRegex(rendered, 'from qiime2 import Artifact')
        self.assertRegex(rendered, rf'{out_name} = Artifact.import_data\(')
        self.assertRegex(rendered, imp_node.type)
        self.assertRegex(rendered, '<your data here>')

    def test_build_import_usage_cli(self):
        ns = UsageVarsDict()
        cfg = ReplayConfig(use=SUPPORTED_USAGE_DRIVERS['cli'](),
                           use_recorded_metadata=False, pm=pm)
        dag = ProvDAG(os.path.join(DATA_DIR, 'v5_table.qza'))
        n_id = 'a35830e1-4535-47c6-aa23-be295a57ee1c'
        imp_node = dag.get_node_data(n_id)
        c_to_s_type = camel_to_snake(imp_node.type)
        unq_var_nm = c_to_s_type + '_0'
        build_import_usage(imp_node, ns, cfg)
        rendered = cfg.use.render()
        out_name = ns[n_id].to_interface_name()

        self.assertIsInstance(ns[n_id], UsageVariable)
        self.assertEqual(ns[n_id].var_type, 'artifact')
        self.assertEqual(ns[n_id].name, unq_var_nm)
        self.assertRegex(rendered, r'qiime tools import \\')
        self.assertRegex(rendered, f"  --type '{imp_node.type}'")
        self.assertRegex(rendered, "  --input-path <your data here>")
        self.assertRegex(rendered, f"  --output-path {out_name}")


class BuildActionUsageTests(CustomAssertions):
    def test_build_action_usage_cli(self):
        plugin = 'demux'
        action = 'emp-single'
        cfg = ReplayConfig(use=SUPPORTED_USAGE_DRIVERS['cli'](),
                           use_recorded_metadata=False, pm=pm)
        import_var = CLIUsageVariable(
            'imported_seqs_0', lambda: None, 'artifact', cfg.use)
        ns = UsageVarsDict(
            {'a35830e1-4535-47c6-aa23-be295a57ee1c': import_var})
        a_ns = set()
        dag = ProvDAG(os.path.join(DATA_DIR, 'v5_table.qza'))
        act_id = '3d69c8d1-a1fa-4ab3-ac88-3a98da15b2d5'
        n_id = '99fa3670-aa1a-45f6-ba8e-803c976a1163'
        node = dag.get_node_data(n_id)
        acts = ActionCollections(std_actions={act_id:
                                              {n_id: 'per_sample_sequences'}})
        unq_var_nm = node.action.output_name + '_0'
        build_action_usage(node, ns, a_ns, acts.std_actions, act_id, cfg)
        rendered = cfg.use.render()
        out_name = ns[n_id].to_interface_name()

        self.assertIsInstance(ns[n_id], UsageVariable)
        self.assertEqual(ns[n_id].var_type, 'artifact')
        self.assertEqual(ns[n_id].name, unq_var_nm)
        self.assertREAppearsOnlyOnce(rendered, "Replay attempts.*metadata")
        self.assertREAppearsOnlyOnce(rendered, "command may have received")
        act_undersc = re.sub('-', '_', action)
        self.assertREAppearsOnlyOnce(
            rendered,
            fr"saved at 'recorded_metadata\/{plugin}_{act_undersc}_0\/'")
        self.assertRegex(rendered, f"qiime {plugin} {action}")
        self.assertRegex(rendered, "--i-seqs imported-seqs-0.qza")
        self.assertRegex(rendered, "--m-barcodes-file barcodes-0.tsv")
        self.assertRegex(rendered, "--m-barcodes-column <column_name>")
        self.assertRegex(rendered, "--p-no-rev-comp-barcodes")
        self.assertRegex(rendered, "--p-no-rev-comp-mapping-barcodes")
        self.assertRegex(rendered, f"--o-per-sample-sequences {out_name}")

    def test_build_action_usage_cli_parameter_name_has_changed(self):
        plugin = 'emperor'
        action = 'plot'
        act_id = 'c147dfbc-139a-4db0-ac17-b11948247f93'
        pcoa_id = '9f6a0f3e-22e6-4c39-8733-4e672919bbc7'
        n_id = '0b8b47bd-f2f8-4029-923c-0e37a68340c3'
        cfg = ReplayConfig(use=SUPPORTED_USAGE_DRIVERS['cli'](),
                           use_recorded_metadata=True, pm=pm)
        import_var = CLIUsageVariable(
            'pcoa', lambda: None, 'artifact', cfg.use)
        ns = UsageVarsDict({pcoa_id: import_var})
        a_ns = set()
        mixed_uuid = '9f6a0f3e-22e6-4c39-8733-4e672919bbc7'
        with self.assertWarnsRegex(
                UserWarning, f'(:?)Art.*{mixed_uuid}.*prior.*incomplete'):
            dag = ProvDAG(os.path.join(DATA_DIR, 'mixed_v0_v1_uu_emperor.qzv'))
        node = dag.get_node_data(n_id)
        # This is a v1 node, so we don't have an output name. use type.
        out_name_raw = node.type.lower()
        acts = ActionCollections(std_actions={act_id:
                                              {n_id: out_name_raw}})
        unq_var_nm = out_name_raw + '_0'
        build_action_usage(node, ns, a_ns, acts.std_actions, act_id, cfg)
        rendered = cfg.use.render()
        out_name = ns[n_id].to_interface_name()

        self.assertIsInstance(ns[n_id], UsageVariable)
        self.assertEqual(ns[n_id].var_type, 'visualization')
        self.assertEqual(ns[n_id].name, unq_var_nm)

        self.assertRegex(rendered, f"qiime {plugin} {action}")
        self.assertRegex(rendered, "--i-pcoa pcoa.qza")
        self.assertRegex(rendered, "--m-metadata-file metadata-0")
        self.assertRegex(rendered,
                         "(?s)parameter name was not found in your.*env")
        # This has become "custom-axes" since the .qzv was first recorded
        self.assertRegex(rendered, r"--\?-custom-axis DaysSinceExperimentSta")
        self.assertRegex(rendered, f"--o-visualization {out_name}")

    def test_build_action_usage_python(self):
        plugin = 'demux'
        action = 'emp_single'
        cfg = ReplayConfig(use=SUPPORTED_USAGE_DRIVERS['python3'](),
                           use_recorded_metadata=False, pm=pm)
        import_var = ArtifactAPIUsageVariable(
            'imported_seqs_0', lambda: None, 'artifact', cfg.use)
        seqs_id = 'a35830e1-4535-47c6-aa23-be295a57ee1c'
        ns = UsageVarsDict({seqs_id: import_var})
        a_ns = set()
        dag = ProvDAG(os.path.join(DATA_DIR, 'v5_table.qza'))
        act_id = '3d69c8d1-a1fa-4ab3-ac88-3a98da15b2d5'
        n_id = '99fa3670-aa1a-45f6-ba8e-803c976a1163'
        node = dag.get_node_data(n_id)
        out_name_raw = node.action.output_name
        acts = ActionCollections(std_actions={act_id:
                                              {n_id: out_name_raw}})
        unq_var_nm = out_name_raw + '_0'
        build_action_usage(node, ns, a_ns, acts.std_actions, act_id, cfg)
        rendered = cfg.use.render()
        out_name = ns[n_id].to_interface_name()

        self.assertIsInstance(ns[n_id], UsageVariable)
        self.assertEqual(ns[n_id].var_type, 'artifact')
        self.assertEqual(ns[n_id].name, unq_var_nm)

        self.assertRegex(rendered, "from qiime2 import Metadata")
        self.assertRegex(
            rendered, f"import.*{plugin}.actions as {plugin}_actions")

        self.assertREAppearsOnlyOnce(rendered, "Replay attempts.*metadata")
        self.assertREAppearsOnlyOnce(rendered, "command may have received")
        self.assertREAppearsOnlyOnce(
            rendered,
            fr"saved at 'recorded_metadata\/{plugin}_{action}_0\/'")
        self.assertREAppearsOnlyOnce(rendered, "NOTE:.*substitute.*Metadata")

        md_name = 'barcodes_0_md'
        self.assertRegex(rendered, rf'{md_name} = Metadata.load\(<.*filepath>')
        self.assertRegex(rendered, f'some_mdc = {md_name}.get_col.*<col')

        self.assertRegex(rendered,
                         rf'{out_name}, _ = {plugin}_actions.{action}\(')

        self.assertRegex(rendered, f'seqs.*{ns[seqs_id].name}')
        self.assertRegex(rendered, 'barcodes.*some_mdc')
        self.assertRegex(rendered, 'rev_comp_barcodes.*False')
        self.assertRegex(rendered, 'rev_comp_mapping_barcodes.*False')

    def test_build_action_usage_recorded_md(self):
        plugin = 'emperor'
        action = 'plot'
        md_param = 'metadata'
        act_id = 'c147dfbc-139a-4db0-ac17-b11948247f93'
        pcoa_id = '9f6a0f3e-22e6-4c39-8733-4e672919bbc7'
        n_id = '0b8b47bd-f2f8-4029-923c-0e37a68340c3'
        cfg = ReplayConfig(use=SUPPORTED_USAGE_DRIVERS['python3'](),
                           use_recorded_metadata=True, pm=pm)
        import_var = ArtifactAPIUsageVariable(
            'pcoa', lambda: None, 'artifact', cfg.use)
        ns = UsageVarsDict({pcoa_id: import_var})
        a_ns = set()
        mixed_uuid = '9f6a0f3e-22e6-4c39-8733-4e672919bbc7'
        with self.assertWarnsRegex(
                UserWarning, f'(:?)Art.*{mixed_uuid}.*prior.*incomplete'):
            dag = ProvDAG(os.path.join(DATA_DIR, 'mixed_v0_v1_uu_emperor.qzv'))
        node = dag.get_node_data(n_id)
        # This is a v1 node, so we don't have an output name. use type.
        out_name_raw = node.type.lower()
        acts = ActionCollections(std_actions={act_id:
                                              {n_id: out_name_raw}})
        unq_var_nm = out_name_raw + '_0'
        build_action_usage(node, ns, a_ns, acts.std_actions, act_id, cfg)
        rendered = cfg.use.render()
        out_name = ns[n_id].to_interface_name()

        self.assertIsInstance(ns[n_id], UsageVariable)
        self.assertEqual(ns[n_id].var_type, 'visualization')
        self.assertEqual(ns[n_id].name, unq_var_nm)

        self.assertRegex(rendered, "from qiime2 import Metadata")
        self.assertRegex(
            rendered, f"import.*{plugin}.actions as {plugin}_actions")

        md_name = f'{md_param}_0_md'
        self.assertRegex(rendered, rf'{md_name} = Metadata.load\(<.*filepath>')

        self.assertRegex(rendered,
                         rf'{out_name}, = {plugin}_actions.{action}\(')
        self.assertRegex(rendered, f'pcoa.*{ns[pcoa_id].name}')
        self.assertRegex(rendered, f'metadata.*{md_name}')
        self.assertRegex(rendered, "custom_axis='DaysSinceExperimentStart'")

    @patch('provenance_lib.replay.init_md_from_artifacts')
    def test_build_action_usage_md_from_artifacts(self, patch):
        act_id = '59798956-9261-40f3-b70f-fc5059e379f5'
        n_id = '75f035ac-33fb-4d1c-bdcd-63ae1d564056'
        sd_act_id = '7862c023-13d4-4cd5-a9db-c92507055d25'
        sd_id = 'a42ea02f-8c40-432c-9b88-e602f6cd3787'
        dag = ProvDAG(os.path.join(DATA_DIR, 'md_tabulated_from_art.qzv'))
        cfg = ReplayConfig(use=SUPPORTED_USAGE_DRIVERS['python3'](),
                           use_recorded_metadata=False, pm=pm)
        sd_var = ArtifactAPIUsageVariable(
            'sample_data_alpha_diversity_0', lambda: None, 'artifact', cfg.use)
        ns = UsageVarsDict({sd_id: sd_var})
        a_ns = set()
        node = dag.get_node_data(n_id)
        out_name_raw = node.action.output_name
        acts = ActionCollections(std_actions={act_id: {n_id: out_name_raw},
                                              sd_act_id: {sd_id: 'smpl_data'}})
        build_action_usage(node, ns, a_ns, acts.std_actions, act_id, cfg)
        patch.assert_called_once_with(
            MetadataInfo(
                input_artifact_uuids=['a42ea02f-8c40-432c-9b88-e602f6cd3787'],
                relative_fp='input.tsv'),
            ns, cfg)


class CitationsTests(unittest.TestCase):
    def test_dedupe_citations(self):
        fn = os.path.join(DATA_DIR, 'dupes.bib')
        with open(fn) as bibtex_file:
            bib_db = bp.load(bibtex_file)
        deduped = dedupe_citations(bib_db.entries)
        # Dedupe by DOI will preserve only one of the biom.table entries
        self.assertEqual(len(deduped), 2)
        # Confirm each paper is present. The len assertion ensures one-to-one
        lower_keys = [entry['ID'].lower() for entry in deduped]
        self.assertTrue(any('framework' in key for key in lower_keys))
        self.assertTrue(any('biom' in key for key in lower_keys))

    def test_collect_citations_no_deduped(self):
        dag = ProvDAG(TEST_DATA['5']['qzv_fp'])
        exp_keys = {'framework|qiime2:2018.11.0|0',
                    'action|feature-table:2018.11.0|method:rarefy|0',
                    'view|types:2018.11.0|BIOMV210DirFmt|0',
                    'view|types:2018.11.0|biom.table:Table|0',
                    'plugin|dada2:2018.11.0|0',
                    'action|alignment:2018.11.0|method:mafft|0',
                    'action|diversity:2018.11.0|method:beta_phylogenetic|0',
                    'action|diversity:2018.11.0|method:beta_phylogenetic|1',
                    'action|diversity:2018.11.0|method:beta_phylogenetic|2',
                    'action|diversity:2018.11.0|method:beta_phylogenetic|3',
                    'action|diversity:2018.11.0|method:beta_phylogenetic|4',
                    'view|types:2018.11.0|BIOMV210Format|0',
                    'plugin|emperor:2018.11.0|0',
                    'plugin|emperor:2018.11.0|1',
                    'action|phylogeny:2018.11.0|method:fasttree|0',
                    'action|alignment:2018.11.0|method:mask|0',
                    }
        citations = collect_citations(dag, deduped=False)
        keys = set(citations.entries_dict.keys())
        self.assertEqual(len(keys), len(exp_keys))
        self.assertEqual(keys, exp_keys)

    def test_collect_deduped(self):
        v5_tbl = ProvDAG(os.path.join(DATA_DIR, 'v5_table.qza'))
        std_keys = {'framework|qiime2:2018.11.0|0',
                    'view|types:2018.11.0|BIOMV210DirFmt|0',
                    'view|types:2018.11.0|biom.table:Table|0',
                    'plugin|dada2:2018.11.0|0'}
        citations = collect_citations(v5_tbl, deduped=False)
        keys = set(citations.entries_dict.keys())
        self.assertEqual(len(keys), len(std_keys))
        self.assertEqual(keys, std_keys)

        citations = collect_citations(v5_tbl, deduped=True)
        keys = set(citations.entries_dict.keys())
        # Dedupe by DOI will drop one of the biom.table entries
        self.assertEqual(len(keys), 3)
        # We want to confirm each paper is present - it doesn't matter which
        # biom entry is dropped.
        lower_keys = [key.lower() for key in keys]
        self.assertTrue(any('framework' in key for key in lower_keys))
        self.assertTrue(any('dada2' in key for key in lower_keys))
        self.assertTrue(any('biom' in key for key in lower_keys))

    def test_collect_citations_no_prov(self):
        v0_uuid = '9f6a0f3e-22e6-4c39-8733-4e672919bbc7'
        with self.assertWarnsRegex(
                UserWarning, f'(:?)Art.*{v0_uuid}.*prior.*incomplete'):
            mixed = ProvDAG(os.path.join(DATA_DIR,
                            'mixed_v0_v1_uu_emperor.qzv'))
        exp_keys = set()
        citations = collect_citations(mixed)
        keys = set(citations.entries_dict.keys())
        self.assertEqual(len(keys), 0)
        self.assertEqual(keys, exp_keys)

    def test_write_citations(self):
        dag = ProvDAG(TEST_DATA['5']['qzv_fp'])
        exp_keys = ['framework|qiime2:2018.11.0|0',
                    'action|feature-table:2018.11.0|method:rarefy|0',
                    'view|types:2018.11.0|BIOMV210DirFmt|0',
                    'plugin|dada2:2018.11.0|0',
                    'action|alignment:2018.11.0|method:mafft|0',
                    'action|diversity:2018.11.0|method:beta_phylogenetic|0',
                    'action|diversity:2018.11.0|method:beta_phylogenetic|1',
                    'action|diversity:2018.11.0|method:beta_phylogenetic|2',
                    'action|diversity:2018.11.0|method:beta_phylogenetic|3',
                    'action|diversity:2018.11.0|method:beta_phylogenetic|4',
                    'plugin|emperor:2018.11.0|0',
                    'plugin|emperor:2018.11.0|1',
                    'action|phylogeny:2018.11.0|method:fasttree|0',
                    'action|alignment:2018.11.0|method:mask|0',
                    ]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_fp = pathlib.Path(tmpdir) / 'citations.bib'
            out_fn = str(out_fp)
            write_citations(dag, out_fn)
            self.assertTrue(out_fp.is_file())
            with open(out_fn, 'r') as fp:
                written = fp.read()
                for key in exp_keys:
                    self.assertIn(key, written)

    def test_write_citations_no_prov(self):
        v0_uuid = '9f6a0f3e-22e6-4c39-8733-4e672919bbc7'
        with self.assertWarnsRegex(
                UserWarning, f'(:?)Art.*{v0_uuid}.*prior.*incomplete'):
            mixed = ProvDAG(os.path.join(DATA_DIR,
                            'mixed_v0_v1_uu_emperor.qzv'))
        exp = "No citations were recorded for this file."
        with tempfile.TemporaryDirectory() as tmpdir:
            out_fp = pathlib.Path(tmpdir) / 'citations.bib'
            out_fn = str(out_fp)
            write_citations(mixed, out_fn)
            self.assertTrue(out_fp.is_file())
            with open(out_fn, 'r') as fp:
                written = fp.read()
                self.assertEqual(exp, written)
