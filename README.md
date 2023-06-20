# QIIME 2 Provenance Replay
Software to support scientific reproducibility, attribution, and collaboration on the QIIME 2 platform.

## About
The provenance-lib software provides the QIIME 2 Provenance Replay functionality, which parses the computational history ( or "provenance") of QIIME 2 results into a directed graph structure, and generates new executable code that can be used for reproducing or replicating an analysis. This supports study validation and automation, and is intended to improve collaboration on and reporting of QIIME 2 analyses.

provenance-lib lets you:
- generate executable scripts for your preferred QIIME 2 interface,
  allowing users to "replay" prior analyses
- automate the translation of analyses from one interface to another
- report the citations, computational actions, and software versions used
  during an analysis for publication

## Installation
As of QIIME 2 2023.5, provenance-lib is installed as part of the QIIME 2 core distribution. If you have installed QIIME 2 2023.5 or later, provenance-lib is already installed. If you're using an earlier version of QIIME 2, we recommend upgrading to QIIME 2 2023.5 or later to use provenance-lib.

Instructions for installing the latest version of QIIME 2 can be found by navigating to https://docs.qiime2.org, and following the link to _Installing QIIME 2_.

## Usage

We are currently planning changes to how users can access provenance-lib to make this more similar to how other QIIME 2 tools are used. The following usage guidelines will be changing slightly in a future release.

### Command line interface
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

### Python 3 API
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

## Brief tutorial: using the command line to replay provenance

### Running provenance replay

1. First, activate your QIIME 2 2023.5 or later conda environment (e.g., using `conda activate qiime2-2023.5`).
2. Navigate into a directory with some QIIME 2 Results in it (i.e. `.qza` and `.qzv` files).

   If you don't have any of your own QIIME 2 results, you can download some from the QIIME 2 [_Moving Pictures_ tutorial](https://docs.qiime2.org/2023.5/tutorials/moving-pictures/). The following commands will download a couple of the final visualizations generated in that tutorial:

   ```
   wget https://docs.qiime2.org/2023.5/data/tutorials/moving-pictures/core-metrics-results/unweighted_unifrac_emperor.qzv
   wget https://docs.qiime2.org/2023.5/data/tutorials/moving-pictures/alpha-rarefaction.qzv
   ```

3. Run the following command from the directory containing your QIIME 2 results. It will produce a zip archive called `reproducibility-supplement.zip`

   ```
   replay supplement \
     --i-in-fp . \
     --o-out-fp ./reproducibility-supplement.zip
   ```

   Note that parsing many QIIME 2 Results can take a long time. Expect ~10 minutes for 500 Results on a decent contemporary laptop.

### Inspecting provenance replay results
The command above will generate reproducibility documentation you can include as supplemental material alongside the paper. Unzip it to find the following:
1. a directory of metadata `.tsv` files called `recorded_metadata`
2. a python3 replay script written to `python3_replay.py`
3. a bash (i.e., command line) replay script written to `cli_replay.sh`
4. a citations bibtex file written to `citations.bib` including citations for all QIIME 2 steps that were applied.

### Use --p-recurse to include subdirectories
If your QIIME 2 Results are organized in a folder with many subfolders, you can use the `--p-recurse` flag to have `replay` generate a reproducibility supplement for all of the files in the current working directory (`./`) and its sub-folders:

```
replay supplement \
  --i-in-fp . \
  --p-recurse \
  --o-out-fp ./reproducibility-supplement.zip
```

Without `--p-recurse`, you will report on only the Results in the current directory.

## Additional documentation
- [A detailed tutorial](https://forum.qiime2.org/t/provenance-replay-alpha-release-and-tutorial/23279) is available on the QIIME 2 forum, and can be run using the same results that were downloaded for the _Brief Tutorial_ above.
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
