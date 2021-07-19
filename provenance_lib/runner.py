# flake8: noqa
import sys
import zipfile

import yaml

sys.path.append('/home/chris/src/provenance_py')

if __name__ == "__main__" and __package__ is None:
    __package__ = "provenance_lib"

from .parse import ProvDAG

if __name__ == '__main__':
    # To begin, we'll read in exactly one fp
    if len(sys.argv) != 2:
        raise ValueError('Please pass one filepath to a QIIME 2 Archive')

    archive_fp = sys.argv[1]
    dummy_DAG = ProvDAG(archive_fp)

    r_uuid = dummy_DAG.root_uuid
    deets = dummy_DAG.get_result(r_uuid).action._action_details
    plurg = deets['plugin']
    ackshun = deets['action']

    print(f'{repr(dummy_DAG)}')
    print(f'{dummy_DAG._archive_md}')
    print(f'- was made by q2-{plurg} {ackshun}')
    print(f'- contains prov. data from {dummy_DAG._num_results}'
          ' QIIME 2 Results, mostly ancestors')
    # print(dummy_DAG._archive_contents)

    print(f'\nIts prov DAG looks like\n{dummy_DAG}')

    print('#########################################')
    print(dummy_DAG.nodes['ffb7cee3-2f1f-4988-90cc-efd5184ef003']['parents'])