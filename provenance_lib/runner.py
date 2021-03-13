import sys

import parse

if __name__ == '__main__':
    # To begin, we'll read in exactly one fp
    if len(sys.argv) != 2:
        raise ValueError('Please pass one filepath to a QIIME 2 Archive')

    archive_fp = sys.argv[1]
    dummy_archive = parse.Archive(archive_fp)

    r_uuid = dummy_archive.root_uuid
    deets = dummy_archive.get_result(r_uuid)._action._action_details
    plurg = deets['plugin']
    ackshun = deets['action']

    print(f'\n{dummy_archive._archive_md}')
    print(f'- was made by q2-{plurg} {ackshun}')
    print(f'- contains prov. data from {dummy_archive._number_of_results}'
          ' QIIME 2 Results, mostly ancestors')
    # print(dummy_archive._archive_contents)

    dummy_tree = parse.ProvTree(dummy_archive)
    print(f'- has parents: {dummy_tree.root.parents}')
    print('- which have parents:')
    for parent in dummy_tree.root.parents:
        print(f'\t- par: {parent.uuid} gps: {parent.parents}')
    print('\t- etcetera, etcetera')

    print(f'\nIts prov tree looks like {dummy_tree}')
