#!/usr/bin/env python
import os


def tab_complete_on_conda_env_activation():
    base = (os.environ['CONDA_PREFIX'])
    fp = os.path.join(base,
                      'etc/conda/activate.d/activate-replay-completion.sh')
    payload = 'if [ -n "${BASH_VERSION-}" ]; then\nsource tab-replay\nfi\n'
    with open(fp, 'w') as fh:
        fh.write(payload)


if __name__ == '__main__':
    tab_complete_on_conda_env_activation()
