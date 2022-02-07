from click.testing import CliRunner
import pathlib
import tempfile

from ..click_commands import replay
from .test_parse import TEST_DATA
from .testing_utilities import CustomAssertions


class ReplayTests(CustomAssertions):
    def test_replay(self):
        in_fp = TEST_DATA['5']['qzv_fp']
        in_fn = str(in_fp)
        out_fn = "provenance_py/provenance_lib/test_outputs/cli_replay_test.sh"
        with tempfile.TemporaryDirectory() as tmpdir:
            out_fp = pathlib.Path(tmpdir) / 'rendered.txt'
            out_fn = str(out_fp)
            res = CliRunner().invoke(
                cli=replay,
                args=(f"--i-in-fp {in_fn} --o-out-fp {out_fn}"))

            self.assertEqual(res.exit_code, 0)
            self.assertTrue(out_fp.is_file())

            with open(out_fn, 'r') as fp:
                rendered = fp.read()
            self.assertIn("qiime tools import", rendered)
            self.assertIn("--type 'EMPSingleEndSequences'", rendered)
            self.assertIn("--input-path <your data here>", rendered)
            self.assertIn("--output-path emp-single-end-sequences-0.qza",
                          rendered)

            self.assertREAppearsOnlyOnce(rendered, "Replay attempts.*metadata")
            self.assertRegex(rendered,
                             'The following command.*additional metadata')

            self.assertIn('qiime demux emp-single', rendered)
            self.assertIn('qiime dada2 denoise-single', rendered)
            self.assertIn('qiime phylogeny align-to-tree-mafft', rendered)
            self.assertIn(
                'recorded_metadata/diversity_core_metrics_phylogenetic_0/',
                rendered)
            self.assertIn('qiime diversity core-metrics-phylogenetic',
                          rendered)
            self.assertIn('parameter name was not found', rendered)
            self.assertIn('--?-n-jobs 1', rendered)

    def test_replay_use_md_without_parse(self):
        in_fp = TEST_DATA['5']['qzv_fp']
        in_fn = str(in_fp)
        out_fn = 'unused_fp'
        res = CliRunner().invoke(
            cli=replay,
            args=(f"--i-in-fp {in_fn} --o-out-fp {out_fn} "
                  "--p-no-parse-metadata --p-use-recorded-metadata"))
        self.assertEqual(res.exit_code, 1)
        self.assertIsInstance(res.exception, ValueError)
        self.assertRegex(str(res.exception), "Metadata not parsed for replay")
