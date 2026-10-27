## 2026-10-27: "Not tested" notice per format and version (#145)
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
  source tool." or, for UFDR report version 7.48, "Imported without errors from three public
  test-phone packages (UFDR report version 7.48). Counts not yet compared with Cellebrite
  Reader. Not tested on your case data." (Baker Eval's wording, picked by Arsh in the owning
  thread 2026-10-27, over the spec's "Tested on public test phones (Cellebrite Reader 7.48)").
  `mabillon import` prints it too. The UFDR
  "not yet verified" coverage item and Limitations line no longer say the reader was "tested only
  on synthetic packages" (wrong since #117); they now say its record counts have not been
  compared with Cellebrite Reader's own. Every UFDR import, 7.48 included, still records
  `format_support: unverified`, starts its headline "Unverified format." and needs review (Baker
  Merge on #145); AXIOM keeps its item. The notice only discloses and never relaxes review: no
  verdict, rule, check, prompt or coverage status reads it. Importers: UFDR 0.3.2, Cellebrite Excel and PDF 0.3.2, AXIOM
  0.2.1 (payload gains `format_check`; records unchanged). Report 0.18.0. No schema change: the
  stated version lives in the coverage payload and the existing `sources.tool_version`. Spec:
  Grok Product on PR #100 (comment 6433304729).
- Where: PR #145 (branch `claude/project-thread-40jhbx`)
- Verified: `tests/test_tested_formats.py` (synthetic only): UFDR 7.48 gets the tested notice;
  UFDR 7.50, a UFDR with no version, Cellebrite Excel (7.70.0.1), Cellebrite PDF (7.70.0.1),
  AXIOM Excel (SYNTHETIC) and AXIOM XML (no version) get "Not tested" with the version as
  written; the payload and the `import.format` entry agree; an import from before 0.3.2 still
  gets its notice; overview, setup screen and report Limitations show the same notices; each
  case01 claim page shows the same notices as its report claim block; marking every source
  tested and auditing again gives the same verdicts. `make check`: see the PR.
- Open: gate 5a is still Not met (Reader-side counts not compared; #144); the 7.48 notice
  says so. The tested set matches
  report.xml's `reportVersion`, not the Physical Analyzer version the metadata states (the public
  Android 12 package states reportVersion 7.48 and PA 7.50). `docs/PILOT_GATES.md` "Pilot rule
  for gate 5" still says the banner does not exist on `d478705`; the next refresh should cite
  this PR. Not checked on a real export in this PR.
- Affects: capabilities (screen, claim page and report disclose per-format test status),
  customer-facing claims (only UFDR report version 7.48 is called tested)
- Status doc: pending: header "Report version" 0.18.0 (#145: each source's tested or "Not
  tested" notice); "Importers (main)" UFDR 0.3.2, Cellebrite Excel and PDF 0.3.2, AXIOM 0.2.1,
  each recording `format_check` and an `import.format` audit entry; section 2 step 1 and the
  limitations item "Real-data formats unverified": replace "UFDR and AXIOM imports say 'not yet
  verified' on screen and in the report; Cellebrite Excel and PDF imports carry no such notice"
  with "Every evidence source shows a format notice on the case screen, each claim page that
  rests on it and in the report (`core/ingest/tested.py`): UFDR stating reportVersion 7.48 gets
  'Imported without errors from three public test-phone packages (UFDR report version 7.48).
  Counts not yet compared with Cellebrite Reader. Not tested on your case data.';
  every other format or version gets 'Not tested: ...' with its version as written. AXIOM
  also keeps its 'not yet verified' item"; pilot gate 5 section: the pilot-rule banner exists
  on main (#145)
