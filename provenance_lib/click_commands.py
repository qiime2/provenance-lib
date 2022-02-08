import click
import os

from .replay import DRIVER_CHOICES, DRIVER_NAMES, replay_fp
from .util import FileName


@click.command()
@click.option('--i-in-fp', help='The filepath to a QIIME 2 Artifact')
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
@click.option('--o-out-fp',
              help='the filepath where your replay script should be written.')
def replay(i_in_fp: FileName, o_out_fp: FileName,
           p_usage_driver_name: DRIVER_CHOICES,
           p_validate_checksums: bool = True,
           p_parse_metadata: bool = True,
           p_use_recorded_metadata: bool = False):
    """
    One-shot replay from a filepath string, through a ProvDAG to a written
    executable
    """
    replay_fp(in_fp=i_in_fp, out_fp=o_out_fp,
              usage_driver_name=p_usage_driver_name,
              validate_checksums=p_validate_checksums,
              parse_metadata=p_parse_metadata,
              use_recorded_metadata=p_use_recorded_metadata)
    filename = os.path.realpath(o_out_fp)
    click.echo(f'Replay script written to {filename}')
