"""
LLMRouter — Dual-provider router for Groq + Gemini.

v3.1 fixes:
  - When ALL providers are on cooldown, router now WAITS for the soonest
    one to come back instead of burning through retries instantly and failing.
  - Provider-specific cooldowns: Groq 30s, Gemini 90s.
  - RateLimitError from LLMClient triggers immediate failover (no wasted retries).
"""
import asyncio
import logging
import os
import time
from typing import Optional

from .llm_client import RateLimitError

logger = logging.getLogger(__name__)

GEMINI_PREFERRED_SKILLS = {"docs", "scaffolding", "deployment"}
GROQ_PREFERRED_SKILLS   = {"components", "routing", "api", "database", "auth",
                            "state", "ml_model", "testing", "styling", "mobile"}

GROQ_COOLDOWN_SECONDS   = 30
GEMINI_COOLDOWN_SECONDS = 90
MAX_RETRIES             = 6    # increased — most will be wait+retry, not blind loops


class ProviderSlot:
    def __init__(self, name: str, client, cooldown_seconds: float = 60):
        self.name             = name
        self.client           = client
        self.default_cooldown = cooldown_seconds
        self.tokens_used      = 0
        self.requests_ok      = 0
        self.requests_failed  = 0
        self._cooldown_until  = 0.0

    @property
    def available(self) -> bool:
        return time.time() >= self._cooldown_until

    @property
    def cooldown_remaining(self) -> float:
        return max(0.0, self._cooldown_until - time.time())

    def cooldown(self, seconds: Optional[float] = None):
        secs = seconds if seconds is not None else self.default_cooldown
        self._cooldown_until = time.time() + secs
        logger.warning(f"[Router] {self.name} cooling down for {secs:.0f}s")

    def record_success(self, tokens: int = 0):
        self.requests_ok += 1
        self.tokens_used += tokens

    def record_failure(self):
        self.requests_failed += 1


class LLMRouter:
    def __init__(
        self,
        groq_key:     Optional[str] = None,
        gemini_key:   Optional[str] = None,
        groq_model:   str   = "llama-3.3-70b-versatile",
        gemini_model: str   = "gemini-2.0-flash",
        temperature:  float = 0.3,
        max_tokens:   int   = 4096,
    ):
        from .llm_client import LLMClient

        self.groq_slot:   Optional[ProviderSlot] = None
        self.gemini_slot: Optional[ProviderSlot] = None

        gk = groq_key   or os.getenv("GROQ_API_KEY")
        mk = gemini_key or os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")

        if gk:
            self.groq_slot = ProviderSlot(
                "Groq",
                LLMClient(provider="groq", model=groq_model, api_key=gk,
                          temperature=temperature, max_tokens=max_tokens),
                cooldown_seconds=GROQ_COOLDOWN_SECONDS,
            )
            logger.info("[Router] Groq registered ✓")
        else:
            logger.warning("[Router] No GROQ_API_KEY — Groq disabled")

        if mk:
            self.gemini_slot = ProviderSlot(
                "Gemini",
                LLMClient(provider="gemini", model=gemini_model, api_key=mk,
                          temperature=temperature, max_tokens=max_tokens),
                cooldown_seconds=GEMINI_COOLDOWN_SECONDS,
            )
            logger.info("[Router] Gemini registered ✓")
        else:
            logger.warning("[Router] No GOOGLE_API_KEY / GEMINI_API_KEY — Gemini disabled")

        if not self.groq_slot and not self.gemini_slot:
            raise RuntimeError(
                "No LLM provider configured. "
                "Set GROQ_API_KEY and/or GOOGLE_API_KEY."
            )

    # ── Public interface ──────────────────────────────────────────────────────

    async def complete(self, prompt: str, system: str = "",
                       skill: str = "", retries: int = MAX_RETRIES) -> str:
        all_slots = [s for s in [self.groq_slot, self.gemini_slot] if s]
        last_err  = None

        for attempt in range(retries):
            # ── Wait if ALL providers are on cooldown ──────────────────────
            if all(not s.available for s in all_slots):
                wait_secs = min(s.cooldown_remaining for s in all_slots)
                logger.info(
                    f"[Router] All providers on cooldown — "
                    f"waiting {wait_secs:.1f}s for soonest to recover"
                )
                await asyncio.sleep(wait_secs + 0.5)   # +0.5s buffer

            # ── Pick the best available provider ───────────────────────────
            ordered = self._elect(skill)
            slot = next((s for s in ordered if s.available), None)

            if slot is None:
                # Shouldn't happen after the wait above, but be safe
                await asyncio.sleep(2)
                continue

            try:
                result = await slot.client.complete(prompt, system)
                slot.record_success(slot.client.total_tokens_used)
                if attempt > 0:
                    logger.info(f"[Router] {slot.name} succeeded on attempt {attempt+1}")
                return result

            except RateLimitError as exc:
                last_err = exc
                slot.record_failure()
                slot.cooldown()
                logger.warning(f"[Router] {slot.name} rate-limited → immediate failover")
                # No sleep — loop immediately to pick the other provider

            except Exception as exc:
                last_err = exc
                slot.record_failure()
                slot.cooldown(5)
                wait = min(2 ** attempt, 8)
                logger.warning(f"[Router] {slot.name} error: {exc} — waiting {wait}s")
                await asyncio.sleep(wait)

        raise RuntimeError(
            f"All providers exhausted after {retries} attempts. "
            f"Last error: {last_err}"
        )

    async def complete_json(self, prompt: str, system: str = "",
                            skill: str = "") -> dict:
        import json
        json_system = (
            system + "\n\nRespond ONLY with valid JSON. No markdown, no backticks."
        ).strip()
        raw = await self.complete(prompt, json_system, skill=skill)
        raw = raw.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.error(f"[Router] JSON parse error: {exc}\nRaw: {raw[:400]}")
            raise

    @property
    def total_tokens_used(self) -> int:
        total = 0
        if self.groq_slot:   total += self.groq_slot.tokens_used
        if self.gemini_slot: total += self.gemini_slot.tokens_used
        return total

    def stats(self) -> dict:
        out = {}
        for slot in [self.groq_slot, self.gemini_slot]:
            if slot:
                out[slot.name] = {
                    "tokens":    slot.tokens_used,
                    "ok":        slot.requests_ok,
                    "failed":    slot.requests_failed,
                    "available": slot.available,
                }
        return out

    def _elect(self, skill: str) -> list:
        slots = [s for s in [self.groq_slot, self.gemini_slot] if s]
        if len(slots) == 1:
            return slots
        if skill in GEMINI_PREFERRED_SKILLS and self.gemini_slot and self.gemini_slot.available:
            return [self.gemini_slot, self.groq_slot]
        return [self.groq_slot, self.gemini_slot]
