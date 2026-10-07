-- Baker canonical schema v0.2.0 (matches CONTRACTS_VERSION in core/contracts.py).
-- HUMAN-OWNED. Agents: propose changes in PROPOSED_CHANGES.md.
-- One SQLite database per case.
-- Conventions:
--   * ids are TEXT, built deterministically from source and locator (stable across re-imports).
--   * every evidence row has (source_id, locator) = its source_ref back to the original artifact.
--   * times: ts_utc is ISO 8601 UTC ('2026-03-05T02:31:00Z'); ts_offset_min is the UTC offset
--     printed with the value (NULL if none). For reports this can be a display setting, not the
--     phone's zone; the phone's zone is devices.timezone. ts_raw is the value as it appeared.
--   * enum values here must match the enums in core/contracts.py (tests enforce this).
--   * audit-side ids follow the id functions in core/contracts.py.
--   * evidence_reviews, model_calls and audit_log are append-only (triggers at the end).

PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------- inputs

CREATE TABLE sources (
    id               TEXT PRIMARY KEY,
    kind             TEXT NOT NULL CHECK (kind IN ('ufdr', 'cellebrite_excel', 'cellebrite_pdf',
                         'cellebrite_html', 'axiom', 'raw_zip', 'govdoc', 'synthetic')),
    fidelity         TEXT NOT NULL CHECK (fidelity IN ('full_extraction', 'curated_report', 'unknown')),
    extraction_type  TEXT NOT NULL CHECK (extraction_type IN ('logical', 'file_system', 'physical',
                         'not_applicable', 'unknown')),
    file_name        TEXT NOT NULL,
    sha256           TEXT NOT NULL,
    tool_name        TEXT,
    tool_version     TEXT,
    extracted_at_utc TEXT,
    imported_at_utc  TEXT NOT NULL
);

CREATE TABLE source_coverage (
    source_id        TEXT PRIMARY KEY REFERENCES sources(id),
    importer         TEXT NOT NULL,     -- 'cellebrite_excel', 'cellebrite_pdf', ...
    importer_version TEXT NOT NULL,
    payload_json     TEXT NOT NULL      -- tables read, rows skipped, unknown columns, time-zone
                                        -- handling, deleted-flag coverage, notes
);

-- ---------------------------------------------------------------- evidence side

CREATE TABLE devices (
    id         TEXT PRIMARY KEY,
    source_id  TEXT NOT NULL REFERENCES sources(id),
    locator    TEXT NOT NULL,
    label      TEXT NOT NULL,
    model      TEXT,
    os_version TEXT,
    timezone   TEXT
);

CREATE TABLE accounts (
    id         TEXT PRIMARY KEY,
    source_id  TEXT NOT NULL REFERENCES sources(id),
    locator    TEXT NOT NULL,
    device_id  TEXT REFERENCES devices(id),
    app        TEXT NOT NULL,
    identifier TEXT NOT NULL,     -- handle, phone number or email as it appears
    display_name TEXT
);

CREATE TABLE persons (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    created_by TEXT NOT NULL      -- 'expert:<name>' or 'govdoc:<claim_id>'; never the model
);

CREATE TABLE identity_links (
    id         TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id),
    person_id  TEXT NOT NULL REFERENCES persons(id),
    status     TEXT NOT NULL CHECK (status IN ('proposed', 'confirmed', 'rejected', 'unresolved')),
    tier       TEXT NOT NULL CHECK (tier IN ('observed', 'derived', 'inferred', 'ai_reviewed', 'confirmed')),
    basis      TEXT NOT NULL,
    decided_by TEXT,
    decided_at_utc TEXT
);

CREATE TABLE threads (
    id         TEXT PRIMARY KEY,
    source_id  TEXT NOT NULL REFERENCES sources(id),
    locator    TEXT NOT NULL,
    device_id  TEXT REFERENCES devices(id),
    app        TEXT NOT NULL,
    title      TEXT
);

CREATE TABLE messages (
    id              TEXT PRIMARY KEY,
    source_id       TEXT NOT NULL REFERENCES sources(id),
    locator         TEXT NOT NULL,
    thread_id       TEXT NOT NULL REFERENCES threads(id),
    sender_account_id TEXT REFERENCES accounts(id),
    sender_raw      TEXT,            -- sender text exactly as the source showed it
    direction       TEXT NOT NULL CHECK (direction IN ('incoming', 'outgoing', 'unknown')),
    ts_utc          TEXT,
    ts_offset_min   INTEGER,
    ts_raw          TEXT,
    body            TEXT NOT NULL,   -- original text; the only citable text
    lang            TEXT,
    deleted_flag    INTEGER CHECK (deleted_flag IN (0, 1)),  -- NULL = source did not say
    bookmarked      INTEGER CHECK (bookmarked IN (0, 1))     -- examiner tag, for the selection audit
);

