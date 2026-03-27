"""
LLM Client — unified interface for Groq / OpenAI / Gemini / Ollama.

v3 changes:
  - Gemini now uses google.genai (new SDK) instead of deprecated google.generativeai
  - Rate-limit errors raise immediately (no internal retry) so LLMRouter can
    failover to the other provider without wasting retry budget.
  - Other transient errors still retry with exponential backoff.
"""
import asyncio
import os
import time
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Markers that mean "don't bother retrying — tell the router to failover now"
_RATE_LIMIT_MARKERS = ("429", "rate limit", "rate_limit", "quota", "resource_exhausted",
                        "too many requests", "toomanyrequests")


def _is_rate_limit(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in _RATE_LIMIT_MARKERS)


class RateLimitError(Exception):
    """Raised immediately on 429/quota so the router can failover without delay."""


class LLMClient:
    """Async LLM client with automatic provider routing."""

    def __init__(self, provider: str = "groq", model: str = "llama-3.3-70b-versatile",
                 api_key: Optional[str] = None, temperature: float = 0.3, max_tokens: int = 4096):
        self.provider = provider.lower()
        self.model = model
        self.api_key = api_key or self._load_key()
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._client = None
        self._total_tokens = 0

    # ── Key loading ───────────────────────────────────────────────────────────
    def _load_key(self) -> Optional[str]:
        key_map = {
            "groq":   "GROQ_API_KEY",
            "openai": "OPENAI_API_KEY",
            "gemini": "GOOGLE_API_KEY",
            "ollama": None,
        }
        env_var = key_map.get(self.provider)
        if not env_var:
            return None
        return os.getenv(env_var) or os.getenv("GEMINI_API_KEY") if self.provider == "gemini" else os.getenv(env_var)

    # ── Client initialisation ─────────────────────────────────────────────────
    def _get_client(self):
        if self._client:
            return self._client
        if self.provider == "groq":
            from groq import AsyncGroq
            self._client = AsyncGroq(api_key=self.api_key)
        elif self.provider == "openai":
            from openai import AsyncOpenAI
            self._client = AsyncOpenAI(api_key=self.api_key)
        elif self.provider == "gemini":
            # New SDK: google.genai (replaces deprecated google.generativeai)
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
                self._gemini_sdk = "new"
            except (ImportError, AttributeError):
                # Fallback to old SDK if new one not installed
                import google.generativeai as genai_old
                genai_old.configure(api_key=self.api_key)
                self._client = genai_old.GenerativeModel(self.model)
                self._gemini_sdk = "old"
        elif self.provider == "ollama":
            from ollama import AsyncClient
            self._client = AsyncClient()
        else:
            raise ValueError(f"Unknown provider: {self.provider}")
        return self._client

    # ── Core completion ───────────────────────────────────────────────────────
    async def complete(self, prompt: str, system: str = "", retries: int = 3) -> str:
        for attempt in range(retries):
            try:
                result = await self._dispatch(prompt, system)
                return result
            except RateLimitError:
                # Propagate immediately — no retry, let the router failover
                raise
            except Exception as e:
                if _is_rate_limit(e):
                    # Wrap and raise immediately without retry
                    raise RateLimitError(str(e)) from e
                wait = 2 ** attempt
                logger.warning(f"LLM attempt {attempt+1} failed: {e}. Retrying in {wait}s…")
                if attempt < retries - 1:
                    await asyncio.sleep(wait)
        raise RuntimeError(f"LLM failed after {retries} attempts")

    async def _dispatch(self, prompt: str, system: str) -> str:
        client = self._get_client()
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        if self.provider in ("groq", "openai"):
            resp = await client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            self._total_tokens += resp.usage.total_tokens if resp.usage else 0
            return resp.choices[0].message.content.strip()

        elif self.provider == "gemini":
            full_prompt = f"{system}\n\n{prompt}" if system else prompt
            sdk = getattr(self, "_gemini_sdk", "old")
            if sdk == "new":
                # google.genai async API
                resp = await asyncio.to_thread(
                    client.models.generate_content,
                    model=self.model,
                    contents=full_prompt,
                )
                return resp.text.strip()
            else:
                # Legacy google.generativeai
                resp = await asyncio.to_thread(client.generate_content, full_prompt)
                return resp.text.strip()

        elif self.provider == "ollama":
            resp = await client.chat(model=self.model, messages=messages)
            return resp["message"]["content"].strip()

        raise ValueError(f"Unsupported provider: {self.provider}")

    # ── Structured JSON completion ────────────────────────────────────────────
    async def complete_json(self, prompt: str, system: str = "") -> dict:
        import json
        json_system = (system + "\n\nRespond ONLY with valid JSON. No markdown, no backticks.").strip()
        raw = await self.complete(prompt, json_system)
        raw = raw.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse error: {e}\nRaw: {raw[:500]}")
            raise

    @property
    def total_tokens_used(self) -> int:
        return self._total_tokens
