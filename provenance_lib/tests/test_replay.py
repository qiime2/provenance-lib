import unittest
import os

from qiime2 import Artifact
from qiime2.sdk import PluginManager  # type: ignore
from qiime2.sdk.usage import Usage, UsageVariable

from ..replay import UsageVarsDict
from .test_parse import DATA_DIR

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
