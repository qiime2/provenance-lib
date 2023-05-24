# provenance-lib
Software to support scientific reproducibility, attribution, and collaboration on the QIIME 2 platform.

## About
provenance-lib parses the computational history ( or "provenance") of QIIME 2 results into a directed graph structure, supporting study validation and automation, and improving collaboration on and reporting of QIIME 2 analyses.

provenance-lib lets you:
- generate executable scripts for your preferred QIIME 2 interface,
  allowing users to "replay" prior analyses
- automate the translation of analyses from one interface to another
- report the citations, computational actions, and software versions used
  during an analysis for publication

## Installation
As of QIIME 2 2023.5, provenance-lib is installed as part of the QIIME 2 core distribution. If you have installed QIIME 2 2023.5 or later, provenance-lib is already installed. If you're using an earlier version of QIIME 2, we recommend upgrading to QIIME 2 2023.5 or later to use provenance-lib.

## Usage

We are currently planning changes to how users can access provenance-lib to make this more similar to how other QIIME 2 tools are used. The following usage guidelines will be changing slightly in a future release.

### Use - CLI
provenance-lib offers tools for the command line under the name `replay`.

`replay --help` renders a list of available commands.

`replay some-command --help` renders command-specific helptext for `some-command`. So does `replay some-command` with no arguments.

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

See the help text for complete details, including information on which parameters are required and which are optional and/or have default values.

### Use - Python API
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

More power and flexibility are available to users of the Python API, through the direct creation and manipulation of provenance digraphs (`ProvDAG` objects).

The basic workflow proceeds as follows:
- `import provenance_lib`
- create ProvDAG objects from QIIME 2 archives
- combine or manipulate these ProvDAGs as needed
- Pass your ProvDAG to tools from the `replay` module
  (`replay_provenance`, `replay_citations`, etc.) to produce your desired results.

A Jupyter Notebook containing additional examples of Python API usage is included in this repository's `docs` directory. To access it, clone or otherwise download the repository, navigate into `docs`, and open the notebook with `jupyter notebook` or your preferred `.ipnyb` client software.

Running the notebook commands as is will write files to `docs`, and will have no impact on the functionality of the software itself.

## Additional documentation
- [A tutorial](https://forum.qiime2.org/t/provenance-replay-alpha-release-and-tutorial/23279) is available on the QIIME 2 forum.
- A video walkthrough is available on the [QIIME 2 YouTube channel](https://youtu.be/KMsacdbQ8hA).

## Questions/User Support?
Please raise user support questions on the [QIIME 2 Forum](https://forum.qiime2.org/).

Please *do not* raise user support questions as issues on the Github repository. They may be closed without response as off topic.

## Contributing
Please open an issue to report bugs, request features, or propose a new feature or enhancement. Contributions will be warmly welcomed.

## Citing

If you use provenance-lib in published work, please cite [our pre-print](https://doi.org/10.48550/arXiv.2305.11198):

```
Keefe, Christopher R., Matthew R. Dillon, Chloe Herman, Mary Jewell, Colin V. Wood, Evan Bolyen, and J. Gregory Caporaso. 2023.
“Facilitating Bioinformatics Reproducibility.” arXiv [q-bio.QM]. arXiv.
https://doi.org/10.48550/arXiv.2305.11198.
```

```
@misc{keefe2023facilitating,
      title={Facilitating Bioinformatics Reproducibility},
      author={Christopher R. Keefe and Matthew R. Dillon and Chloe Herman and Mary Jewell and Colin V. Wood and Evan Bolyen and J. Gregory Caporaso},
      year={2023},
      eprint={2305.11198},
      archivePrefix={arXiv},
      primaryClass={q-bio.QM}
}
```
