"""Cloud AI by per-case opt-in: the cloud stance labeler, its fallback and the per-case choice.

No network: the API is a stand-in client and the local model a scripted fake.
"""

from __future__ import annotations

import json
import os
import stat
import sys
import types
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import pytest

from core.audit import stance as stance_mod
from core.audit._llm_json import CloudPaused, ModelUnavailable
from core.casework import cloud as cloud_policy
from core.contracts import EvidenceCandidate, ProvenanceTier, SourceRef
from core.llm import cloud
from core.llm.runtime import ModelOutput
from core.report.html import labelled_by
from tests.fake_model import make_assumption

SHA = "ab" * 32
SUPPORTS = '{"stance": "supports", "quote": "garage", "rationale": "Says so."}'
KEY = "sk-ant-test-0123456789abcdef"


# ---------------------------------------------------------------- stand-ins


@dataclass
class _Out:
    raw_text: str


@dataclass
class FakeLocal:
    replies: list[str]
    name: str = "fake-14b"
    sha256: str = SHA
    prompts: list[str] = field(default_factory=list)

    def generate_json(self, prompt, schema, params=None):  # noqa: ANN001, ANN201
        self.prompts.append(prompt)
        return _Out(self.replies.pop(0))


@dataclass
class FakeCloud:
    """Answers like core.llm.cloud.ClaudeModel: text, or a CloudError."""

    replies: list[object]
    name: str = "claude-opus-5-5"
    sha256: str = "api:claude-opus-5-5"
    where: str = "cloud"
    params: cloud.CloudParams = field(
        default_factory=lambda: cloud.CloudParams("claude-opus-5-5", "medium")
    )
    prompts: list[str] = field(default_factory=list)

    def request(self, prompt, schema):  # noqa: ANN001, ANN201
        return {"model": self.name, "messages": [{"role": "user", "content": prompt}]}

    def generate_json(self, prompt, schema, params=None):  # noqa: ANN001, ANN201
        self.prompts.append(prompt)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return _Out(str(reply))


class _Obj:
    def __init__(self, **kw: object) -> None:
        self.__dict__.update(kw)


class FakeClient:
    def __init__(self, reply: object) -> None:
        self.messages = self
        self.reply = reply
        self.requests: list[dict] = []

    def create(self, **kw: object) -> object:
        self.requests.append(kw)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def _resp(text: str = SUPPORTS, stop: str = "end_turn") -> object:
    usage = _Obj(input_tokens=100, output_tokens=20)
    return _Obj(stop_reason=stop, content=[_Obj(type="text", text=text)], usage=usage)


@pytest.fixture(autouse=True)
def probe_passed(monkeypatch):  # noqa: ANN001, ANN201
    """These tests cover what happens once a model passes the signed stance test; the gate
    itself, and the shipped list, are tested on their own."""
    version = cloud_policy._stance_prompt_version()
    monkeypatch.setattr(
        cloud, "PROBE_PASSED", frozenset({(cloud.DEFAULT_MODEL, cloud.DEFAULT_EFFORT, version)})
    )


@pytest.fixture
def fake_context(monkeypatch):  # noqa: ANN001, ANN201
    ctx = types.ModuleType("core.audit.context")
    ctx.render_for = lambda conn, rid, names=None: f">> CONTEXT FOR {rid}"
    monkeypatch.setitem(sys.modules, "core.audit.context", ctx)


def _cand(rid: str = "msg:7") -> EvidenceCandidate:
    return EvidenceCandidate(
        record_id=rid,
        ref=SourceRef(source_id="s", locator="l"),
        text="meet me at the garage",
        tier=ProvenanceTier.OBSERVED,
        retrieval_score=1.0,
    )


def _cloud_run(lab):  # noqa: ANN001, ANN202
    (run,) = lab.model_runs  # a cloud case has one stance run: labels never mix models
    assert run.model_sha256.startswith("api:")
    return run


# ---------------------------------------------------------------- config and key


def test_config_reads_the_key_from_the_environment_first(tmp_path, monkeypatch):
    p = tmp_path / "cloud.json"
    p.write_text(json.dumps({"api_key": "sk-ant-file", "effort": "high"}))
    monkeypatch.setenv(cloud.KEY_ENV, "sk-ant-env")
    cfg = cloud.load_config(p)
    assert cfg.api_key == "sk-ant-env" and cfg.effort == "high"
    assert cfg.model == "claude-opus-5-5" and cfg.base_url == "https://api.anthropic.com"
    assert "sk-ant" not in repr(cfg)


@pytest.mark.parametrize(
    "raw",
    [
        {},
        {"api_key": "k", "effort": "turbo"},
        {"api_key": "k", "base_url": "http://x"},
        {"api_key": "k", "base_url": "https://proxy.example.com"},
    ],
)
def test_bad_or_missing_config_is_refused(tmp_path, monkeypatch, raw):
    monkeypatch.delenv(cloud.KEY_ENV, raising=False)
    p = tmp_path / "cloud.json"
    p.write_text(json.dumps(raw))
    with pytest.raises(cloud.CloudConfigError):
        cloud.load_config(p)


