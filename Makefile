.PHONY: run lint test test-cov

run:
	python provenance_lib/runner.py provenance_lib/tests/data/unweighted_unifrac_emperor.qzv

lint:
	flake8

test: lint
	py.test

test-cov: lint
	pytest --cov-report=term-missing --cov=provenance_lib