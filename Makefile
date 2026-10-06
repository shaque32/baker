PY ?= python3

.PHONY: install lint fmt test eval check

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
