"""LLM client: OpenAI for real, echo for keyless dev/tests."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterator, Literal

from ..config import get_settings

log = logging.getLogger(__name__)

# Approximate OpenAI pricing (USD per 1M tokens) — update when rates change.
PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
}


@dataclass(slots=True)
class StreamChunk:
    kind: Literal["text", "usage"]
    text: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


class OpenAIClient:
    def __init__(self, api_key: str, model: str) -> None:
        from openai import OpenAI

        self._client = OpenAI(api_key=api_key)
        self.model = model

    def stream(self, *, system: str, user: str, max_tokens: int = 1024) -> Iterator[StreamChunk]:
        stream = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            stream=True,
            stream_options={"include_usage": True},
        )
        for event in stream:
            if event.choices and event.choices[0].delta and event.choices[0].delta.content:
                yield StreamChunk(kind="text", text=event.choices[0].delta.content)
            if getattr(event, "usage", None):
                yield StreamChunk(
                    kind="usage",
                    input_tokens=event.usage.prompt_tokens,
                    output_tokens=event.usage.completion_tokens,
                )

    def complete(self, prompt: str, *, system: str = "", max_tokens: int = 512) -> str:
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system or "You are a helpful assistant."},
                {"role": "user", "content": prompt},
            ],
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""

    def cost_usd(self, input_tokens: int, output_tokens: int) -> float:
        in_rate, out_rate = PRICING.get(self.model, (0, 0))
        return (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000


class EchoClient:
    """No-network LLM. Returns a deterministic fake answer with a citation."""
    model = "echo"

    def stream(self, *, system: str, user: str, max_tokens: int = 1024) -> Iterator[StreamChunk]:
        text = self._fake_answer(user)
        for ch in text:
            yield StreamChunk(kind="text", text=ch)
        yield StreamChunk(kind="usage", input_tokens=len(user) // 4, output_tokens=len(text) // 4)

    def complete(self, prompt: str, *, system: str = "", max_tokens: int = 512) -> str:
        return self._fake_answer(prompt)

    def cost_usd(self, input_tokens: int, output_tokens: int) -> float:
        return 0.0

    @staticmethod
    def _fake_answer(prompt: str) -> str:
        head = prompt.strip().splitlines()[-1] if prompt.strip() else "the question"
        return f"From the retrieved context, the answer to '{head[:80]}' is described in [SOURCE 1]."


@lru_cache(maxsize=1)
def get_llm():
    """Pick the configured LLM. The whole app uses one client."""
    s = get_settings()
    if s.llm_provider == "openai" and s.openai_api_key:
        return OpenAIClient(s.openai_api_key, s.llm_model)
    log.info("Using echo LLM client (no OPENAI_API_KEY configured)")
    return EchoClient()
