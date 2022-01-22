import unittest

from ..replay import UniqueValsDict
from ..yaml_constructors import MetadataInfo

from qiime2.sdk import PluginManager  # type: ignore
from qiime2.plugins import ArtifactAPIUsage  # type: ignore

pm = PluginManager()


class UniqueValsDictTests(unittest.TestCase):
    def test_uniquify(self):
        collision_val = 'emp_single_end_sequences'
        unique_val = 'some_prime'
        ns = UniqueValsDict({'123': collision_val})
        self.assertEqual(ns.data, {'123': 'emp_single_end_sequences_0'})

        # We can update w/ multiple values. Also, if the same value has been
        # repatedly added to ns, we expect n to increment each time.
        ns.update({'456': collision_val, 'unique': unique_val})
        self.assertEqual(ns['456'], 'emp_single_end_sequences_1')
        self.assertEqual(ns['unique'], 'some_prime_0')

        ns['789'] = collision_val
        self.assertEqual(ns.pop('789'), 'emp_single_end_sequences_2')

    def test_evaluate_md_info(self):
        # TODO: Delete this scratchpad test
        x = eval("MetadataInfo(input_artifact_uuids=[], "
                 "relative_fp='barcodes.tsv')")
        self.assertIsInstance(x, MetadataInfo)

    def test_why_borken(self):
        # TODO: Delete this scratchpad test
        use = ArtifactAPIUsage()
        x = eval("use.action("
                 "use.UsageAction(plugin_id='demux', action_id='emp_single'), "
                 "use.UsageInputs("
                 "**{'seqs': 'a35830e1-4535-47c6-aa23-be295a57ee1c', "
                 "'barcodes': MetadataInfo(input_artifact_uuids=[], "
                 "relative_fp='barcodes.tsv'), "
                 "'rev_comp_barcodes': False, "
                 "'rev_comp_mapping_barcodes': False}), "
                 "use.UsageOutputNames("
                 "**{'99fa3670-aa1a-45f6-ba8e-803c976a1163': "
                 "'per_sample_sequences'}))")

        print(x)
        print(use.render())
        self.assertTrue(False)
