# Provenance Replay Alpha Release and Tutorial

Hi hi! I'm excited to announce the alpha release of `provenance_lib`, software
for scientific reproducibility, attribution, and collaboration on the QIIME 2
platform.

## About

`provenance_lib` parses the computational history (i.e. the "provenance") of QIIME 2
Results, letting you:

* generate executable scripts for your preferred QIIME 2 interface, allowing
  users to "replay" prior analyses
* report all citations from a QIIME 2 analysis, so creating your reference
  section is easy
* produce reproducibility supplements for publication or collaboration,
  supporting the reproducibility of your QIIME 2 work

## Installation
- [Install QIIME 2](https://docs.qiime2.org/2022.2/install/) within a conda
  environment. QIIME 2 versions 2021.11 and newer are supported.
- `conda activate` your QIIME 2 environment
- `git clone` or otherwise download `provenance_lib` from the [github repository](https://github.com/qiime2/provenance-lib)
- navigate to the root directory you just downloaded (e.g. `cd provenance-lib`)
- `pip install .`

## Basic Use - CLI
`provenance_lib` offers tools for the command line under the name `replay`.

`replay --help` renders a list of available commands.
Available commands include at least `provenance`, `citations`, and
`supplement`.

`replay <some-command> --help` renders command-specific helptext for `some-command`.
So does `replay <some-command>` with no arguments.

The basic command structure is as follows:
```
replay <command-name> [<parameter-name> <argument-value>] ...
```
For example, you can produce a list of all citations for an analysis with:

# TODO: Make this relevant to some data directory
```
replay citations \
  --i-in-fp ~/data/my_q2_data_dir \
  --o-out-fp ./my_analysis_citations.bib
```

# TODO: MODIFY
See the helptext for complete details, including information on which commands
are required and which are optional and/or have default values.

## Basic Use - Python API
, but basic
use follows a similar pattern to the CLI.

The basic workflow proceeds as follows:
- `import provenance_lib`
- run a command

More power and flexibility are available to users of the Python API, through
interaction with the underlying ProvDAG data structure.
ProvDAG objects are limited wrappers around [`networkx.DiGraph`](TODO: insert link).


A few key DiGraph methods are re-implemented on ProvDAG, but for
- create ProvDAG objects from QIIME 2 archives
- combine or manipulate these ProvDAGs as needed
- Pass your ProvDAG to tools from the `replay` module
  (`replay_provenance`, `replay_citations`, etc.) to produce your desired results.

# TODO: MODIFY
Full API documentation pending. Thanks for your patience!

## Questions/User Support?
Please raise user support questions in the [Community Plugin Support category
of the QIIME 2 Forum](https://forum.qiime2.org/c/community-plugin-support/).
Mentioning me in your post, @ChrisKeefe,
will help me respond to your questions quickly.

Please *do not* raise user support questions as issues on the Github repository.
They may be closed without response as off topic.

## Contributing
Please [open an issue](https://github.com/qiime2/provenance-lib/issues) to
report bugs, request features, or propose a new feature or enhancement.
Contributions will be warmly welcomed.