CREATE TABLE message_recipients (
    message_id TEXT NOT NULL REFERENCES messages(id),
    account_id TEXT NOT NULL REFERENCES accounts(id),
    raw        TEXT,                 -- recipient text exactly as the source showed it
    PRIMARY KEY (message_id, account_id)
);

CREATE TABLE translations (
    id           TEXT PRIMARY KEY,
    message_id   TEXT NOT NULL REFERENCES messages(id),
    target_lang  TEXT NOT NULL,
    text         TEXT NOT NULL,
    model_run_id TEXT NOT NULL REFERENCES model_runs(id)
);

CREATE TABLE attachments (
    id         TEXT PRIMARY KEY,
    source_id  TEXT NOT NULL REFERENCES sources(id),
    locator    TEXT NOT NULL,
    message_id TEXT REFERENCES messages(id),
    file_name  TEXT,
    mime_type  TEXT,
    sha256     TEXT
);

CREATE TABLE calls (
    id            TEXT PRIMARY KEY,
    source_id     TEXT NOT NULL REFERENCES sources(id),
    locator       TEXT NOT NULL,
    device_id     TEXT REFERENCES devices(id),
    app           TEXT NOT NULL,
    from_account_id TEXT REFERENCES accounts(id),
    to_account_id   TEXT REFERENCES accounts(id),
    direction     TEXT NOT NULL CHECK (direction IN ('incoming', 'outgoing', 'missed', 'unknown')),
    ts_utc        TEXT,
    ts_offset_min INTEGER,
    ts_raw        TEXT,
    duration_s    INTEGER,
    deleted_flag  INTEGER CHECK (deleted_flag IN (0, 1))
);

CREATE TABLE contacts (
    id         TEXT PRIMARY KEY,
    source_id  TEXT NOT NULL REFERENCES sources(id),
    locator    TEXT NOT NULL,
    device_id  TEXT REFERENCES devices(id),
    name       TEXT,
    identifier TEXT NOT NULL
);

CREATE TABLE locations (
    id            TEXT PRIMARY KEY,
    source_id     TEXT NOT NULL REFERENCES sources(id),
    locator       TEXT NOT NULL,
    device_id     TEXT REFERENCES devices(id),
    ts_utc        TEXT,
    ts_offset_min INTEGER,
    ts_raw        TEXT,
    lat           REAL NOT NULL,
    lon           REAL NOT NULL,
    accuracy_m    REAL
);

-- ---------------------------------------------------------------- government-document side

CREATE TABLE govdocs (
    id        TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES sources(id),
    title     TEXT NOT NULL,
    doc_kind  TEXT NOT NULL CHECK (doc_kind IN ('affidavit', 'police_report', 'forensic_report', 'other'))
);

CREATE TABLE govdoc_paragraphs (
    id         TEXT PRIMARY KEY,
    govdoc_id  TEXT NOT NULL REFERENCES govdocs(id),
    page       INTEGER NOT NULL,
    para_no    INTEGER NOT NULL,     -- position in the document, counting from 1
    label      TEXT,                 -- paragraph number as printed; NULL if unnumbered
    char_start INTEGER NOT NULL,
    char_end   INTEGER NOT NULL,
    text       TEXT NOT NULL,
    ocr        INTEGER NOT NULL DEFAULT 0 CHECK (ocr IN (0, 1))  -- 1 = OCR text, not verbatim
);

-- ---------------------------------------------------------------- audit side

CREATE TABLE pipeline_runs (
    id                TEXT PRIMARY KEY,  -- 'run:<YYYYMMDDTHHMMSSZ>'
    started_at_utc    TEXT NOT NULL,
    finished_at_utc   TEXT,
    status            TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    baker_version     TEXT NOT NULL,
    contracts_version TEXT NOT NULL,
    rule_version      TEXT NOT NULL,
    config_json       TEXT NOT NULL,     -- eval mode, k, flags
    note              TEXT               -- why it failed, e.g. the invariant that stopped it
);

CREATE TABLE model_runs (
    id           TEXT PRIMARY KEY,
    pipeline_run_id TEXT REFERENCES pipeline_runs(id),
    purpose      TEXT NOT NULL,     -- 'claims', 'assumptions', 'stance', 'review', 'translate', ...
    model_name   TEXT NOT NULL,
    model_sha256 TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    prompt_sha256 TEXT,             -- hash of the prompt file the run used
    params_json  TEXT NOT NULL,     -- temperature, max tokens, grammar, ...
    seed         INTEGER,
    started_at_utc TEXT NOT NULL
);

