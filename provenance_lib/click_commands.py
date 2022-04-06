import click
import os
import pathlib
import shutil
import tempfile

from .parse import ProvDAG
from .replay import replay_fp, replay_provdag, write_citations
from ._usage_drivers import DRIVER_CHOICES, DRIVER_NAMES
from .util import FileName


@click.group()
def replay():
    pass  # pragma: no cover


@replay.command(no_args_is_help=True)
@click.option('--i-in-fp', required=True,
              help='filepath to a QIIME 2 Archive or directory of Archives')
@click.option('--p-recurse/--p-no-recurse',
              default=False,
              show_default=True,
              help=('if in-fp is a directory, will also search sub-directories'
                    ' when finding .qza/.qzv files to parse'))
@click.option('--p-usage-driver',
              default='cli',
              show_default=True,
              help='the target interface for your replay script',
              type=click.Choice(DRIVER_NAMES, case_sensitive=False))
@click.option('--p-validate-checksums/--p-no-validate-checksums',
              default=True,
              show_default=True,
              help='check that replayed archives are intact and uncorrupted')
@click.option('--p-parse-metadata/--p-no-parse-metadata',
              default=True,
              show_default=True,
              help=('parse the original metadata captured by provenance '
                    'for review or replay'))
@click.option('--p-use-recorded-metadata/--p-no-use-recorded-metadata',
              default=False,
              show_default=True,
              help='re-use the original metadata captured by provenance')
@click.option('--p-suppress-header/--p-no-suppress-header',
              default=False,
              show_default=True,
              help='do not write header/footer blocks in the output script')
@click.option('--p-verbose/--p-no-verbose',
              default=True,
              show_default=True,
              help='print status messages to stdout while processing')
@click.option('--o-out-fp',
              required=True,
              help='the filepath where your replay script should be written.')
def provenance(i_in_fp: FileName, o_out_fp: FileName,
               p_usage_driver: DRIVER_CHOICES,
               p_recurse: bool = False,
               p_validate_checksums: bool = True,
               p_parse_metadata: bool = True,
               p_use_recorded_metadata: bool = False,
               p_suppress_header: bool = False,
               p_verbose: bool = True):
    """
    Replay provenance from a QIIME 2 Artifact filepath to a written executable
    """
    replay_fp(in_fp=i_in_fp, out_fp=o_out_fp,
              usage_driver_name=p_usage_driver,
              validate_checksums=p_validate_checksums,
              parse_metadata=p_parse_metadata,
              recursive=p_recurse,
              use_recorded_metadata=p_use_recorded_metadata,
              suppress_header=p_suppress_header,
              verbose=p_verbose)
    filename = os.path.realpath(o_out_fp)
    click.echo(f'Replay script written to {filename}')


@replay.command(no_args_is_help=True)
@click.option('--i-in-fp', required=True,
              help='filepath to a QIIME 2 Archive or directory of Archives')
@click.option('--p-recurse/--p-no-recurse',
              default=False,
              show_default=True,
              help=('if in-fp is a directory, will also search sub-directories'
                    ' when finding .qza/.qzv files to parse'))
@click.option('--p-deduplicate/--p-no-deduplicate',
              default=True,
              show_default=True,
              help=('If deduplicate, duplicate citations will be removed '
                    'heuristically, e.g. by comparing DOI fields. '
                    'This greatly reduces manual curation of reference lists, '
                    'but introduces a small risk of reference loss.'))
@click.option('--p-suppress-header/--p-no-suppress-header',
              default=False,
              show_default=True,
              help='do not write header/footer blocks in the output file')
@click.option('--p-verbose/--p-no-verbose',
              default=True,
              show_default=True,
              help='print status messages to stdout while processing')
@click.option('--o-out-fp',
              required=True,
              help='the filepath where your bibtex file should be written.')
