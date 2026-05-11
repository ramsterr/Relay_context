from __future__ import annotations
import asyncio
import json
import logging
from dataclasses import dataclass, asdict
from typing import Any, Optional, Callable
from enum import Enum

import numpy as np

logger = logging.getLogger(__name__)

try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("redis not available - using asyncio.Queue only")


class EventType(Enum):
    MESSAGE_RECEIVED = "message_received"
    CHECKPOINT_TRIGGER = "checkpoint_trigger"
    HANDOVER_REQUESTED = "handover_requested"


@dataclass
class ContextEvent:
    event_type: EventType
    session_id: str
    payload: dict

    def to_json(self) -> str:
        return json.dumps({
            "event_type": self.event_type.value,
            "session_id": self.session_id,
            "payload": self.payload,
        })

    @classmethod
    def from_json(cls, data: str) -> "ContextEvent":
        d = json.loads(data)
        return cls(
            event_type=EventType(d["event_type"]),
            session_id=d["session_id"],
            payload=d["payload"],
        )


class AsyncContextPipeline:
    def __init__(
        self,
        extractor=None,
        registry=None,
        drift_suite=None,
        ledger=None,
        otel_instrumentor=None,
        langfuse_client=None,
        use_redis: bool = False,
        redis_url: str = "redis://localhost:6379",
        redis_queue_name: str = "context_events",
    ):
        self.extractor = extractor
        self.registry = registry
        self.drift_suite = drift_suite
        self.ledger = ledger
        self.otel = otel_instrumentor
        self.langfuse = langfuse_client
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None
        self.use_redis = use_redis
        self.redis_client = None

        if use_redis and REDIS_AVAILABLE:
            self._init_redis(redis_url, redis_queue_name)

    def _init_redis(self, redis_url: str, queue_name: str):
        try:
            self.redis_client = redis.from_url(redis_url)
            self.redis_queue_name = queue_name
            logger.info(f"Redis connected: {redis_url}")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.use_redis = False

    def emit(self, event: ContextEvent):
        try:
            self.queue.put_nowait(event)
            if self.use_redis and self.redis_client:
                self.redis_client.rpush(self.redis_queue_name, event.to_json())
        except asyncio.QueueFull:
            logger.warning(f"Pipeline queue full — dropping event {event.event_type}")

    def emit_message(self, session_id: str, content: str):
        self.emit(ContextEvent(
            event_type=EventType.MESSAGE_RECEIVED,
            session_id=session_id,
            payload={"content": content},
        ))

    def emit_checkpoint(self, session_id: str, level: str, token_count: int):
        self.emit(ContextEvent(
            event_type=EventType.CHECKPOINT_TRIGGER,
            session_id=session_id,
            payload={"level": level, "token_count": token_count},
        ))

    def emit_handover(self, session_from: str, session_to: str, atoms: list):
        self.emit(ContextEvent(
            event_type=EventType.HANDOVER_REQUESTED,
            session_id=session_from,
            payload={
                "session_from": session_from,
                "session_to": session_to,
                "atom_count": len(atoms),
            },
        ))

    async def start_worker(self):
        self._running = True
        self._worker_task = asyncio.create_task(self._run_worker())
        logger.info("Context pipeline worker started")

    async def stop_worker(self):
        self._running = False
        if self._worker_task:
            await self._worker_task
        logger.info("Context pipeline worker stopped")

    async def _run_worker(self):
        while self._running:
            try:
                if self.use_redis and self.redis_client:
                    result = self.redis_client.blpop(self.redis_queue_name, timeout=1)
                    if result:
                        _, data = result
                        event = ContextEvent.from_json(data)
                else:
                    event = await asyncio.wait_for(self.queue.get(), timeout=1.0)

                await self._process(event)

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Worker error: {e}")

    async def _process(self, event: ContextEvent):
        logger.debug(f"Processing event: {event.event_type}")

        if event.event_type == EventType.MESSAGE_RECEIVED:
            await self._process_message(event)
        elif event.event_type == EventType.CHECKPOINT_TRIGGER:
            await self._process_checkpoint(event)
        elif event.event_type == EventType.HANDOVER_REQUESTED:
            await self._process_handover(event)

    async def _process_message(self, event: ContextEvent):
        if not self.extractor or not self.registry:
            return

        content = event.payload.get("content", "")
        candidates = self.extractor.extract(content)

        for candidate in candidates:
            self.registry.insert_or_update(
                candidate,
                event.session_id,
                event.payload.get("message_index", 0),
                event.payload.get("total_messages", 1),
            )

    async def _process_checkpoint(self, event: ContextEvent):
        level = event.payload.get("level", "standard")
        token_count = event.payload.get("token_count", 0)
        logger.info(f"Processing checkpoint: {event.session_id} - {level}")

        drift_result = await self._compute_drift(event.payload, level)
        logger.info(f"Drift computation: {drift_result.get('composite', 0):.3f}")

        if self.drift_suite and drift_result.get("composite", 0) > 0.45:
            logger.warning(f"Critical drift detected - flagging for handover")

    async def _compute_drift(self, payload: dict, tier: str) -> dict:
        if not self.drift_suite or not self.registry:
            return {"kl_structural": 0.0, "jaccard": 1.0, "composite": 0.0}

        active_atoms = self.registry.get_active_atoms()
        if not active_atoms:
            return {"kl_structural": 0.0, "jaccard": 1.0, "composite": 0.0}

        model_dist = payload.get("model_belief_dist", {
            "entity": 0.3,
            "decision": 0.25,
            "constraint": 0.2,
            "task": 0.15,
            "question": 0.1,
        })

        kl_struct = self.drift_suite.kl_structural(active_atoms, model_dist)

        kl_sem = None
        if tier == "deep" and len(active_atoms) >= 3:
            embeddings = np.array([
                self.registry.embeddings[aid]
                for aid in active_atoms
                if aid in self.registry.embeddings
            ])
            if len(embeddings) >= 2:
                kl_sem = self.drift_suite.kl_semantic(embeddings, embeddings[:1])

        atom_ids = set(active_atoms.keys())
        jaccard = payload.get("jaccard_score", 1.0)

        composite = self.drift_suite.composite(kl_struct, jaccard, kl_sem)

        return {
            "kl_structural": kl_struct,
            "kl_semantic": kl_sem,
            "jaccard": jaccard,
            "composite": composite,
        }

    async def _process_handover(self, event: ContextEvent):
        session_from = event.payload.get("session_from")
        session_to = event.payload.get("session_to")
        logger.info(f"Processing handover: {session_from} → {session_to}")