def _encrypted_case(tmp_path: Path, name: str = "a") -> Path:
    from core import encryption

    dbp = tmp_path / name / "case.db"
    dbp.parent.mkdir()
    encryption.create_key(dbp, "correct horse battery staple")
    return dbp


def test_an_encrypted_case_keeps_the_key_sealed_under_the_case_key(tmp_path, monkeypatch):
    from core import encryption

    monkeypatch.delenv(cloud.KEY_ENV, raising=False)
    plain = tmp_path / "cloud.json"
    dbp = _encrypted_case(tmp_path)
    where = cloud.save_key(KEY, plain, case_db=dbp)
    assert where == dbp.with_suffix(".cloud-key") and not plain.exists()
    assert KEY.encode() not in where.read_bytes()
    assert stat.S_IMODE(os.stat(where).st_mode) == 0o600 or os.name == "nt"
    assert cloud.load_config(plain, case_db=dbp).api_key == KEY
    encryption.forget_all()  # Baker stopped: every case is locked
    with pytest.raises(cloud.CloudConfigError, match="cannot be read"):
        cloud.load_config(plain, case_db=dbp)


def test_a_plain_case_and_the_environment_keep_their_old_behaviour(tmp_path, monkeypatch):
    monkeypatch.delenv(cloud.KEY_ENV, raising=False)
    plain = tmp_path / "cloud.json"
    (tmp_path / "p").mkdir()
    plain_case = tmp_path / "p" / "case.db"
    assert cloud.save_key(KEY, plain, case_db=plain_case) == plain
    assert cloud.load_config(plain, case_db=plain_case).api_key == KEY
    dbp = _encrypted_case(tmp_path)
    assert cloud.load_config(plain, case_db=dbp).api_key == KEY  # none sealed: the file's
    cloud.save_key("sk-ant-sealed-0123456789", plain, case_db=dbp)
    assert cloud.load_config(plain, case_db=dbp).api_key == "sk-ant-sealed-0123456789"
    monkeypatch.setenv(cloud.KEY_ENV, "sk-ant-env-0123456789abcdef")
    assert cloud.load_config(plain, case_db=dbp).api_key == "sk-ant-env-0123456789abcdef"
    with pytest.raises(cloud.CloudConfigError, match="is the one in use"):
        cloud.save_key(KEY, plain, case_db=dbp)


def test_a_sealed_key_from_another_case_is_refused(tmp_path, monkeypatch):
    monkeypatch.delenv(cloud.KEY_ENV, raising=False)
    a, b = _encrypted_case(tmp_path, "a"), _encrypted_case(tmp_path, "b")
    cloud.save_key(KEY, tmp_path / "cloud.json", case_db=a)
    a.with_suffix(".cloud-key").replace(b.with_suffix(".cloud-key"))
    with pytest.raises(cloud.CloudConfigError, match="does not belong"):
        cloud.load_config(tmp_path / "cloud.json", case_db=b)


@pytest.mark.parametrize("field", ["nonce", "sealed"])
def test_a_damaged_sealed_key_reads_as_a_config_error(tmp_path, monkeypatch, field):
    monkeypatch.delenv(cloud.KEY_ENV, raising=False)
    dbp = _encrypted_case(tmp_path)
    where = cloud.save_key(KEY, tmp_path / "cloud.json", case_db=dbp)
    data = json.loads(where.read_text(encoding="utf-8"))
    data[field] = "not base64!"
    where.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(cloud.CloudConfigError, match="altered"):
        cloud.load_config(tmp_path / "cloud.json", case_db=dbp)


def test_saved_key_is_readable_by_its_owner_only(tmp_path, monkeypatch):
    monkeypatch.delenv(cloud.KEY_ENV, raising=False)
    p = cloud.save_key(KEY, tmp_path / "cloud.json")
    assert cloud.load_config(p).api_key == KEY
    if os.name != "nt":
        assert stat.S_IMODE(p.stat().st_mode) == 0o600


# ---------------------------------------------------------------- the API model


def _model(reply: object) -> tuple[cloud.ClaudeModel, FakeClient]:
    client = FakeClient(reply)
    return cloud.ClaudeModel(cloud.CloudConfig(api_key=KEY), client=client), client


def test_cloud_model_answers_and_sends_the_schema_without_length_limits():
    model, client = _model(_resp())
    out = model.generate_json("p", stance_mod.STANCE_SCHEMA)
    assert isinstance(out, ModelOutput) and out.parsed["stance"] == "supports"
    sent = client.requests[0]
    assert sent["model"] == "claude-opus-5-5"
    assert sent["output_config"]["effort"] == "medium"
    assert "maxLength" not in json.dumps(sent["output_config"]["format"]["schema"])
    assert model.sha256 == "api:claude-opus-5-5" and model.params.as_record()["where"] == "cloud"


