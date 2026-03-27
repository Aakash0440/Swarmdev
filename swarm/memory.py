"""
Stigmergy Memory — shared pheromone store backed by ChromaDB.
Agents deposit signals; others read them to coordinate without direct messaging.
"""
import asyncio
import hashlib
import json
import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)


class StigmergyMemory:
    """
    Swarm shared memory inspired by ant colony stigmergy.
    Each 'pheromone' is a key-value entry with a strength that decays over time.
    """

    def __init__(self, persist_path: str = "./chroma_db", decay_rate: float = 0.05,
                 use_chroma: bool = True):
        self.decay_rate = decay_rate
        self.use_chroma = use_chroma
        self._local: dict[str, dict] = {}   # always available fallback
        self._collection = None
        if use_chroma:
            self._init_chroma(persist_path)

    # ── ChromaDB init ─────────────────────────────────────────────────────────
    def _init_chroma(self, path: str):
        try:
            import chromadb
            client = chromadb.PersistentClient(path=path)
            self._collection = client.get_or_create_collection(
                name="swarm_memory",
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("ChromaDB stigmergy store ready")
        except Exception as e:
            logger.warning(f"ChromaDB unavailable ({e}), using in-memory store")
            self._collection = None

    # ── Deposit (write) ───────────────────────────────────────────────────────
    async def deposit(self, key: str, value: Any, strength: float = 1.0,
                      agent_id: str = "system", tags: list[str] | None = None):
        """Deposit a pheromone signal into shared memory."""
        doc_id = self._make_id(key)
        payload = {
            "key": key,
            "value": json.dumps(value) if not isinstance(value, str) else value,
            "strength": strength,
            "agent_id": agent_id,
            "timestamp": time.time(),
            "tags": json.dumps(tags or []),
        }
        # Local store (always)
        self._local[key] = payload

        # ChromaDB (if available)
        if self._collection:
            try:
                await asyncio.to_thread(
                    self._collection.upsert,
                    ids=[doc_id],
                    documents=[payload["value"]],
                    metadatas=[{k: v for k, v in payload.items() if k != "value"}],
                )
            except Exception as e:
                logger.debug(f"ChromaDB deposit error: {e}")

    # ── Retrieve (read) ───────────────────────────────────────────────────────
    async def retrieve(self, key: str) -> Optional[Any]:
        """Retrieve a pheromone by exact key."""
        entry = self._local.get(key)
        if entry:
            return self._parse_value(entry["value"])
        if self._collection:
            try:
                doc_id = self._make_id(key)
                result = await asyncio.to_thread(self._collection.get, ids=[doc_id])
                if result["documents"]:
                    return self._parse_value(result["documents"][0])
            except Exception:
                pass
        return None

    # ── Semantic search ───────────────────────────────────────────────────────
    async def search(self, query: str, n: int = 5) -> list[dict]:
        """Search memory by semantic similarity."""
        if self._collection:
            try:
                results = await asyncio.to_thread(
                    self._collection.query,
                    query_texts=[query],
                    n_results=min(n, max(1, self._collection.count())),
                )
                items = []
                for doc, meta in zip(results["documents"][0], results["metadatas"][0]):
                    items.append({"value": self._parse_value(doc), **meta})
                return items
            except Exception as e:
                logger.debug(f"Search error: {e}")
        # Fallback: substring match on local store
        query_lower = query.lower()
        matches = [
            {"value": self._parse_value(v["value"]), **v}
            for k, v in self._local.items()
            if query_lower in k.lower() or query_lower in v["value"].lower()
        ]
        return matches[:n]

    # ── Pheromone decay ───────────────────────────────────────────────────────
    async def decay(self):
        """Reduce strength of all signals (call periodically)."""
        now = time.time()
        to_delete = []
        for key, entry in self._local.items():
            age = now - entry["timestamp"]
            entry["strength"] *= (1 - self.decay_rate * age / 3600)
            if entry["strength"] < 0.01:
                to_delete.append(key)
        for key in to_delete:
            del self._local[key]

    # ── Helpers ───────────────────────────────────────────────────────────────
    @staticmethod
    def _make_id(key: str) -> str:
        return hashlib.md5(key.encode()).hexdigest()

    @staticmethod
    def _parse_value(raw: str) -> Any:
        try:
            return json.loads(raw)
        except Exception:
            return raw

    def stats(self) -> dict:
        return {"entries": len(self._local), "has_chroma": self._collection is not None}
