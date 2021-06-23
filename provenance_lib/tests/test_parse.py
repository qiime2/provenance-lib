import os
import pathlib
import unittest
from unittest.mock import MagicMock

import zipfile

from ..archive_formats import ProvNode
from ..parse import ProvDAG, UnionedDAG
from .util import is_provnode_data


DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')


class ProvDAGTests(unittest.TestCase):
    # Remove the character limit when reporting failing tests for this class
    maxDiff = None

    v5_qzv = os.path.join(DATA_DIR, 'v5_uu_emperor.qzv')
    v5_qzv_version_gone = os.path.join(DATA_DIR, 'VERSION_missing.qzv')
    v5_qzv_version_bad = os.path.join(DATA_DIR, 'VERSION_bad.qzv')
    v5_qzv_version_short = os.path.join(DATA_DIR, 'VERSION_short.qzv')
    v5_qzv_version_long = os.path.join(DATA_DIR, 'VERSION_long.qzv')
    v5_qzv_two_root_mds = os.path.join(DATA_DIR, 'two_root_md_yamls.qzv')
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
        mock_archive = MagicMock()
        self.root_metadata_fps = None
        with zipfile.ZipFile(self.v5_qzv) as zf:
            all_filenames = zf.namelist()
            self.root_md_fnames = filter(is_provnode_data, all_filenames)
            self.root_md_fps = [pathlib.Path(fp) for fp in self.root_md_fnames]
            self.v5_ProvNode = ProvNode(mock_archive, zf,
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

    def test_nonexistent_fp(self):
        with self.assertRaisesRegex(FileNotFoundError, "not_a_filepath.qza"):
            ProvDAG(self.fake_fp)

    def test_not_a_zip_archive(self):
        with self.assertRaisesRegex(zipfile.BadZipFile,
                                    "File is not a zip file"):
            ProvDAG(self.not_a_zip)

    # Testing major VERSION file issues is easier and more reliable with
    # "real" archives (here). Detailed tests of the VERSION regex are in
    # test_archive_formats.VersionMatcherTests, so we can reduce overhead
    def test_archive_version_correct(self):
        self.assertEqual(self.v5_provDag.archive_version, '5')

    def test_framework_version_correct(self):
        self.assertEqual(self.v5_provDag.framework_version, '2018.11.0')

    def test_no_VERSION(self):
        with self.assertRaisesRegex(ValueError, "VERSION.*nonexistent"):
            ProvDAG(self.v5_qzv_version_gone)

    def test_bad_VERSION(self):
        with self.assertRaisesRegex(ValueError, "VERSION.*out of spec"):
            ProvDAG(self.v5_qzv_version_bad)

    def test_short_VERSION(self):
        with self.assertRaisesRegex(ValueError, "VERSION.*out of spec"):
            ProvDAG(self.v5_qzv_version_short)

    def test_long_VERSION(self):
        with self.assertRaisesRegex(ValueError,
                                    "VERSION.*out of spec"):
            ProvDAG(self.v5_qzv_version_long)


class UnionedDAGTests(unittest.TestCase):
    v5_qzv = os.path.join(DATA_DIR, 'v5_uu_emperor.qzv')
    v5_dag = ProvDAG(v5_qzv)
    dag_list = [v5_dag]

    def test_union_one_dag(self):
        dag = UnionedDAG(self.dag_list)
        self.assertEqual(dag.root_uuids,
                         ["ffb7cee3-2f1f-4988-90cc-efd5184ef003"])
        self.assertEqual(dag.root_nodes, [self.v5_dag.root_node])