def test_an_api_error_is_a_sticky_cloud_error():
    model, _ = _model(ConnectionError("no network"))
    with pytest.raises(cloud.CloudError) as err:
        model.generate_json("p", stance_mod.STANCE_SCHEMA)
    assert err.value.sticky


@pytest.mark.parametrize("stop", ["refusal", "max_tokens"])
def test_a_refusal_or_cut_off_answer_falls_back_for_that_call_only(stop):
    model, _ = _model(_resp("", stop))
    with pytest.raises(cloud.CloudError) as err:
        model.generate_json("p", stance_mod.STANCE_SCHEMA)
    assert not err.value.sticky


def test_the_api_address_is_pinned_whatever_the_environment_says(monkeypatch):
    pytest.importorskip("anthropic")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://elsewhere.example")
    model = cloud.ClaudeModel(cloud.CloudConfig(api_key=KEY))
    client = model._get_client()  # builds the client; makes no call
    assert str(client.base_url).startswith("https://api.anthropic.com")


# ---------------------------------------------------------------- the labeler: no mixed labels


def test_cloud_labels_and_the_item_names_the_cloud_run(case_db, fake_context):
    up, local = FakeCloud([SUPPORTS]), FakeLocal([])
    lab = stance_mod.create(case_db, model=local, cloud_model=up)
    run = _cloud_run(lab)
    label = lab.label(make_assumption("They met at the garage."), _cand())
    assert label.model_run_id == run.id and not local.prompts
    assert ">> CONTEXT FOR msg:7" in up.prompts[0]


def test_a_sticky_failure_pauses_the_run_and_never_asks_the_local_model(case_db, fake_context):
    up = FakeCloud([cloud.CloudError("ConnectionError: down", sticky=True)])
    local = FakeLocal([SUPPORTS])
    lab = stance_mod.create(case_db, model=local, cloud_model=up)
    with pytest.raises(CloudPaused, match="stopped answering"):
        lab.label(make_assumption("They met at the garage."), _cand())
    assert not local.prompts
    assert isinstance(CloudPaused("x"), ModelUnavailable)  # the pipeline stops, never drops


def test_a_refusal_drops_that_label_and_the_next_call_stays_on_the_cloud(case_db, fake_context):
    up = FakeCloud([cloud.CloudError("declined", sticky=False), SUPPORTS])
    local = FakeLocal([SUPPORTS])
    lab = stance_mod.create(case_db, model=local, cloud_model=up)
    run = _cloud_run(lab)
    a = make_assumption("They met at the garage.")
    first = lab.try_label(a, _cand("msg:1"))
    assert first.label is None and first.call.outcome.value == "error"
    assert lab.label(a, _cand("msg:2")).model_run_id == run.id
    assert not local.prompts


def test_a_cloud_label_whose_quote_fails_is_dropped_not_relabeled(
    case_db, fake_context, monkeypatch
):
    from core import pipeline

    made_up = '{"stance": "supports", "quote": "at the warehouse", "rationale": "Says so."}'
    local = FakeLocal([SUPPORTS])
    lab = stance_mod.create(case_db, model=local, cloud_model=FakeCloud([made_up]))
    monkeypatch.setattr(
        pipeline.invariants, "record_text", lambda conn, rid: "meet me at the garage"
    )
    run = pipeline._Run.__new__(pipeline._Run)
    run.conn, run.result = case_db, types.SimpleNamespace(dropped_labels=0)
    run.c = types.SimpleNamespace(labeler=lab, verify_quote=lambda q, text: q in text)
    run.flush_calls = lambda quote_failed=frozenset(): None
    assert run._label(make_assumption("They met at the garage."), _cand()) is None
    assert run.result.dropped_labels == 1 and not local.prompts


def test_a_cloud_model_reads_the_cloud_prompt_and_the_local_model_keeps_its_own(
    case_db, fake_context
):
    # Arsh's "Opus only" (2026-10-19): v1.2 for a cloud model, v1.1 for the local 14B.
    from core.audit._llm_json import load_prompt, prompt_version

    local_v = prompt_version(load_prompt(stance_mod.PROMPT_FILE))
    cloud_v = prompt_version(load_prompt(stance_mod.CLOUD_PROMPT_FILE))
    assert local_v != cloud_v
    lab = stance_mod.create(case_db, cloud_model=FakeCloud([SUPPORTS]))
    assert lab.prompt_version == _cloud_run(lab).prompt_version == cloud_v
    assert stance_mod.create(case_db, model=FakeLocal([])).prompt_version == local_v
    # The cloud benchmarks pass a cloud model as the labeler's model: it reads the cloud prompt.
    assert stance_mod.create(case_db, model=FakeCloud([])).prompt_version == cloud_v
    assert stance_mod.prompt_file(None) == stance_mod.PROMPT_FILE
    # The gate checks the version a cloud case would send.
    assert cloud_policy._stance_prompt_version() == cloud_v


