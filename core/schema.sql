-- Baker canonical schema. HUMAN-OWNED. Agents: propose changes in PROPOSED_CHANGES.md.
-- One SQLite database per case.
-- Conventions:
--   * ids are TEXT, built deterministically from source and locator (stable across re-imports).
--   * every evidence row has (source_id, locator) = its source_ref back to the original artifact.
--   * times: ts_utc is ISO 8601 UTC ('2026-03-05T02:31:00Z'); ts_offset_min is the original
--     UTC offset in minutes (NULL if the source did not say); ts_raw is the value as it appeared.
--   * enum values here must match the enums in core/contracts.py (tests enforce this).

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

CREATE TABLE model_runs (
    id           TEXT PRIMARY KEY,
    purpose      TEXT NOT NULL,     -- 'claims', 'assumptions', 'stance', 'translate', ...
    model_name   TEXT NOT NULL,
    model_sha256 TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    params_json  TEXT NOT NULL,     -- temperature, max tokens, grammar, ...
    seed         INTEGER,
    started_at_utc TEXT NOT NULL
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
    id       TEXT PRIMARY KEY,
    claim_id TEXT NOT NULL REFERENCES claims(id),
    kind     TEXT NOT NULL CHECK (kind IN ('identity', 'time', 'meaning', 'completeness', 'event')),
    text     TEXT NOT NULL,
    is_core  INTEGER NOT NULL CHECK (is_core IN (0, 1)),
    tier     TEXT NOT NULL CHECK (tier IN ('observed', 'derived', 'inferred', 'ai_reviewed', 'confirmed'))
);

CREATE TABLE evidence_items (
    id            TEXT PRIMARY KEY,
    assumption_id TEXT NOT NULL REFERENCES assumptions(id),
    source_id     TEXT NOT NULL REFERENCES sources(id),
    locator       TEXT NOT NULL,
    record_id     TEXT NOT NULL,    -- messages.id, calls.id, ...
    stance        TEXT NOT NULL CHECK (stance IN ('supports', 'contradicts', 'complicates', 'irrelevant')),
    quote         TEXT NOT NULL,    -- verified verbatim against the record before insert
    rationale     TEXT NOT NULL,
    tier          TEXT NOT NULL CHECK (tier IN ('observed', 'derived', 'inferred', 'ai_reviewed', 'confirmed')),
    status        TEXT NOT NULL CHECK (status IN ('open', 'ai_accepted', 'accepted', 'dismissed')),
    model_run_id  TEXT REFERENCES model_runs(id)
);

CREATE TABLE check_results (
    id            TEXT PRIMARY KEY,
    assumption_id TEXT NOT NULL REFERENCES assumptions(id),
    check_name    TEXT NOT NULL,
    check_version TEXT NOT NULL,
    outcome       TEXT NOT NULL CHECK (outcome IN ('pass', 'fail', 'inconclusive')),
    detail        TEXT NOT NULL
);

CREATE TABLE verdicts (
    id             TEXT PRIMARY KEY,
    claim_id       TEXT NOT NULL REFERENCES claims(id),
    verdict        TEXT NOT NULL CHECK (verdict IN ('supported', 'contradicted', 'unproven')),
    rule_version   TEXT NOT NULL,
    reasons_json   TEXT NOT NULL,
    decided_at_utc TEXT NOT NULL,
    confirmed_by   TEXT,            -- expert who confirmed or overrode it
    override_note  TEXT
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
