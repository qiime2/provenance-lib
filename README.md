# provenance_lib
Software to support scientific reproducibility, attribution,
and collaboration on the QIIME 2 platform.

## About
provenance_lib parses the computational history ( or "provenance") of QIIME 2
results into a directed graph structure, supporting study validation and automation,
and improving collaboration on and reporting of QIIME 2 analyses.

provenance_lib lets you:
- generate executable scripts for your preferred QIIME 2 interface,
  allowing users to "replay" prior analyses
- automate the translation of analyses from one interface to another
- report the citations, computational actions, and software versions used
  during an analysis for publication

## Installation
- `git clone` or otherwise download this repo
- [Install QIIME 2](https://docs.qiime2.org/2022.2/install/) within a conda
  environment. QIIME 2 versions 2021.11 and newer are supported.
- `conda activate` your QIIME 2 environment
- `pip install .` from the repo root directory

## BASH tab completion
To activate tab-completion automatically whenever you activate your conda environment,
run `activate-replay-completion.py` while the environment is active. You should
only have to do this once.
To activate tab-completion for one session only,
`source tab-replay` from your active conda env.

Other shells (zsh, fish) are not supported at this time.
Please raise an issue if this matters to you.

## Use - CLI
provenance_lib offers tools for the command line under the name `replay`.

`replay --help` renders a list of available commands.

`replay some-command --help` renders command-specific helptext for `some-command`.
So does `replay some-command` with no arguments.

The basic command structure is as follows:
```
replay <command-name> [<parameter-name> <argument-value>] ...
```
For example, you can produce a list of all citations for an analysis with:
```
replay citations \
  --i-in-fp ~/data/my_q2_data_dir \
  --o-out-fp ./my_analysis_citations.bib
```

See the helptext for complete details, including information on which parameters
are required and which are optional and/or have default values.

## Use - Python API
Basic example:
```python
import provenance_lib

# helptext for the package
help(provenance_lib)

# command-specific helptext
help(provenance_lib.replay_supplement)

# help alternative for iPython and Jupyter Notebook only
? provenance_lib.replay_supplement

# Generate a reproducibility supplement for the current directory's
# Results including all of its subdirectories recursively
provenance_lib.replay_supplement(
    '.', './reproducibility-supplement.zip', recurse=True)
```

More power and flexibility are available to users of the Python API.
The basic workflow proceeds as follows:
- `import provenance_lib`
- create ProvDAG objects from QIIME 2 archives
- combine or manipulate these ProvDAGs as needed
- Pass your ProvDAG to tools from the `replay` module
  (`replay_provenance`, `replay_citations`, etc.) to produce your desired results.

A Jupyter Notebook containing additional examples of Python API usage is
included in this repository's `docs` directory.
To access it, clone or otherwise download the repository,
navigate into `docs`, and open the notebook with `jupyter notebook` or your
preferred `.ipnyb` client software.

Running the notebook commands as is will write files to `docs`,
and will have no impact on the functionality of the software itself.

## Additional documentation
- [A tutorial](https://forum.qiime2.org) will be available shortly on the QIIME 2 forum.
- A video walkthrough will be available shortly on the [QIIME 2 YouTube channel](https://www.youtube.com/c/QIIME2).
- This tool can be found on the [QIIME 2 Library](https://library.qiime2.org/plugins/provenance_lib/43/)

## Questions/User Support?
Please raise user support questions in the [Community Plugin Support category
of the QIIME 2 Forum](https://forum.qiime2.org/c/community-plugin-support/).
Mentioning me in your post, @ChrisKeefe,
will help me respond to your questions quickly.

Please *do not* raise user support questions as issues on the Github repository.
They may be closed without response as off topic.

## Contributing
Please open an issue to report bugs, request features, or propose a new feature or enhancement.
Contributions will be warmly welcomed.
