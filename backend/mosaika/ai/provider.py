"""Provider dell'assistente. L'interfaccia è un solo metodo `complete`."""

from __future__ import annotations

import logging
from typing import Protocol

import httpx

from mosaika.ai.testo import componi_frasi, estrai_blocchi_validati

log = logging.getLogger("mosaika.ai")


class AINonConfigurata(RuntimeError):
    pass


class AIProvider(Protocol):
    name: str

    def complete(self, *, system: str, user: str) -> str: ...


class MockAIProvider:
    """Non chiama nessuna rete. Ricuce solo i blocchi [VALIDATA] del messaggio."""

    name = "mock"

    def __init__(self) -> None:
        self.chiamate = 0
        self.ultimo_system = ""
        self.ultimo_user = ""

    def complete(self, *, system: str, user: str) -> str:
        self.chiamate += 1
        self.ultimo_system = system
        self.ultimo_user = user
        return componi_frasi(estrai_blocchi_validati(user))


class OpenAICompatibleProvider:
    """Endpoint chat compatibile con OpenAI. La chiave sta in MOSAIKA_AI_API_KEY."""

    name = "openai"

    def __init__(self, settings) -> None:
        self.api_key = settings.ai_api_key
        self.base_url = (settings.ai_base_url or "").rstrip("/")
        self.model = settings.ai_model

    def complete(self, *, system: str, user: str) -> str:
        if not self.api_key:
            raise AINonConfigurata("Manca MOSAIKA_AI_API_KEY")
        response = httpx.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json={
                "model": self.model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            },
            timeout=30,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return (content or "").strip()


def build_provider(settings) -> AIProvider:
    if settings.ai_provider == "mock":
        return MockAIProvider()
    if settings.ai_provider == "openai":
        return OpenAICompatibleProvider(settings)
    raise RuntimeError(
        f"MOSAIKA_AI_PROVIDER non riconosciuto: {settings.ai_provider}. "
        "Valori ammessi: mock, openai."
    )
