.PHONY: run lint test test-cov

run:
	replay provenance \
	--i-in-fp provenance_lib/tests/data/v5_uu_emperor.qzv \
	--p-verbose \
	--o-out-fp ./replay_scripts/sample_replay.sh

run-py:
	replay provenance \
	--i-in-fp provenance_lib/tests/data/v5_uu_emperor.qzv \
	--p-usage-driver python3 \
	--p-verbose \
	--o-out-fp ./replay_scripts/sample_replay.py

run-cite:
	replay citations \
	--i-in-fp provenance_lib/tests/data/v5_uu_emperor.qzv \
	--p-verbose \
	--o-out-fp ./replay_scripts/sample-citations.bib

cite-everything:
	replay citations \
	--i-in-fp ~/data/alzmice/ileum \
	--p-recurse \
	--p-verbose \
	--o-out-fp ./replay_scripts/every-citation-2.bib

# TODO: install and dev targets
# Conda recipe will use make install and will copy the tab-complete language
# https://github.com/qiime2/q2cli/blob/master/hooks/50_activate_q2cli_tab_completion.sh
# from /bin or /scripts over to activate.d
# https://github.com/qiime2/q2cli/blob/ab0afe7917977c1272cad2d334607f7e6b1f6e41/ci/recipe/meta.yaml#L12

# NOTE: Dev will also need to install testing deps, and mypy should prob. move
# over to extras. These are all referenced by the [dev] key in extras
# dev:
# 	pip install -e .[dev]

lint:
	flake8

test: lint
	py.test

test-cov: lint
	pytest --cov-report=term-missing --cov=provenance_lib

mypy:
	mypy -p provenance_lib

uml:
	# pyreverse is packaged with pylint, and installable with `pip install pylint`
	pyreverse -ASmy -k -o puml provenance_lib/ --ignore tests -p packages

uml-full:
	pyreverse -ASmy --colorized -o puml provenance_lib/ --ignore tests -p classes

uml-archive-parser:
	pyreverse -ASmy --colorized -o puml provenance_lib/_archive_parser.py

dev:
	pip install -e .

clean:
	rm -r recorded_metadata replay_scripts
