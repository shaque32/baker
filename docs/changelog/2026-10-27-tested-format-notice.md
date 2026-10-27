## 2026-10-27: "Not tested" notice per format and version (#PR)
- Changed: the pilot rule from #144 (first pilot limited to UFDR from Cellebrite Reader 7.48;
  everything else shows "not tested") is now in code. `core/ingest/tested.py` holds the one
  tested set: a Cellebrite UFDR whose report.xml states `reportVersion` 7.48, matched exactly as
  written; a missing or blank version is not tested. Each import records its format, the version
  the export states (a UFDR's `reportVersion`; the summary's tool version for Cellebrite Excel,
  PDF and AXIOM) and whether it is tested, in the coverage payload (`format_check`) and in a new
  audit-log entry (`import.format`). The case overview, the setup screen's file list, every claim
  page that rests on the source (its evidence, what its checks searched, the records they cite),
  the report's Limitations and each such claim in the report print the same notice: "Not tested:
  <format> <version as written> has not been tested with Mabillon. Check results against the
  source tool." or, for UFDR report version 7.48, "Tested on public test phones (Cellebrite
  Reader 7.48). Not tested on your case data." `mabillon import` prints it too. The stale UFDR
  "tested only on synthetic packages" item and Limitations line are removed, and a UFDR's coverage
  headline no longer starts "Unverified format." (UFDR still records `format_support:
  unverified`; AXIOM keeps its "not yet verified" item). The notice only discloses: no verdict,
  rule, check or prompt reads it. Importers: UFDR 0.3.2, Cellebrite Excel and PDF 0.3.2, AXIOM
  0.2.1 (payload gains `format_check`; records unchanged). Report 0.18.0. No schema change: the
  stated version lives in the coverage payload and the existing `sources.tool_version`. Spec:
  Grok Product on PR #100 (comment 6433304729).
- Where: branch `claude/project-thread-40jhbx`
- Verified: `tests/test_tested_formats.py` (synthetic only): UFDR 7.48 gets the tested notice;
  UFDR 7.50, a UFDR with no version, Cellebrite Excel (7.70.0.1), Cellebrite PDF (7.70.0.1),
  AXIOM Excel (SYNTHETIC) and AXIOM XML (no version) get "Not tested" with the version as
  written; the payload and the `import.format` entry agree; an import from before 0.3.2 still
  gets its notice; overview, setup screen and report Limitations show the same notices; each
  case01 claim page shows the same notices as its report claim block; marking every source
  tested and auditing again gives the same verdicts. `make check`: see the PR.
- Open: the tested notice says "Tested on public test phones" while gate 5a is still Not met
  (Reader-side counts not compared; #144); the wording is the spec's. The tested set matches
  report.xml's `reportVersion`, not the Physical Analyzer version the metadata states (the public
  Android 12 package states reportVersion 7.48 and PA 7.50). `docs/PILOT_GATES.md` "Pilot rule
  for gate 5" still says the banner does not exist on `d478705`; the next refresh should cite
  this PR. Not checked on a real export in this PR.
- Affects: capabilities (screen, claim page and report disclose per-format test status),
  customer-facing claims (only UFDR report version 7.48 is called tested)
- Status doc: pending: header "Report version" 0.18.0 (#PR: each source's tested or "Not
  tested" notice); "Importers (main)" UFDR 0.3.2, Cellebrite Excel and PDF 0.3.2, AXIOM 0.2.1,
  each recording `format_check` and an `import.format` audit entry; section 2 step 1 and the
  limitations item "Real-data formats unverified": replace "UFDR and AXIOM imports say 'not yet
  verified' on screen and in the report; Cellebrite Excel and PDF imports carry no such notice"
  with "Every evidence source shows a format notice on the case screen, each claim page that
  rests on it and in the report (`core/ingest/tested.py`): UFDR stating reportVersion 7.48 gets
  'Tested on public test phones (Cellebrite Reader 7.48). Not tested on your case data.';
  every other format or version gets 'Not tested: ...' with its version as written. AXIOM
  also keeps its 'not yet verified' item"; pilot gate 5 section: the pilot-rule banner exists
  on main (#PR)
