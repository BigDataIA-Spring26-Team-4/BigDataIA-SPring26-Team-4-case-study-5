"""
Bonus Extension: Mem0 Semantic Memory (+5 pts).

Gives agents persistent memory of past DD conversations.
Stores key findings, decisions, and context across sessions
so agents can reference prior assessments.

Uses mem0ai for semantic storage and retrieval.
Falls back to in-memory dict if mem0ai is not installed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from typing import List, Dict, Optional
from datetime import datetime
from dataclasses import dataclass, field
import json
import structlog

logger = structlog.get_logger()


@dataclass
class MemoryEntry:
    """Single memory entry from a past DD conversation."""
    memory_id: str
    company_id: str
    content: str
    memory_type: str        # "finding", "decision", "context", "risk"
    agent_name: str
    created_at: datetime
    metadata: Dict = field(default_factory=dict)


class SemanticMemoryService:
    """
    Semantic memory for DD agents.

    Stores and retrieves past findings, decisions, and context.
    Uses mem0ai when available, falls back to keyword search
    over an in-memory store.
    """

    def __init__(self, user_id: str = "pe_analyst"):
        self.user_id = user_id
        self._mem0_client = None
        self._fallback_store: List[MemoryEntry] = []

        # Try to initialize mem0
        try:
            from mem0 import Memory
            self._mem0_client = Memory()
            logger.info("mem0_initialized", user_id=user_id)
        except ImportError:
            logger.info("mem0_not_available_using_fallback")
        except Exception as e:
            logger.warning("mem0_init_failed", error=str(e))

    async def store_memory(
        self,
        company_id: str,
        content: str,
        memory_type: str = "finding",
        agent_name: str = "system",
        metadata: Optional[Dict] = None,
    ) -> str:
        """
        Store a memory from a DD conversation.

        Args:
            company_id: Company ticker this memory relates to
            content: The finding/decision/context text
            memory_type: One of: finding, decision, context, risk
            agent_name: Which agent produced this memory
            metadata: Additional key-value pairs

        Returns:
            Memory ID string
        """
        memory_id = f"mem_{company_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        meta = metadata or {}
        meta.update({
            "company_id": company_id,
            "memory_type": memory_type,
            "agent_name": agent_name,
        })

        if self._mem0_client:
            try:
                result = self._mem0_client.add(
                    content,
                    user_id=self.user_id,
                    metadata=meta,
                )
                memory_id = result.get("id", memory_id) if isinstance(result, dict) else memory_id
            except Exception as e:
                logger.warning("mem0_store_failed", error=str(e))

        # Always store in fallback too
        entry = MemoryEntry(
            memory_id=memory_id,
            company_id=company_id.upper(),
            content=content,
            memory_type=memory_type,
            agent_name=agent_name,
            created_at=datetime.utcnow(),
            metadata=meta,
        )
        self._fallback_store.append(entry)

        logger.info(
            "memory_stored",
            memory_id=memory_id,
            company_id=company_id,
            memory_type=memory_type,
        )
        return memory_id

    async def recall(
        self,
        query: str,
        company_id: Optional[str] = None,
        limit: int = 5,
    ) -> List[MemoryEntry]:
        """
        Recall relevant memories for a query.

        Uses semantic search (mem0) or keyword fallback.
        """
        # Try mem0 semantic search
        if self._mem0_client:
            try:
                results = self._mem0_client.search(
                    query, user_id=self.user_id, limit=limit,
                )
                # Convert mem0 results to MemoryEntry
                entries = []
                for r in results:
                    meta = r.get("metadata", {})
                    entries.append(MemoryEntry(
                        memory_id=r.get("id", ""),
                        company_id=meta.get("company_id", ""),
                        content=r.get("memory", r.get("text", "")),
                        memory_type=meta.get("memory_type", "finding"),
                        agent_name=meta.get("agent_name", "unknown"),
                        created_at=datetime.utcnow(),
                        metadata=meta,
                    ))
                if company_id:
                    entries = [e for e in entries if e.company_id == company_id.upper()]
                return entries[:limit]
            except Exception as e:
                logger.warning("mem0_recall_failed", error=str(e))

        # Fallback: keyword search over in-memory store
        query_lower = query.lower()
        candidates = self._fallback_store

        if company_id:
            candidates = [
                m for m in candidates if m.company_id == company_id.upper()
            ]

        # Simple keyword relevance scoring
        scored = []
        for entry in candidates:
            score = sum(
                1 for word in query_lower.split()
                if word in entry.content.lower()
            )
            if score > 0:
                scored.append((score, entry))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:limit]]

    async def get_company_history(
        self, company_id: str
    ) -> List[MemoryEntry]:
        """Get all memories for a specific company."""
        ticker = company_id.upper()
        return [
            m for m in self._fallback_store
            if m.company_id == ticker
        ]

    async def clear(self, company_id: Optional[str] = None) -> int:
        """Clear memories, optionally for a specific company."""
        if company_id:
            ticker = company_id.upper()
            before = len(self._fallback_store)
            self._fallback_store = [
                m for m in self._fallback_store
                if m.company_id != ticker
            ]
            cleared = before - len(self._fallback_store)
        else:
            cleared = len(self._fallback_store)
            self._fallback_store.clear()

        logger.info("memory_cleared", company_id=company_id, count=cleared)
        return cleared


# Module-level singleton
semantic_memory = SemanticMemoryService()