def test_a_cloud_case_needs_no_local_stance_model(case_db, fake_context, monkeypatch):
    monkeypatch.setenv("BAKER_MODEL_CONFIG", "/nonexistent/model.json")
    lab = stance_mod.create(case_db, cloud_model=FakeCloud([SUPPORTS]))
    run = _cloud_run(lab)
    assert lab.label(make_assumption("They met at the garage."), _cand()).model_run_id == run.id


def test_every_request_is_in_the_audit_log_before_it_is_sent(case_db, fake_context):
    from core.audit._local_model import SENT_ACTION
    from core.review.audit_log import verify_chain

    up = FakeCloud([SUPPORTS, cloud.CloudError("ConnectionError: down", sticky=True)])
    lab = stance_mod.create(case_db, cloud_model=up)
    a = make_assumption("They met at the garage.")
    lab.label(a, _cand("msg:1"))
    with pytest.raises(CloudPaused):
        lab.label(a, _cand("msg:2"))  # a request that got no answer was still sent
    rows = case_db.execute(
        "SELECT actor, payload_json FROM audit_log WHERE action = ? ORDER BY seq", (SENT_ACTION,)
    ).fetchall()
    assert len(rows) == 2 and verify_chain(case_db)
    sent = [json.loads(p)["request"]["messages"][0]["content"] for _, p in rows]
    assert sent == up.prompts and all(actor == "system" for actor, _ in rows)
    assert KEY not in json.dumps([p for _, p in rows])


def test_without_cloud_the_labeler_is_the_local_model_alone(case_db, fake_context):
    local = FakeLocal([SUPPORTS])
    lab = stance_mod.create(case_db, model=local)
    (run,) = lab.model_runs
    assert lab.label(make_assumption("They met at the garage."), _cand()).model_run_id == run.id
    assert not case_db.execute("SELECT 1 FROM audit_log WHERE action = 'cloud.sent'").fetchall()


def test_a_rules_only_redecide_keeps_the_cloud_decision_for_the_report():
    src = (Path(__file__).resolve().parents[1] / "core" / "review" / "redecide.py").read_text(
        encoding="utf-8"
    )
    assert 'cfg["cloud"] = src["config"]["cloud"]' in src


def test_the_report_shows_who_attested_and_the_words_they_agreed_to(tmp_path):
    from core.report.html import render_report
    from eval import run_pipeline as rp

    conn = rp.build_case("case01", tmp_path / "case01.db")
    cloud_policy.set_cloud(conn, "expert:Ana", allowed=True, csam=False)
    page = render_report(conn)
    assert "expert:Ana" in page and "set_cloud" in page
    assert "allows its evidence to be sent to a cloud AI service under my firm" in page
    assert "informed consent" in page


def test_a_cloud_estimate_keeps_assumption_filling_at_the_local_speed():
    from core.casework import jobs

    local_only = jobs.estimate_seconds(20, 40.0)
    mixed = jobs.estimate_seconds(20, 40.0, jobs.CLOUD_SECONDS_PER_CALL)
    stance_calls = jobs.CALLS_PER_CLAIM - jobs.LOCAL_CALLS_PER_CLAIM
    assert mixed == 20 * (40.0 + stance_calls * jobs.CLOUD_SECONDS_PER_CALL) < local_only


def test_a_stalled_cloud_request_gives_up_in_minutes():
    assert cloud.REQUEST_TIMEOUT_SECONDS * (cloud.MAX_RETRIES + 1) <= 6 * 60


# ---------------------------------------------------------------- the case's choice


def _key() -> cloud.CloudConfig:
    return cloud.CloudConfig(api_key=KEY)


def _no_key() -> cloud.CloudConfig:
    raise cloud.CloudConfigError("no Anthropic key")


@pytest.mark.parametrize(
    ("entries", "load", "use"),
    [
        ([], _key, False),  # never attested
        ([{"allowed": True, "csam": False}], _key, True),
        ([{"allowed": True, "csam": True}], _key, False),  # CSAM wins over the attestation
        ([{"allowed": True, "csam": False}], _no_key, False),  # no key: local
        ([{"allowed": True, "csam": False}, {"allowed": False, "csam": False}], _key, False),
    ],
)
def test_cloud_is_used_only_when_attested_not_csam_and_keyed(case_db, entries, load, use):
    for e in entries:
        cloud_policy.set_cloud(case_db, "expert:Ana", **e)
    choice = cloud_policy.choose(case_db, load)
    assert choice.use is use
    assert choice.why.startswith("Cloud model" if use else "Local model")


