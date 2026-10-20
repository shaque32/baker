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
