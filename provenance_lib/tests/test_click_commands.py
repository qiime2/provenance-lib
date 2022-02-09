import bibtexparser as bp
from click.testing import CliRunner
import pathlib
import tempfile

from ..click_commands import replay, write_citations_from_artifact
from .test_parse import TEST_DATA
from .testing_utilities import CustomAssertions


class ReplayTests(CustomAssertions):
    def test_replay(self):
        in_fp = TEST_DATA['5']['qzv_fp']
        in_fn = str(in_fp)
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


class ReportCitationsTests(CustomAssertions):
    def test_write_citations_from_artifact(self):
        in_fp = TEST_DATA['5']['qzv_fp']
        in_fn = str(in_fp)
        with tempfile.TemporaryDirectory() as tmpdir:
            out_fp = pathlib.Path(tmpdir) / 'citations.bib'
            out_fn = str(out_fp)
            res = CliRunner().invoke(
                cli=write_citations_from_artifact,
                args=(f"--i-in-fp {in_fn} --o-out-fp {out_fn}"))

            self.assertEqual(res.exit_code, 0)
            self.assertTrue(out_fp.is_file())

            exp = ['action|alignment:2018.11.0|method:mafft|0',
                   'action|alignment:2018.11.0|method:mask|0',
                   'action|diversity:2018.11.0|method:beta_phylogenetic|0',
                   'action|diversity:2018.11.0|method:beta_phylogenetic|1',
                   'action|diversity:2018.11.0|method:beta_phylogenetic|2',
                   'action|diversity:2018.11.0|method:beta_phylogenetic|3',
                   'action|diversity:2018.11.0|method:beta_phylogenetic|4',
                   'action|feature-table:2018.11.0|method:rarefy|0',
                   'action|phylogeny:2018.11.0|method:fasttree|0',
                   'framework|qiime2:2018.11.0|0',
                   'plugin|dada2:2018.11.0|0',
                   'plugin|emperor:2018.11.0|0',
                   'plugin|emperor:2018.11.0|1',
                   'view|types:2018.11.0|BIOMV210DirFmt|0',
                   ]

            with open(out_fn) as bibtex_file:
                bib_database = bp.load(bibtex_file)
                self.assertEqual(len(exp), len(bib_database.entries))

            with open(out_fn, 'r') as fp:
                written = fp.read()

            for record in set(exp):
                self.assertIn(record, written)

    def test_write_citations_from_artifact_no_deduped(self):
        in_fp = TEST_DATA['5']['qzv_fp']
        in_fn = str(in_fp)
        with tempfile.TemporaryDirectory() as tmpdir:
            out_fp = pathlib.Path(tmpdir) / 'citations.bib'
            out_fn = str(out_fp)
            res = CliRunner().invoke(
                cli=write_citations_from_artifact,
                args=(f"--i-in-fp {in_fn} --o-out-fp {out_fn} "
                      "--p-no-deduped"))

            self.assertEqual(res.exit_code, 0)
            self.assertTrue(out_fp.is_file())

            with open(out_fn, 'r') as fp:
                written = fp.read()

            exp = ['action|alignment:2018.11.0|method:mafft|0',
                   'action|alignment:2018.11.0|method:mask|0',
                   'action|diversity:2018.11.0|method:beta_phylogenetic|0',
                   'action|diversity:2018.11.0|method:beta_phylogenetic|1',
                   'action|diversity:2018.11.0|method:beta_phylogenetic|2',
                   'action|diversity:2018.11.0|method:beta_phylogenetic|3',
                   'action|diversity:2018.11.0|method:beta_phylogenetic|4',
                   'action|feature-table:2018.11.0|method:rarefy|0',
                   'action|phylogeny:2018.11.0|method:fasttree|0',
                   'framework|qiime2:2018.11.0|0',
                   'framework|qiime2:2018.11.0|0',
                   'framework|qiime2:2018.11.0|0',
                   'framework|qiime2:2018.11.0|0',
                   'framework|qiime2:2018.11.0|0',
                   'framework|qiime2:2018.11.0|0',
                   'framework|qiime2:2018.11.0|0',
                   'framework|qiime2:2018.11.0|0',
                   'framework|qiime2:2018.11.0|0',
                   'framework|qiime2:2018.11.0|0',
                   'framework|qiime2:2018.11.0|0',
                   'framework|qiime2:2018.11.0|0',
                   'framework|qiime2:2018.11.0|0',
                   'framework|qiime2:2018.11.0|0',
                   'framework|qiime2:2018.11.0|0',
                   'plugin|dada2:2018.11.0|0',
                   'plugin|dada2:2018.11.0|0',
                   'plugin|emperor:2018.11.0|0',
                   'plugin|emperor:2018.11.0|1',
                   'view|types:2018.11.0|biom.table:Table|0',
                   'view|types:2018.11.0|biom.table:Table|0',
                   'view|types:2018.11.0|BIOMV210DirFmt|0',
                   'view|types:2018.11.0|BIOMV210DirFmt|0',
                   'view|types:2018.11.0|BIOMV210DirFmt|0',
                   'view|types:2018.11.0|BIOMV210Format|0',
                   ]

            for record in set(exp):
                self.assertIn(record, written)

            with open(out_fn) as bibtex_file:
                bib_database = bp.load(bibtex_file)
                self.assertEqual(len(exp), len(bib_database.entries))
