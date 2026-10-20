"""Chat templates that think before answering: the no-think check and the open-block guard.

The templates below copy the generation-prompt endings of the real model files (Qwen3-14B,
Qwen3.8-27B and Gemma 4, read from their GGUF metadata on 2026-10-20); the rest is trimmed.
"""

from __future__ import annotations

import jinja2
import pytest

from core.llm.runtime import (
    NO_THINK_SUFFIX,
    no_think_handler,
    opens_thinking,
    refuse_open_thinking,
    renders_without_thinking,
)

_TURNS = (
    "{%- for m in messages %}"
    "{{- '<|im_start|>' + m.role + '\\n' + m.content + '<|im_end|>\\n' }}"
    "{%- endfor %}"
)
QWEN3 = (
    _TURNS + "{%- if add_generation_prompt %}{{- '<|im_start|>assistant\\n' }}"
    "{%- if enable_thinking is defined and enable_thinking is false %}"
    "{{- '<think>\\n\\n</think>\\n\\n' }}{%- endif %}{%- endif %}"
)
QWEN3_8 = (
    "{%- if enable_thinking is undefined or enable_thinking is true %}"
    "{{- '<|im_start|>system\\nReasoning effort is set to xhigh.<|im_end|>\\n' }}{%- endif %}"
    + _TURNS
    + "{%- if add_generation_prompt %}{{- '<|im_start|>assistant\\n' }}"
    "{%- if enable_thinking is defined and enable_thinking is false %}"
    "{{- '<think>\\n\\n</think>\\n\\n' }}{%- else %}{{- '<think>\\n' }}{%- endif %}{%- endif %}"
)
GEMMA4 = (
    "{%- for m in messages -%}{{- '<|turn>' + m.role + '\\n' + m.content + '<turn|>\\n' -}}"
    "{%- endfor -%}{%- if add_generation_prompt -%}{{- '<|turn>model\\n' -}}"
    "{%- if not enable_thinking -%}{{- '<|channel>thought\\n<channel|>' -}}{%- endif -%}"
    "{%- endif -%}"
)
MESSAGES = [{"role": "user", "content": "x"}]


def render(template: str, **kwargs: object) -> str:
    env = jinja2.Environment()  # noqa: S701 - chat templates render text, not HTML
    return env.from_string(template).render(messages=MESSAGES, add_generation_prompt=True, **kwargs)


def test_qwen3_no_think_adds_an_empty_block():
    plain, no_think = render(QWEN3), render(QWEN3, enable_thinking=False)
    assert no_think == plain + NO_THINK_SUFFIX
    assert renders_without_thinking(plain, no_think)
    assert not opens_thinking(plain)


def test_qwen3_8_no_think_closes_the_block_it_would_open():
    plain, no_think = render(QWEN3_8), render(QWEN3_8, enable_thinking=False)
    assert plain.startswith("<|im_start|>system\nReasoning effort")
    assert plain.endswith("<|im_start|>assistant\n<think>\n")
    assert no_think == "<|im_start|>user\nx<|im_end|>\n<|im_start|>assistant\n" + NO_THINK_SUFFIX
    assert opens_thinking(plain)
    assert renders_without_thinking(plain, no_think)
    assert not opens_thinking(no_think)


def test_gemma4_starts_without_thinking_so_no_think_has_nothing_to_change():
    plain = render(GEMMA4)
    assert plain.endswith("<|turn>model\n<|channel>thought\n<channel|>")
    assert not opens_thinking(plain)
    assert not renders_without_thinking(plain, render(GEMMA4, enable_thinking=False))


@pytest.mark.parametrize(
    "no_think",
    [
        "<|im_start|>user\nx<|im_end|>\n<|im_start|>assistant\n<think>\nok</think>\n\n",
        "<|im_start|>user\ny<|im_end|>\n<|im_start|>assistant\n" + NO_THINK_SUFFIX,
        "<|im_start|>user\nx<|im_end|>\n<|im_start|>assistant\n",
        "<|im_start|>assistant\n" + NO_THINK_SUFFIX,
    ],
)
def test_any_other_difference_is_refused(no_think):
    assert not renders_without_thinking(render(QWEN3_8), no_think)


class _FakeInner:
    def token_get_text(self, token: int) -> str:
        return {1: "<|endoftext|>", 2: "<bos>"}[token]


class _FakeLlama:
    """Just what the template helpers read from a loaded llama_cpp.Llama."""

    def __init__(self, template: str) -> None:
        self.metadata = {"tokenizer.chat_template": template}
        self._model = _FakeInner()

    def token_eos(self) -> int:
        return 1

    def token_bos(self) -> int:
        return 2


def test_llama_cpp_renders_the_same_endings():
    pytest.importorskip("llama_cpp")
    assert callable(no_think_handler(_FakeLlama(QWEN3)))
    assert callable(no_think_handler(_FakeLlama(QWEN3_8)))
    with pytest.raises(ValueError, match="refusing to guess"):
        no_think_handler(_FakeLlama(GEMMA4))
    refuse_open_thinking(_FakeLlama(QWEN3))
    refuse_open_thinking(_FakeLlama(GEMMA4))
    with pytest.raises(ValueError, match="no-think"):
        refuse_open_thinking(_FakeLlama(QWEN3_8))


def fake_llama_cpp(monkeypatch, template: str) -> None:
    """Stand-ins for llama_cpp.Llama and its Jinja2ChatFormatter, so the load path runs in CI."""
    import sys
    import types

    class Rendered:
        def __init__(self, prompt: str) -> None:
            self.prompt = prompt

    class Formatter:
        def __init__(self, template: str, eos_token: str, bos_token: str, **_: object) -> None:
            self.template = template

        def __call__(self, *, messages: list, **kwargs: object) -> Rendered:
            env = jinja2.Environment()  # noqa: S701 - chat templates render text, not HTML
            return Rendered(
                env.from_string(self.template).render(
                    messages=messages, add_generation_prompt=True, **kwargs
                )
            )

        def to_chat_handler(self) -> object:
            return self

    class Llama(_FakeLlama):
        def __init__(self, **_: object) -> None:
            super().__init__(template)
            self.chat_handler = None

    chat_format = types.ModuleType("llama_cpp.llama_chat_format")
    chat_format.Jinja2ChatFormatter = Formatter
    module = types.ModuleType("llama_cpp")
    module.Llama = Llama
    module.llama_chat_format = chat_format
    monkeypatch.setitem(sys.modules, "llama_cpp", module)
    monkeypatch.setitem(sys.modules, "llama_cpp.llama_chat_format", chat_format)


def load(tmp_path, chat_template: str = "gguf", chat_format: str | None = None):
    from core.llm.runtime import GenerationParams, LlamaCppModel, ModelSpec

    path = tmp_path / "m.gguf"
    path.write_bytes(b"GGUF")
    spec = ModelSpec(name="m", path=path, chat_format=chat_format)
    return LlamaCppModel(spec, GenerationParams(chat_template=chat_template))


def test_load_refuses_a_template_that_opens_thinking(monkeypatch, tmp_path):
    fake_llama_cpp(monkeypatch, QWEN3_8)
    with pytest.raises(ValueError, match="no-think"):
        load(tmp_path)
    model = load(tmp_path, chat_template="no-think")
    assert model._llm.chat_handler is not None
    load(tmp_path, chat_format="chatml")  # a named format never uses the file's template


@pytest.mark.parametrize("template", [QWEN3, GEMMA4])
def test_load_keeps_templates_that_answer_without_thinking(monkeypatch, tmp_path, template):
    fake_llama_cpp(monkeypatch, template)
    assert load(tmp_path)._llm.chat_handler is None
