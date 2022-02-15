import click
import os

from .parse import ProvDAG
from .replay import DRIVER_CHOICES, DRIVER_NAMES, replay_fp, write_citations
from .util import FileName


@click.group()
def replay():
    pass  # pragma: no cover


@replay.command(no_args_is_help=True)
@click.option('--i-in-fp', required=True,
              help='The filepath to a QIIME 2 Artifact')
@click.option('--p-usage-driver-name',
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
              help=('parse the original metadata captured by provenance'
                    'for review or replay'))
@click.option('--p-use-recorded-metadata/--p-no-use-recorded-metadata',
              default=False,
              show_default=True,
              help='re-use the original metadata captured by provenance')
@click.option('--p-verbose/--p-no-verbose',
              default=False,
              show_default=True,
              help='print status messages to stdout while processing')
@click.option('--o-out-fp',
              required=True,
              help='the filepath where your replay script should be written.')
def provenance(i_in_fp: FileName, o_out_fp: FileName,
               p_usage_driver_name: DRIVER_CHOICES,
               p_validate_checksums: bool = True,
               p_parse_metadata: bool = True,
               p_use_recorded_metadata: bool = False,
               p_verbose: bool = False):
    """
    Replay provenance from a QIIME 2 Artifact filepath to a written executable
    TODO: accept fp argument for recorded_metadata output folder
    """
    replay_fp(in_fp=i_in_fp, out_fp=o_out_fp,
              usage_driver_name=p_usage_driver_name,
              validate_checksums=p_validate_checksums,
              parse_metadata=p_parse_metadata,
              use_recorded_metadata=p_use_recorded_metadata,
              verbose=p_verbose)
    filename = os.path.realpath(o_out_fp)
    click.echo(f'Replay script written to {filename}')


@replay.command(no_args_is_help=True)
@click.option('--i-in-fp', required=True,
              help='The filepath to a QIIME 2 Artifact')
@click.option('--p-deduped/--p-no-deduped',
              default=True,
              show_default=True,
              help=('If deduped, collect_citations will attempt some heuristic'
                    'deduplication of documents, e.g. by comparing DOI fields,'
                    ' which may reduce manual curation of reference lists.'))
@click.option('--p-verbose/--p-no-verbose',
              default=False,
              show_default=True,
              help='print status messages to stdout while processing')
@click.option('--o-out-fp',
              required=True,
              help='the filepath where your bibtex file should be written.')
def citations(i_in_fp: FileName, o_out_fp: FileName, p_deduped: bool = True,
              p_verbose: bool = False):
    """
    Report all citations from a QIIME 2 Artifact.
    """
    dag = ProvDAG(i_in_fp, verbose=p_verbose)
    write_citations(dag, out_fp=o_out_fp, deduped=p_deduped)
    filename = os.path.realpath(o_out_fp)
    click.echo(f'Citations bibtex file written to {filename}')
