"""Cloud first, local behind it: the cloud stance labeler, its fallback and the per-case choice.

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
from core.audit._llm_json import ModelUnavailable
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


def _runs(lab) -> tuple:  # noqa: ANN001
    cloud_run, local_run = lab.model_runs
    assert cloud_run.model_sha256.startswith("api:") and local_run.model_sha256 == SHA
    return cloud_run, local_run


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
    "raw", [{}, {"api_key": "k", "effort": "turbo"}, {"api_key": "k", "base_url": "http://x"}]
)
def test_bad_or_missing_config_is_refused(tmp_path, monkeypatch, raw):
    monkeypatch.delenv(cloud.KEY_ENV, raising=False)
    p = tmp_path / "cloud.json"
    p.write_text(json.dumps(raw))
    with pytest.raises(cloud.CloudConfigError):
        cloud.load_config(p)


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


# ---------------------------------------------------------------- the labeler and fallback


def test_cloud_labels_first_and_the_item_names_the_cloud_run(case_db, fake_context):
    up, local = FakeCloud([SUPPORTS]), FakeLocal([])
    lab = stance_mod.create(case_db, model=local, cloud_model=up)
    cloud_run, _ = _runs(lab)
    label = lab.label(make_assumption("They met at the garage."), _cand())
    assert label.model_run_id == cloud_run.id and not local.prompts
    assert ">> CONTEXT FOR msg:7" in up.prompts[0]


def test_a_sticky_failure_sends_this_and_every_later_call_to_the_local_model(case_db, fake_context):
    up = FakeCloud([cloud.CloudError("ConnectionError: down", sticky=True)])
    local = FakeLocal([SUPPORTS, SUPPORTS])
    lab = stance_mod.create(case_db, model=local, cloud_model=up)
    cloud_run, local_run = _runs(lab)
    a = make_assumption("They met at the garage.")
    first = lab.label(a, _cand("msg:1"))
    second = lab.label(a, _cand("msg:2"))
    assert first.model_run_id == local_run.id == second.model_run_id
    assert len(up.prompts) == 1 and len(local.prompts) == 2  # the cloud is not asked again
    assert up.prompts[0] == local.prompts[0]  # the same question, word for word
    calls = [(c.model_run_id, c.outcome.value) for c in lab.recorder.calls]
    assert calls == [(cloud_run.id, "error"), (local_run.id, "ok"), (local_run.id, "ok")]
    assert lab.model.fell_back == "ConnectionError: down"


def test_a_refusal_sends_only_that_call_to_the_local_model(case_db, fake_context):
    up = FakeCloud([cloud.CloudError("declined", sticky=False), SUPPORTS])
    local = FakeLocal([SUPPORTS])
    lab = stance_mod.create(case_db, model=local, cloud_model=up)
    cloud_run, local_run = _runs(lab)
    a = make_assumption("They met at the garage.")
    assert lab.label(a, _cand("msg:1")).model_run_id == local_run.id
    assert lab.label(a, _cand("msg:2")).model_run_id == cloud_run.id
    assert lab.model.fell_back is None


def test_a_cloud_answer_that_fails_validation_is_asked_again_locally(case_db, fake_context):
    long = '{"stance": "supports", "quote": "garage", "rationale": "' + "x" * 1001 + '"}'
    up = FakeCloud([long, SUPPORTS])
    local = FakeLocal([SUPPORTS])
    lab = stance_mod.create(case_db, model=local, cloud_model=up)
    cloud_run, local_run = _runs(lab)
    a = make_assumption("They met at the garage.")
    assert lab.label(a, _cand("msg:1")).model_run_id == local_run.id
    assert lab.label(a, _cand("msg:2")).model_run_id == cloud_run.id
    outcomes = [(c.model_run_id, c.outcome.value) for c in lab.recorder.calls]
    assert outcomes[0] == (cloud_run.id, "invalid_output")


def test_with_no_local_model_a_cloud_failure_stops_the_run(case_db, fake_context, monkeypatch):
    monkeypatch.setenv("BAKER_MODEL_CONFIG", "/nonexistent/model.json")
    up = FakeCloud([cloud.CloudError("ConnectionError: down", sticky=True)])
    lab = stance_mod.create(case_db, cloud_model=up)
    (only,) = lab.model_runs
    assert only.model_sha256.startswith("api:")
    with pytest.raises(ModelUnavailable, match="no local model is set up"):
        lab.label(make_assumption("They met at the garage."), _cand())


def test_without_cloud_the_labeler_is_the_local_model_alone(case_db, fake_context):
    local = FakeLocal([SUPPORTS])
    lab = stance_mod.create(case_db, model=local)
    (run,) = lab.model_runs
    assert lab.label(make_assumption("They met at the garage."), _cand()).model_run_id == run.id
    assert not hasattr(lab.model, "retry_locally")


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
    lab = stance_mod.create(case_db, model=FakeLocal([]), cloud_model=FakeCloud([]))
    case_db.execute("PRAGMA foreign_keys = OFF")
    for m in lab.model_runs:
        case_db.execute(
            "INSERT INTO model_runs (id, pipeline_run_id, purpose, model_name, model_sha256,"
            " prompt_version, prompt_sha256, params_json, seed, started_at_utc)"
            " VALUES (?, 'run:x', 'stance', ?, ?, 'v', 's', '{}', NULL, '2026-10-15T00:00:00Z')",
            (m.id, m.model_name, m.model_sha256),
        )
    cloud_run, local_run = _runs(lab)
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
    assert "Cloud first" in page and "Cloud labels on" in page

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
    assert "cloud=choice" in src and "cloud_policy.choose(conn)" in src