def _shipped_probe_passed() -> frozenset[tuple[str, str, str]]:
    # The fixture patches PROBE_PASSED, so read the shipped value from the source:
    # `PROBE_PASSED: ... = frozenset({...})` with a literal set inside.
    import ast

    tree = ast.parse(Path(cloud.__file__).read_text(encoding="utf-8"))
    (node,) = [
        n
        for n in tree.body
        if isinstance(n, ast.AnnAssign) and getattr(n.target, "id", None) == "PROBE_PASSED"
    ]
    assert isinstance(node.value, ast.Call) and getattr(node.value.func, "id", "") == "frozenset"
    return frozenset(ast.literal_eval(node.value.args[0]) if node.value.args else ())


def test_only_opus_at_medium_with_the_cloud_prompt_has_passed_the_signed_stance_test():
    # Signed by Arsh 2026-10-20. A change to the cloud prompt changes its version, which drops
    # this entry and fails here, until the new prompt passes again and Arsh signs a new entry.
    version = cloud_policy._stance_prompt_version()
    assert version == "sha256:2863d8dbf66960f6"
    assert _shipped_probe_passed() == {(cloud.DEFAULT_MODEL, cloud.DEFAULT_EFFORT, version)}


def test_the_entry_s_committed_answers_meet_the_signed_bars():
    # The per-item answers behind the entry (core/llm/cloud.py names the file): the signed set
    # as it is in the repo now, and both new sets with no wrong "contradicts".
    import hashlib

    root = Path(__file__).resolve().parents[1]
    results = root / "eval/probe/results/2026-10-15-opus-5-5-medium-stance-v1-2.jsonl"
    rows = [json.loads(line) for line in results.read_text(encoding="utf-8").splitlines()]
    signed = [r for r in rows if r["set"] == "signed"]
    probe = (root / "eval/gold/probe/probe.jsonl").read_bytes()
    assert {r["set_sha256"] for r in signed} == {hashlib.sha256(probe).hexdigest()[:16]}
    gated = [r for r in signed if r["scored"]]
    assert len(gated) == 95
    supports = [r for r in gated if r["gold"] == "supports"]
    said = [r for r in gated if r["first"] == "contradicts"]
    assert sum(r["first"] == "supports" for r in supports) == len(supports) == 33
    assert sum(r["gold"] == "contradicts" for r in said) == len(said) == 10
    assert not [r for r in gated if r["gold"] == "contradicts" and r["first"] == "supports"]
    for name, n in (("new-24", 22), ("new-26", 26)):
        new = [r for r in rows if r["set"] == name and r["scored"]]
        assert len(new) == n
        assert not [r for r in new if r["first"] == "contradicts" and r["gold"] != "contradicts"]


def test_the_shipped_entry_lets_an_attested_case_use_opus_at_medium(case_db, monkeypatch):
    monkeypatch.setattr(cloud, "PROBE_PASSED", _shipped_probe_passed())
    cloud_policy.set_cloud(case_db, "expert:Ana", allowed=True, csam=False)
    assert cloud_policy.choose(case_db, _key).use
    high = cloud.CloudConfig(api_key=KEY, effort="high")
    assert not cloud_policy.choose(case_db, lambda: high).use


def test_a_model_that_has_not_passed_the_signed_test_labels_locally(case_db, monkeypatch):
    monkeypatch.setattr(cloud, "PROBE_PASSED", frozenset())
    cloud_policy.set_cloud(case_db, "expert:Ana", allowed=True, csam=False)
    choice = cloud_policy.choose(case_db, _key)
    assert not choice.use
    assert "has not passed Baker's signed stance test" in choice.why


def test_a_pass_on_another_stance_prompt_does_not_count(case_db, monkeypatch):
    old = (cloud.DEFAULT_MODEL, cloud.DEFAULT_EFFORT, "sha256:old")
    monkeypatch.setattr(cloud, "PROBE_PASSED", frozenset({old}))
    cloud_policy.set_cloud(case_db, "expert:Ana", allowed=True, csam=False)
    assert not cloud_policy.choose(case_db, _key).use


def test_a_pass_at_another_effort_does_not_count(case_db):
    cloud_policy.set_cloud(case_db, "expert:Ana", allowed=True, csam=False)
    low = cloud.CloudConfig(api_key=KEY, effort="low")
    choice = cloud_policy.choose(case_db, lambda: low)
    assert not choice.use and "low effort" in choice.why


def test_a_client_that_cannot_be_built_pauses_rather_than_drops(monkeypatch):
    def broken(**kw):  # noqa: ANN003, ANN202
        raise ValueError("bad proxy URL")

    monkeypatch.setitem(sys.modules, "anthropic", types.SimpleNamespace(Anthropic=broken))
    model = cloud.ClaudeModel(cloud.CloudConfig(api_key=KEY))
    with pytest.raises(cloud.CloudError, match="could not be set up") as err:
        model.prepare()
    assert err.value.sticky


def _log(conn, actor: str, payload: dict) -> None:  # noqa: ANN001
    from core.review import audit_log

    audit_log.append(conn, datetime(2026, 10, 15, tzinfo=UTC), actor, "set_cloud", payload)