-- Every model call, whatever happened to its output. Dropped output is kept here.
CREATE TABLE model_calls (
    id            TEXT PRIMARY KEY,  -- 'mc:<model_run_id>#<seq>'
    model_run_id  TEXT NOT NULL REFERENCES model_runs(id),
    seq           INTEGER NOT NULL CHECK (seq >= 1),
    subject_json  TEXT NOT NULL,     -- ids the call was about (assumption, record, evidence)
    prompt        TEXT NOT NULL,     -- fully rendered prompt
    raw_output    TEXT NOT NULL,     -- exactly what the model returned; '' on error
    outcome       TEXT NOT NULL CHECK (outcome IN ('ok', 'invalid_output', 'quote_failed', 'error')),
    error         TEXT,
    at_utc        TEXT NOT NULL,
    UNIQUE (model_run_id, seq)
);

CREATE TABLE claims (
    id           TEXT PRIMARY KEY,
    paragraph_id TEXT NOT NULL REFERENCES govdoc_paragraphs(id),
    text         TEXT NOT NULL,
    claim_type   TEXT NOT NULL CHECK (claim_type IN ('communication', 'identity', 'timing',
                     'content_meaning', 'count', 'absence', 'role', 'event')),
    status       TEXT NOT NULL CHECK (status IN ('proposed', 'accepted', 'edited', 'removed')),
    model_run_id TEXT REFERENCES model_runs(id)   -- NULL when the expert wrote it
);

CREATE TABLE assumptions (
    id       TEXT PRIMARY KEY,       -- 'asm:<claim_id>:<template_id>:<params hash>'
    claim_id TEXT NOT NULL REFERENCES claims(id),
    kind     TEXT NOT NULL CHECK (kind IN ('identity', 'time', 'meaning', 'completeness', 'event')),
    template_id      TEXT NOT NULL,  -- fixed template in core/audit/assumptions.py
    template_version TEXT NOT NULL,
    params_json      TEXT NOT NULL,  -- AssumptionParams; checks read this, never text
    text     TEXT NOT NULL,          -- human-readable rendering; never parsed
    is_core  INTEGER NOT NULL CHECK (is_core IN (0, 1)),
    -- tier at creation; coverage is computed in rules.py and never stored back here
    tier     TEXT NOT NULL CHECK (tier IN ('observed', 'derived', 'inferred', 'ai_reviewed', 'confirmed'))
);

CREATE TABLE evidence_items (
    id            TEXT PRIMARY KEY,  -- 'ev:<assumption_id>|<record_id>|<stance+quote hash>'
    assumption_id TEXT NOT NULL REFERENCES assumptions(id),
    source_id     TEXT NOT NULL REFERENCES sources(id),
    locator       TEXT NOT NULL,
    record_id     TEXT NOT NULL,    -- messages.id, calls.id, ...
    stance        TEXT NOT NULL CHECK (stance IN ('supports', 'contradicts', 'complicates', 'irrelevant')),
    quote         TEXT NOT NULL,    -- verified verbatim against the record before insert
    rationale     TEXT NOT NULL,
    -- the record's tier; never changes. Review status lives in evidence_reviews,
    -- and the tier a report shows comes from display_tier() in core/contracts.py.
    tier          TEXT NOT NULL CHECK (tier IN ('observed', 'derived', 'inferred')),
    model_run_id  TEXT REFERENCES model_runs(id)
);

-- Reviews of evidence items, AI or expert. Append-only: a human override is a new row.
-- The latest row (highest seq) per evidence item is its status; no row means 'open'.
CREATE TABLE evidence_reviews (
    id             TEXT PRIMARY KEY,  -- 'rv:<evidence_id>#<seq>'
    evidence_id    TEXT NOT NULL REFERENCES evidence_items(id),
    seq            INTEGER NOT NULL CHECK (seq >= 1),
    reviewer_kind  TEXT NOT NULL CHECK (reviewer_kind IN ('ai', 'expert')),
    reviewer       TEXT NOT NULL,     -- 'ai:<model_name>' or 'expert:<name>'
    status         TEXT NOT NULL CHECK (status IN ('open', 'ai_accepted', 'accepted', 'dismissed')),
    reason         TEXT NOT NULL CHECK (length(reason) > 0),
    model_run_id   TEXT REFERENCES model_runs(id),
    model_call_id  TEXT REFERENCES model_calls(id),
    decided_at_utc TEXT NOT NULL,
    UNIQUE (evidence_id, seq),
    CHECK ((reviewer_kind = 'ai' AND status IN ('ai_accepted', 'dismissed')
                AND model_run_id IS NOT NULL)
        OR (reviewer_kind = 'expert' AND status IN ('accepted', 'dismissed', 'open')
                AND model_run_id IS NULL))
);

