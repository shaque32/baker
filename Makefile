PY ?= python3

.PHONY: install lint fmt test eval eval-fake eval-real eval-hostile check synth fixtures report

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

# The merge gate scores eval/out/case01/predictions.jsonl, which only the real pipeline writes.
# eval-fake runs the whole pipeline on stand-ins first (twice, to prove runs repeat) and prints
# its scores without gating, so every merge exercises the full pipeline end to end.
eval: eval-fake
	$(PY) -m eval.run_eval

eval-fake:
	$(PY) -m eval.run_pipeline --mode fake --repeat
	$(PY) -m eval.run_eval --predictions eval/out/case01/fake/predictions.jsonl --report-only

# Product components; fails with the list of modules not built yet.
eval-real:
	$(PY) -m eval.run_pipeline --mode real --repeat
	$(PY) -m eval.run_eval
	$(PY) -m eval.run_pipeline --mode real --reviewer none
	$(PY) -m eval.run_eval --predictions eval/out/case01/no_reviewer/predictions.jsonl --report-only

# Red team: real structure, worst-case model. Fails if a structurally blocked claim goes supported.
# Uses the case01 assumption spec (draft until signed; then it moves under eval/gold/case01/).
ASSUMPTION_SPEC ?= eval/probe_draft/case01_assumptions.jsonl
eval-hostile:
	$(PY) -m eval.run_pipeline --mode hostile --assumption-spec $(ASSUMPTION_SPEC)

# Offline HTML claims report for the last fake run.
report: eval-fake
	@echo "open eval/out/case01/fake/report.html"

check: lint test eval

# Regenerate synthetic case01 (reports, draft affidavit, draft answer key, expected database).
synth:
	$(PY) -m eval.synthetic.generate --db eval/out/case01/case01.db

fixtures:
	$(PY) -m eval.synthetic.govdocs eval/fixtures/govdoc