def test_a_bare_allowed_flag_without_the_attestation_is_not_cloud(case_db):
    _log(case_db, "expert:Ana", {"allowed": True, "csam": False})  # no attestation text
    assert not cloud_policy.choose(case_db, _key).use
    _log(case_db, "system", {"allowed": True, "csam": False,
                             "attestation": cloud_policy.ATTESTATION})  # fmt: skip
    assert not cloud_policy.choose(case_db, _key).use  # only an expert attests


def test_the_choice_is_logged_under_the_expert_and_nowhere_readable(case_db):
    at = datetime(2026, 10, 15, tzinfo=UTC)
    entry = cloud_policy.set_cloud(
        case_db, "expert:Ana", allowed=True, csam=False, clock=lambda: at
    )
    assert entry == {"allowed": True, "csam": False, "attested_by": "expert:Ana",
                     "attested_at": "2026-10-15T00:00:00Z"}  # fmt: skip
    choice = cloud_policy.choose(case_db, _key)
    assert "attested by Ana on 2026-10-15" in choice.why
    entry = cloud_policy.set_cloud(case_db, "expert:Ana", allowed=True, csam=True)
    assert entry == {"allowed": False, "csam": True}
    rows = case_db.execute("SELECT actor, action, payload_json FROM audit_log").fetchall()
    assert [(a, b) for a, b, _ in rows] == [("expert:Ana", "set_cloud")] * 2
    assert json.loads(rows[0][2])["attestation"] == cloud_policy.ATTESTATION
    assert json.loads(rows[1][2])["csam"] is True


def test_only_a_named_expert_sets_the_choice(case_db):
    from core.review.actions import ReviewError

    with pytest.raises(ReviewError):
        cloud_policy.set_cloud(case_db, "system", allowed=True, csam=False)


# ---------------------------------------------------------------- what the expert reads


def test_each_item_says_which_model_labeled_it(case_db, fake_context):
    up = stance_mod.create(case_db, model=FakeLocal([]), cloud_model=FakeCloud([]))
    down = stance_mod.create(case_db, model=FakeLocal([]))
    case_db.execute("PRAGMA foreign_keys = OFF")
    for m in (*up.model_runs, *down.model_runs):
        case_db.execute(
            "INSERT INTO model_runs (id, pipeline_run_id, purpose, model_name, model_sha256,"
            " prompt_version, prompt_sha256, params_json, seed, started_at_utc)"
            " VALUES (?, 'run:x', 'stance', ?, ?, 'v', 's', '{}', NULL, '2026-10-15T00:00:00Z')",
            (m.id, m.model_name, m.model_sha256),
        )
    cloud_run, (local_run,) = _cloud_run(up), down.model_runs
    assert labelled_by(case_db, cloud_run.id) == "Labeled by claude-opus-5-5 (cloud)"
    assert labelled_by(case_db, local_run.id) == "Labeled by fake-14b (local)"


def test_only_the_cloud_file_in_core_imports_a_network_client():
    root = Path(__file__).resolve().parents[1] / "core"
    users = [
        p.relative_to(root).as_posix()
        for p in root.rglob("*.py")
        if "import anthropic" in p.read_text(encoding="utf-8")
    ]
    assert users == ["llm/cloud.py"]


# ---------------------------------------------------------------- the setup screen


def _screen(tmp_path: Path, monkeypatch):  # noqa: ANN001, ANN202
    from ui.app import App, Request

    monkeypatch.delenv(cloud.KEY_ENV, raising=False)
    host = {"host": "127.0.0.1:8765"}
    app = App(home=tmp_path / "cases", port=8765, model_check=None,
              cloud_config=tmp_path / "cloud.json")  # fmt: skip

    def get(path: str):  # noqa: ANN202
        return app.handle(Request("GET", path, {}, dict(host)))

    def post(path: str, **form: str):  # noqa: ANN202
        form.setdefault("token", app.token)
        return app.handle(Request("POST", path, {}, dict(host), form))

    post("/expert", name="Test Expert")
    post("/case/new", name="Cloud case")
    return app, get, post


def test_the_setup_page_attests_per_case_and_keeps_the_key_local(tmp_path, monkeypatch):
    app, get, post = _screen(tmp_path, monkeypatch)
    page = get("/setup").text
    assert "Cloud AI for this case" in page and "Local only" in page
    assert "No cloud key yet" in page

    post("/cloud/key", api_key="not a key")
    assert not (tmp_path / "cloud.json").exists()
    post("/cloud/key", api_key=KEY)
    assert cloud.load_config(tmp_path / "cloud.json").api_key == KEY
    page = get("/setup").text
    assert KEY not in page and "An Anthropic key is set up" in page

    post("/cloud/case", allowed="1")
    assert "cloud" not in app.case.settings  # kept in the case database, not case.json
    page = get("/setup").text
    assert "Cloud AI on for this case" in page and "Cloud labels on" in page

    post("/cloud/case", allowed="1", csam="1")
    page = get("/setup").text
    assert "Local only" in page and "Offline" in page


