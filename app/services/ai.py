"""AI provider: one interface, mock or live Gemini (AI Studio key or Vertex AI).

Callers always pass a deterministic `fallback`. Mock mode returns it; live mode
returns it if Gemini fails, so the demo never breaks. AI output explains and
drafts only - decisions and amounts come from Python services.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator
from typing import Any

from app.config import get_settings

log = logging.getLogger("finguard.ai")


class AIProvider:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._client = None
        if self.settings.live_ai:
            try:
                from google import genai

                if self.settings.use_vertex:
                    self._client = genai.Client(
                        vertexai=True,
                        project=self.settings.gcp_project_id,
                        location=self.settings.gcp_location,
                    )
                else:
                    self._client = genai.Client(api_key=self.settings.gemini_api_key)
            except Exception as exc:  # missing SDK or bad config -> stay in mock mode
                log.warning("Gemini unavailable, using mock AI: %s", exc)

    @property
    def mode(self) -> str:
        if self._client is None:
            return "mock"
        return "vertex" if self.settings.use_vertex else "gemini-api"

    def _model(self, pro: bool) -> str:
        return self.settings.gemini_pro_model if pro else self.settings.gemini_fast_model

    def _contents(self, prompt: str, file_bytes: bytes | None, mime_type: str | None) -> list[Any]:
        contents: list[Any] = []
        if file_bytes and mime_type:
            from google.genai import types

            contents.append(types.Part.from_bytes(data=file_bytes, mime_type=mime_type))
        contents.append(prompt)
        return contents

    def text(self, prompt: str, fallback: str, pro: bool = False) -> str:
        if self._client is None:
            return fallback
        try:
            resp = self._client.models.generate_content(model=self._model(pro), contents=prompt)
            return (resp.text or "").strip() or fallback
        except Exception as exc:
            log.warning("Gemini text call failed: %s", exc)
            return fallback

    def json(
        self,
        prompt: str,
        fallback: dict[str, Any],
        file_bytes: bytes | None = None,
        mime_type: str | None = None,
        pro: bool = False,
    ) -> dict[str, Any]:
        if self._client is None:
            return fallback
        try:
            from google.genai import types

            resp = self._client.models.generate_content(
                model=self._model(pro),
                contents=self._contents(prompt, file_bytes, mime_type),
                config=types.GenerateContentConfig(response_mime_type="application/json"),
            )
            data = json.loads(resp.text or "{}")
            return data if isinstance(data, dict) and data else fallback
        except Exception as exc:
            log.warning("Gemini json call failed: %s", exc)
            return fallback

    def stream(self, prompt: str, fallback: str, pro: bool = True) -> Iterator[str]:
        if self._client is not None:
            try:
                emitted = False
                for chunk in self._client.models.generate_content_stream(model=self._model(pro), contents=prompt):
                    if chunk.text:
                        emitted = True
                        yield chunk.text
                if emitted:
                    return
            except Exception as exc:
                log.warning("Gemini stream failed: %s", exc)
        # Mock streaming: word chunks with a small delay for the typing effect
        words = fallback.split(" ")
        for i in range(0, len(words), 3):
            yield " ".join(words[i : i + 3]) + " "
            time.sleep(0.03)


_provider: AIProvider | None = None


def get_ai() -> AIProvider:
    global _provider
    if _provider is None:
        _provider = AIProvider()
    return _provider