CREATE VIEW evidence_status AS
SELECT e.id AS evidence_id,
       COALESCE((SELECT r.status FROM evidence_reviews r WHERE r.evidence_id = e.id
                 ORDER BY r.seq DESC LIMIT 1), 'open') AS status
FROM evidence_items e;

CREATE TABLE check_results (
    id            TEXT PRIMARY KEY,  -- 'chk:<assumption_id>|<check_name>@<check_version>'
    assumption_id TEXT NOT NULL REFERENCES assumptions(id),
    check_name    TEXT NOT NULL,
    check_version TEXT NOT NULL,
    outcome       TEXT NOT NULL CHECK (outcome IN ('pass', 'fail', 'inconclusive')),
    searched      TEXT NOT NULL,     -- what was searched and the sources' coverage
    record_ids_json TEXT NOT NULL DEFAULT '[]',  -- records the outcome rests on
    source_ids_json TEXT NOT NULL DEFAULT '[]',  -- sources searched
    detail        TEXT NOT NULL
);

-- Case-level facts the expert confirms once (e.g. who owns each phone). Every report
-- lists each confirmed stipulation as a limitation.
CREATE TABLE stipulations (
    id             TEXT PRIMARY KEY,  -- 'stip:<kind>:<subject_id>'
    kind           TEXT NOT NULL CHECK (kind IN ('device_owner')),
    subject_id     TEXT NOT NULL,     -- devices.id for device_owner
    person_id      TEXT NOT NULL REFERENCES persons(id),
    statement      TEXT NOT NULL,
    status         TEXT NOT NULL CHECK (status IN ('proposed', 'confirmed', 'rejected')),
    decided_by     TEXT,              -- 'expert:<name>'
    decided_at_utc TEXT,
    CHECK (status = 'proposed' OR (decided_by LIKE 'expert:%' AND decided_at_utc IS NOT NULL))
);

CREATE TABLE verdicts (
    id              TEXT PRIMARY KEY,  -- 'vd:<claim_id>@<pipeline_run_id>'
    claim_id        TEXT NOT NULL REFERENCES claims(id),
    pipeline_run_id TEXT NOT NULL REFERENCES pipeline_runs(id),
    verdict         TEXT NOT NULL CHECK (verdict IN ('supported', 'contradicted', 'unproven')),
    supported_basis TEXT CHECK (supported_basis IN ('ai_reviewed', 'confirmed')),
    rule_version    TEXT NOT NULL,
    reasons_json    TEXT NOT NULL,
    coverage_json   TEXT NOT NULL,     -- AssumptionCoverage per core assumption, as computed
    cited_json      TEXT NOT NULL,     -- {"evidence": [...], "checks": [...], "stipulations": [...]}
    decided_at_utc  TEXT NOT NULL,
    confirmed_by    TEXT,              -- expert who confirmed or overrode it
    override_note   TEXT,
    CHECK ((verdict = 'supported') = (supported_basis IS NOT NULL))
);

CREATE TABLE audit_log (
    seq          INTEGER PRIMARY KEY,
    at_utc       TEXT NOT NULL,
    actor        TEXT NOT NULL,     -- 'system', 'expert:<name>'
    action       TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    prev_hash    TEXT NOT NULL,     -- '' for the first entry
    hash         TEXT NOT NULL      -- sha256 over prev_hash, at_utc, actor, action, payload_json
);

CREATE INDEX idx_messages_thread_ts ON messages(thread_id, ts_utc);
CREATE INDEX idx_messages_sender ON messages(sender_account_id);
CREATE INDEX idx_evidence_assumption ON evidence_items(assumption_id);
CREATE INDEX idx_verdicts_run ON verdicts(pipeline_run_id, claim_id);

-- ---------------------------------------------------------------- append-only tables

CREATE TRIGGER evidence_reviews_no_update BEFORE UPDATE ON evidence_reviews
BEGIN SELECT RAISE(ABORT, 'evidence_reviews is append-only'); END;
CREATE TRIGGER evidence_reviews_no_delete BEFORE DELETE ON evidence_reviews
BEGIN SELECT RAISE(ABORT, 'evidence_reviews is append-only'); END;
CREATE TRIGGER model_calls_no_update BEFORE UPDATE ON model_calls
BEGIN SELECT RAISE(ABORT, 'model_calls is append-only'); END;
CREATE TRIGGER model_calls_no_delete BEFORE DELETE ON model_calls
BEGIN SELECT RAISE(ABORT, 'model_calls is append-only'); END;
CREATE TRIGGER audit_log_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER audit_log_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