def test_a_key_from_the_environment_is_not_silently_replaced(tmp_path, monkeypatch):
    app, get, post = _screen(tmp_path, monkeypatch)
    monkeypatch.setenv(cloud.KEY_ENV, "sk-ant-env-0123456789abcdef")
    assert "comes from" in get("/setup").text
    post("/cloud/key", api_key=KEY)
    assert not (tmp_path / "cloud.json").exists()
    with pytest.raises(cloud.CloudConfigError):
        cloud.save_key(KEY, tmp_path / "cloud.json")


def test_the_cli_audit_applies_the_case_choice():
    src = (Path(__file__).resolve().parents[1] / "cli" / "main.py").read_text(encoding="utf-8")
    assert "cloud=choice" in src and "cloud_policy.choose(conn, load)" in src
    assert "except CloudPaused" in src  # a cloud failure pauses with the expert's choices


def test_a_real_audit_pauses_on_a_cloud_failure_with_every_request_logged(tmp_path):
    """Synthetic case01 through the real pipeline: the run stops as failed with the reason, no
    claim after the failure is labeled by anything else, and the log holds every request."""
    from core import pipeline
    from core.audit._local_model import SENT_ACTION
    from core.contracts import GoldClaim
    from core.review.audit_log import verify_chain
    from eval import run_pipeline as rp
    from eval.run_eval import load_jsonl

    conn = rp.build_case("case01", tmp_path / "case01.db")
    gold = load_jsonl(rp.gold_path("case01"), GoldClaim)
    comps = rp.model_free_components(conn, rp.assumption_sheet("case01"), gold)
    unrelated = '{"stance": "unrelated", "quote": "", "rationale": "No."}'
    up = FakeCloud([unrelated] * 40 + [cloud.CloudError("ConnectionError: down", sticky=True)])
    comps.labeler = stance_mod.create(conn, cloud_model=up)
    comps.model_runs = (
        *[m for m in comps.model_runs if m.purpose != "stance"],
        *comps.labeler.model_runs,
    )
    with pytest.raises(CloudPaused):
        pipeline.run_audit(conn, comps)
    status, note = conn.execute("SELECT status, note FROM pipeline_runs").fetchone()
    assert status == "failed" and "stopped answering" in note
    sent = conn.execute("SELECT COUNT(*) FROM audit_log WHERE action = ?", (SENT_ACTION,))
    assert sent.fetchone()[0] == len(up.prompts) == 41 and verify_chain(conn)


class _Quoter:
    """Answers "supports" quoting the first three words of the record, like any model would."""

    def __init__(self, base: object) -> None:
        self.base = base

    def __getattr__(self, name: str) -> object:
        return getattr(self.base, name)

    def generate_json(self, prompt, schema, params=None):  # noqa: ANN001, ANN201
        record = prompt.split("[RECORD START]\n", 1)[1].split("\n[RECORD END]", 1)[0]
        quote = " ".join(record.split()[:3])
        self.base.prompts.append(prompt)
        return _Out(json.dumps({"stance": "supports", "quote": quote, "rationale": self.why}))


def test_an_item_relabeled_by_another_model_names_the_model_of_the_latest_run(tmp_path):
    from core import pipeline
    from core.contracts import GoldClaim
    from eval import run_pipeline as rp
    from eval.run_eval import load_jsonl

    conn = rp.build_case("case01", tmp_path / "case01.db")
    gold = load_jsonl(rp.gold_path("case01"), GoldClaim)
    claims = [g.claim_id for g in gold][:3]

    def audit(labeler) -> None:  # noqa: ANN001
        comps = rp.model_free_components(conn, rp.assumption_sheet("case01"), gold)
        comps.labeler = labeler
        comps.model_runs = (
            *[m for m in comps.model_runs if m.purpose != "stance"],
            *labeler.model_runs,
        )
        pipeline.run_audit(conn, comps, claim_ids=claims)

    local = _Quoter(FakeLocal([]))
    local.why = "local"
    audit(stance_mod.create(conn, model=local))
    up = _Quoter(FakeCloud([]))
    up.why = "cloud"
    cloud_lab = stance_mod.create(conn, cloud_model=up)
    audit(cloud_lab)
    rows = conn.execute("SELECT model_run_id, rationale FROM evidence_items").fetchall()
    assert rows and {r for r in rows} == {(_cloud_run(cloud_lab).id, "cloud")}


class _Misquoter(_Quoter):
    """Answers "supports" with a quote that is not in the record."""

    def generate_json(self, prompt, schema, params=None):  # noqa: ANN001, ANN201
        self.base.prompts.append(prompt)
        bad = {"stance": "supports", "quote": "words nobody wrote", "rationale": "x"}
        return _Out(json.dumps(bad))


