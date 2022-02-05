# flake8: noqa
import pathlib
import sys
import zipfile

import yaml

sys.path.append('/home/chris/src/provenance_py')

if __name__ == "__main__" and __package__ is None:
    __package__ = "provenance_lib"

from .parse import ProvDAG, Config
from .replay import replay_provdag

if __name__ == '__main__':
    # To begin, we'll read in exactly one fp
    if len(sys.argv) != 2:
        raise ValueError('Please pass one filepath to a QIIME 2 Archive')

    archive_fp = sys.argv[1]
    dummy_DAG = ProvDAG(archive_fp)

    # We're only parsing one Artifact here, so need to grab the only term. uuid
    terminal_uuid, *_ = dummy_DAG.terminal_uuids
    deets = dummy_DAG.get_node_data(terminal_uuid).action._action_details
    plurg = deets['plugin']
    ackshun = deets['action']

    print(f'{repr(dummy_DAG)}')

    terminal_node = next(iter(dummy_DAG.terminal_nodes))
    print(f'{terminal_node._result_md}')
    print(f'- was made by q2-{plurg} {ackshun}')
    print(f'- contains prov. data from {len(dummy_DAG)}'
          ' QIIME 2 Results, mostly ancestors')
    # print(dummy_DAG._prov_digraph)

    print(f'\nIts prov DAG looks like\n{dummy_DAG}')

    print(dummy_DAG.predecessors('ffb7cee3-2f1f-4988-90cc-efd5184ef003'))
    # The following is not trustworthy bc _parents may not be updated
    print(
          dummy_DAG
          .get_node_data('ffb7cee3-2f1f-4988-90cc-efd5184ef003')._parents)
    print('#########################################')

    out_fp = pathlib.Path(
        '/home/chris/src/provenance_py/provenance_lib/test_outputs/rendered.txt')
    replay_provdag(dag=dummy_DAG, out_fp=out_fp, usage_driver='python3',
                   use_recorded_metadata=False)

    out_fp = pathlib.Path(
        '/home/chris/src/provenance_py/provenance_lib/test_outputs/cli_rendered.txt')
    replay_provdag(dag=dummy_DAG, out_fp=out_fp, usage_driver='cli',
                   use_recorded_metadata=False)

    mixed = ProvDAG('/home/chris/src/provenance_py/provenance_lib/tests/data/mixed_v0_v1_uu_emperor.qzv')
    out_fp = pathlib.Path(
        '/home/chris/src/provenance_py/provenance_lib/test_outputs/mixed.txt')
    replay_provdag(dag=mixed, out_fp=out_fp, usage_driver='python3',
                   use_recorded_metadata=False)
    out_fp = pathlib.Path(
        '/home/chris/src/provenance_py/provenance_lib/test_outputs/mixed_cli.txt')
    replay_provdag(dag=mixed, out_fp=out_fp, usage_driver='cli',
                   use_recorded_metadata=False)

    out_fp = pathlib.Path(
        '/home/chris/src/provenance_py/provenance_lib/test_outputs/joined.txt')
    v0_uuid = '0b8b47bd-f2f8-4029-923c-0e37a68340c3'
    tbl_uuid = '89af91c0-033d-4e30-8ac4-f29a3b407dc1'
    tbl = ProvDAG('/home/chris/src/provenance_py/provenance_lib/tests/data/v0_table.qza')
    qzv = ProvDAG('/home/chris/src/provenance_py/provenance_lib/tests/data/v0_uu_emperor.qzv')
    joined = ProvDAG.union([tbl, qzv])
    replay_provdag(dag=joined, out_fp=out_fp, usage_driver='cli',
                   use_recorded_metadata=False)
