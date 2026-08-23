from __future__ import annotations

import pytest

from cuttlefish.llm.provider import LlmResponse
from cuttlefish.llm.replay import ExhaustedReplayError, ReplayLlmProvider


async def test_returns_responses_in_call_order() -> None:
    provider = ReplayLlmProvider(
        [LlmResponse(model="replay", text="first"), LlmResponse(model="replay", text="second")]
    )
    first = await provider.complete("prompt one")
    second = await provider.complete("prompt two")
    assert first.text == "first"
    assert second.text == "second"


async def test_raises_once_responses_are_exhausted() -> None:
    provider = ReplayLlmProvider([LlmResponse(model="replay", text="only")])
    await provider.complete("prompt one")
    with pytest.raises(ExhaustedReplayError):
        await provider.complete("prompt two")
