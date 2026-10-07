PY ?= python3

.PHONY: install lint fmt test eval check synth fixtures

install:
	$(PY) -m pip install -e ".[dev]"

lint:
	ruff check .
	ruff format --check .

fmt:
	ruff check --fix .
	ruff format .

test:
	$(PY) -m pytest -q

eval:
	$(PY) -m eval.run_eval

check: lint test eval

# Regenerate synthetic case01 (reports, draft affidavit, draft answer key, expected database).
synth:
	$(PY) -m eval.synthetic.generate --db eval/out/case01/case01.db

fixtures:
	$(PY) -m eval.synthetic.govdocs eval/fixtures/govdoc