def citations(i_in_fp: FileName,
              o_out_fp: FileName,
              p_recurse: bool = False,
              p_deduplicate: bool = True,
              p_suppress_header: bool = False,
              p_verbose: bool = True):
    """
    Reports all citations from a QIIME 2 Artifact or directory of Artifacts,
    with the goal of improving and simplifying attribution of/in published
    work.

    Not for use in reporting e.g. software versions used in an analysis, as
    deduplication removes duplicate references with different plugin versions.
    """
    dag = ProvDAG(i_in_fp, verbose=p_verbose, recursive=p_recurse)
    write_citations(dag, out_fp=o_out_fp, deduplicate=p_deduplicate,
                    suppress_header=p_suppress_header)
    filename = os.path.realpath(o_out_fp)
    click.echo(f'Citations bibtex file written to {filename}')


@replay.command(no_args_is_help=True)
@click.option('--i-in-fp', required=True,
              help='filepath to a QIIME 2 Archive or directory of Archives')
@click.option('--p-recurse/--p-no-recurse',
              default=False,
              show_default=True,
              help=('if in-fp is a directory, will also search sub-directories'
                    ' when finding .qza/.qzv files to parse'))
@click.option('--p-deduplicate/--p-no-deduplicate',
              default=True,
              show_default=True,
              help=('If deduplicate, duplicate citations will be removed '
                    'heuristically, e.g. by comparing DOI fields. '
                    'This greatly reduces manual curation of reference lists, '
                    'but introduces a small risk of reference loss.'))
@click.option('--p-validate-checksums/--p-no-validate-checksums',
              default=True,
              show_default=True,
              help='check that replayed archives are intact and uncorrupted')
@click.option('--p-parse-metadata/--p-no-parse-metadata',
              default=True,
              show_default=True,
              help=('parse the original metadata captured by provenance '
                    'for review or replay'))
@click.option('--p-use-recorded-metadata/--p-no-use-recorded-metadata',
              default=False,
              show_default=True,
              help='re-use the original metadata captured by provenance')
@click.option('--p-suppress-header/--p-no-suppress-header',
              default=False,
              show_default=True,
              help='do not write header/footer blocks in the output files')
@click.option('--p-verbose/--p-no-verbose',
              default=True,
              show_default=True,
              help='print status messages to stdout while processing')
@click.option('--o-out-fp',
              required=True,
              help='the filepath where your reproduciblity supplement zipfile '
                   'should be written.')
def reproducibility_supplement(i_in_fp: FileName,
                               o_out_fp: FileName,
                               p_validate_checksums: bool = True,
                               p_parse_metadata: bool = True,
                               p_use_recorded_metadata: bool = False,
                               p_recurse: bool = False,
                               p_deduplicate: bool = True,
                               p_suppress_header: bool = False,
                               p_verbose: bool = True):
    """
    Produces a zipfile package of useful documentation for enabling in silico
    reproducibility of some QIIME 2 Result(s) from a QIIME 2 Artifact or
    directory of Artifacts, including:
    - replay scripts for all supported interfaces
    - a bibtex-formatted collection of all citations
    """
    dag = ProvDAG(i_in_fp, validate_checksums=p_validate_checksums,
                  parse_metadata=p_parse_metadata, recursive=p_recurse,
                  verbose=p_verbose)
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = pathlib.Path(tmpdir)
        filenames = {
            'python3': 'python3_replay.py',
            'cli': 'cli_replay.sh',
        }

        for usage_driver in DRIVER_NAMES:
            rel_fp = filenames[usage_driver]
            tmp_fp = pathlib.Path(tmpdir_path) / rel_fp
            replay_provdag(
                dag=dag,
                out_fp=str(tmp_fp),
                usage_driver=usage_driver,
                use_recorded_metadata=p_use_recorded_metadata,
                suppress_header=p_suppress_header,
                verbose=p_verbose)
            click.echo(f'{usage_driver} replay script written to {rel_fp}')

        tmp_fp = tmpdir_path / 'citations.bib'
        write_citations(dag, out_fp=str(tmp_fp), deduplicate=p_deduplicate,
                        suppress_header=p_suppress_header)
        click.echo('Citations bibtex file written to citations.bib')

        out_fp = pathlib.Path(os.path.realpath(o_out_fp))
        # Drop .zip suffix if any so that we don't get file.zip.zip
        if out_fp.suffix == '.zip':
            out_fp = out_fp.with_suffix('')

        shutil.make_archive(out_fp, 'zip', tmpdir)
        click.echo(f'Reproducibility package written to {out_fp}.zip')
