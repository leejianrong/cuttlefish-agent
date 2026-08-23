"""A keyless, deterministic ``LlmProvider`` for tests (QUESTIONS.md Q11).

The same shape sibei-flow's own replay provider uses: canned responses, returned in
call order, with no network call and no API key required. A workflow test configures
one of these instead of a real provider so cuttlefish's own reasoning calls are
exercised deterministically.
"""

from __future__ import annotations

from collections.abc import Sequence

from cuttlefish.llm.provider import LlmResponse


class ExhaustedReplayError(RuntimeError):
    """The replay provider was called more times than it has canned responses for."""


class ReplayLlmProvider:
    """Returns `responses` in order, one per call. Raises once they run out."""

    def __init__(self, responses: Sequence[LlmResponse]) -> None:
        self._responses = list(responses)
        self._next = 0

    async def complete(self, prompt: str) -> LlmResponse:
        if self._next >= len(self._responses):
            raise ExhaustedReplayError(
                f"ReplayLlmProvider has no response left for call {self._next + 1} "
                f"(prompt: {prompt!r})"
            )
        response = self._responses[self._next]
        self._next += 1
        return response
