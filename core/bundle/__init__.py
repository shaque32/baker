"""Reproducibility bundle: what lies behind a case's verdicts, re-checkable without Mabillon's help.

`export.py` writes one zip for a case (`baker export-bundle`): the input file hashes, the build
and every version, each model run's identity, every model call exactly as stored (prompt and
raw output), every evidence item, expert decision and verdict, the full hash-chained audit log
(cloud attestation included), the report, and a plain-English method note. Producing one is
the examiner's choice on counsel's advice; Mabillon never makes or sends one on its own.

`verify.py` checks a bundle offline (`baker verify-bundle`): the files match their hashes, the
audit log's chain holds and matches the stored rows, each label matches the model's answer as
stored, and the verdict rules, re-applied to the recorded labels and expert decisions, give
every verdict exactly. Any edit fails loudly. Format: docs/bundle.md.
"""
