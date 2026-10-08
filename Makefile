PY ?= python3

.PHONY: install lint fmt test eval eval-model-free eval-fake eval-real eval-hostile check synth fixtures report

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

# The case01 assumption sheet: the signed copy once Arsh signs it, else the draft. Every run
# prints which one it used.
ASSUMPTION_SPEC ?= $(if $(wildcard eval/gold/case01/assumptions.jsonl),eval/gold/case01/assumptions.jsonl,eval/probe_draft/case01_assumptions.jsonl)

# The merge gate. Model-free: real assumptions (from the sheet), retrieval, checks, quote check
# and rules; a stand-in labels every retrieved record and a simulated expert accepts only the
# key evidence Arsh signed in gold (eval/simulated_expert.py). Gate: accuracy >= 0.80 and zero
# false supported on case01. The unreviewed run (0 supported by design) is reported beside it,
# then the red-team run, which fails if a structurally blocked claim goes supported.
eval: eval-model-free eval-hostile

eval-model-free:
	$(PY) -m eval.run_pipeline --mode model-free --assumption-spec $(ASSUMPTION_SPEC) --repeat
	$(PY) -m eval.run_eval --predictions eval/out/case01/model_free/unreviewed/predictions.jsonl --report-only
	$(PY) -m eval.run_eval --predictions eval/out/case01/model_free/predictions.jsonl

# The pipeline on the eval stand-ins from eval/pipeline_fakes.py; not gated.
eval-fake:
	$(PY) -m eval.run_pipeline --mode fake --repeat
	$(PY) -m eval.run_eval --predictions eval/out/case01/fake/predictions.jsonl --report-only

# The real local model (stance labeler and AI reviewer) plus the simulated expert, on a machine
# with the model installed. Gated like make eval; the unreviewed run is reported.
eval-real:
	$(PY) -m eval.run_pipeline --mode real --assumption-spec $(ASSUMPTION_SPEC) --repeat
	$(PY) -m eval.run_eval --predictions eval/out/case01/unreviewed/predictions.jsonl --report-only
	$(PY) -m eval.run_eval

# Red team: real structure, worst-case model. Fails if a structurally blocked claim goes supported.
eval-hostile:
	$(PY) -m eval.run_pipeline --mode hostile --assumption-spec $(ASSUMPTION_SPEC)

# Offline HTML claims report for the last model-free run, after the simulated expert.
report: eval-model-free
	@echo "open eval/out/case01/model_free/report.html"

check: lint test eval

# Regenerate synthetic case01 (reports, draft affidavit, draft answer key, expected database).
synth:
	$(PY) -m eval.synthetic.generate --db eval/out/case01/case01.db

fixtures:
	$(PY) -m eval.synthetic.govdocs eval/fixtures/govdoc
