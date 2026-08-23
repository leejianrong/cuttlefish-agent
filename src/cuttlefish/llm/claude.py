"""A real Claude provider for cuttlefish's own reasoning calls (QUESTIONS.md Q11).

Credentials resolve exactly the way the Anthropic SDK always does — ``ANTHROPIC_API_KEY``,
or any other source ``anthropic.AsyncAnthropic()`` checks — never handled by this module
directly, and never logged (ADR-0004's redactor is what keeps a value like this out of
the episodic journal if it ever ends up in a tool result, but this module has no reason
to see the key at all: the SDK reads it itself).
"""

from __future__ import annotations

import anthropic

from cuttlefish.llm.provider import LlmResponse

DEFAULT_MODEL = "claude-opus-5"
DEFAULT_MAX_TOKENS = 4096


class ClaudeLlmProvider:
    """One prompt in, one response out, over the real Anthropic API."""

    def __init__(self, *, model: str = DEFAULT_MODEL, max_tokens: int = DEFAULT_MAX_TOKENS) -> None:
        self._client = anthropic.AsyncAnthropic()
        self._model = model
        self._max_tokens = max_tokens

    async def complete(self, prompt: str) -> LlmResponse:
        response = await self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        return LlmResponse(
            model=response.model,
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