def test_a_cloud_answer_that_failed_its_quote_check_is_asked_again(tmp_path):
    from core import pipeline
    from core.contracts import GoldClaim
    from eval import run_pipeline as rp
    from eval.run_eval import load_jsonl

    conn = rp.build_case("case01", tmp_path / "case01.db")
    gold = load_jsonl(rp.gold_path("case01"), GoldClaim)
    claims = [g.claim_id for g in gold][:3]

    def audit(labeler) -> None:  # noqa: ANN001
        comps = rp.model_free_components(conn, rp.assumption_sheet("case01"), gold)
        comps.labeler = labeler
        comps.model_runs = (
            *[m for m in comps.model_runs if m.purpose != "stance"],
            *labeler.model_runs,
        )
        pipeline.run_audit(conn, comps, claim_ids=claims)

    bad = _Misquoter(FakeCloud([]))
    audit(stance_mod.create(conn, cloud_model=bad))
    assert bad.base.prompts
    assert not conn.execute("SELECT 1 FROM evidence_items").fetchone()
    good = _Quoter(FakeCloud([]))
    good.why = "second try"
    audit(stance_mod.create(conn, cloud_model=good))
    assert len(good.base.prompts) == len(bad.base.prompts)  # asked again, nothing reused
    assert conn.execute("SELECT 1 FROM evidence_items").fetchone()


def test_nothing_is_logged_as_sent_when_the_client_cannot_be_built(case_db, monkeypatch):
    from core.audit._local_model import SENT_ACTION, SentLog

    monkeypatch.setitem(sys.modules, "anthropic", None)  # the cloud extra is not installed
    model = cloud.ClaudeModel(cloud.CloudConfig(api_key=KEY))
    with pytest.raises(cloud.CloudError, match="not installed"):
        SentLog(model, case_db).generate_json("p", {"type": "object"})
    sent = case_db.execute("SELECT 1 FROM audit_log WHERE action = ?", (SENT_ACTION,))
    assert sent.fetchone() is None


def test_a_retryable_failure_is_sent_again_and_every_send_is_logged(case_db):
    from core.audit._local_model import SENT_ACTION, SentLog

    down = cloud.CloudError("APIConnectionError: reset", sticky=True, retryable=True)
    up = FakeCloud([down, down, SUPPORTS])
    waits: list[float] = []
    log = SentLog(up, case_db, sleep=waits.append)
    assert log.generate_json("the prompt", {"type": "object"}).raw_text == SUPPORTS
    attempts = [
        json.loads(p)["attempt"]
        for (p,) in case_db.execute(
            "SELECT payload_json FROM audit_log WHERE action = ? ORDER BY seq", (SENT_ACTION,)
        )
    ]
    assert attempts == [1, 2, 3] and len(up.prompts) == 3 and waits == [2.0, 4.0]
    up = FakeCloud([down, down, down])
    with pytest.raises(cloud.CloudError):  # the third failure ends the retries
        SentLog(up, case_db, sleep=waits.append).generate_json("p", {"type": "object"})
    assert len(up.prompts) == 3


def test_a_request_that_cannot_be_logged_is_not_sent(case_db):
    from core.audit._local_model import SentLog

    up = FakeCloud([SUPPORTS])
    case_db.execute("BEGIN")  # an open write transaction: the log entry cannot be written
    with pytest.raises(CloudPaused, match="was not sent"):
        SentLog(up, case_db).generate_json("p", {"type": "object"})
    assert not up.prompts


@pytest.mark.parametrize(
    ("status", "name", "retry"),
    [
        (429, "RateLimitError", True),
        (529, "OverloadedError", True),
        (408, "X", True),
        (401, "AuthenticationError", False),
        (400, "BadRequestError", False),
        (None, "APIConnectionError", True),
        (None, "APITimeoutError", True),
        (None, "ValueError", False),
    ],  # fmt: skip
)
def test_which_failures_are_retried(status, name, retry):
    err = type(name, (Exception,), {"status_code": status})()
    assert cloud.is_retryable(err) is retry


def test_the_sdk_does_not_retry_unlogged():
    model, _ = _model(_resp())
    model._client = None
    pytest.importorskip("anthropic")
    assert model._get_client().max_retries == 0


def test_the_pill_stays_on_while_a_cloud_audit_runs_after_the_key_goes(tmp_path, monkeypatch):
    from core.casework import jobs

    app, get, post = _screen(tmp_path, monkeypatch)
    post("/cloud/key", api_key=KEY)
    post("/cloud/case", allowed="1")
    job = jobs.Job("audit", app.case.db)
    job.cloud = True
    app.jobs.current = job  # a cloud audit started with the key in place
    (tmp_path / "cloud.json").unlink()  # then the key file goes
    assert "Cloud labels on" in get("/setup").text
    job.end("done", "finished")
    assert "Offline" in get("/setup").text
