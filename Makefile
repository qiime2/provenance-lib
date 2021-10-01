.PHONY: run lint test test-cov

run:
	python provenance_lib/runner.py provenance_lib/tests/data/v5_uu_emperor.qzv

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
	pyreverse -ASmy -k -o png provenance_lib/ --ignore tests

uml-full:
	pyreverse -ASmy -o png provenance_lib/ --ignore tests