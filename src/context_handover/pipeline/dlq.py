"""
Dead Letter Queue (DLQ) for handling failed events.

This module provides a Dead Letter Queue pattern for storing and managing
events that failed processing after all retry attempts, enabling later
inspection, replay, or manual intervention.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional, List, Dict
from pathlib import Path

logger = logging.getLogger(__name__)


class FailureReason(Enum):
    """Reasons for event failure."""
    MAX_RETRIES_EXCEEDED = "max_retries_exceeded"
    NON_RETRYABLE_ERROR = "non_retryable_error"
    TIMEOUT = "timeout"
    CIRCUIT_BREAKER_OPEN = "circuit_breaker_open"
    VALIDATION_ERROR = "validation_error"
    UNKNOWN = "unknown"


@dataclass
class DLQEntry:
    """
    Entry in the Dead Letter Queue.
    
    Attributes:
        event_id: Unique identifier for the failed event
        event_type: Type of the original event
        session_id: Session ID from the original event
        payload: Original event payload
        failure_reason: Why the event failed
        error_message: Detailed error message
        attempt_count: Number of retry attempts made
        first_failure_time: When the first failure occurred
        last_failure_time: When the last failure occurred
        metadata: Additional context about the failure
    """
    event_id: str
    event_type: str
    session_id: str
    payload: dict
    failure_reason: FailureReason
    error_message: str
    attempt_count: int
    first_failure_time: datetime
    last_failure_time: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "session_id": self.session_id,
            "payload": self.payload,
            "failure_reason": self.failure_reason.value,
            "error_message": self.error_message,
            "attempt_count": self.attempt_count,
            "first_failure_time": self.first_failure_time.isoformat(),
            "last_failure_time": self.last_failure_time.isoformat(),
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "DLQEntry":
        """Create from dictionary."""
        return cls(
            event_id=data["event_id"],
            event_type=data["event_type"],
            session_id=data["session_id"],
            payload=data["payload"],
            failure_reason=FailureReason(data["failure_reason"]),
            error_message=data["error_message"],
            attempt_count=data["attempt_count"],
            first_failure_time=datetime.fromisoformat(data["first_failure_time"]),
            last_failure_time=datetime.fromisoformat(data["last_failure_time"]),
            metadata=data.get("metadata", {}),
        )
    
    def age(self) -> timedelta:
        """Get age of the DLQ entry."""
        return datetime.now() - self.first_failure_time
    
    def is_stale(self, max_age_hours: int = 24) -> bool:
        """Check if entry is stale (older than max_age)."""
        return self.age().total_seconds() > max_age_hours * 3600


class DLQStorage:
    """Base class for DLQ storage backends."""
    
    async def add(self, entry: DLQEntry) -> None:
        """Add an entry to the DLQ."""
        raise NotImplementedError
    
    async def get_all(self) -> List[DLQEntry]:
        """Get all entries in the DLQ."""
        raise NotImplementedError
    
    async def remove(self, event_id: str) -> bool:
        """Remove an entry by event_id. Returns True if removed."""
        raise NotImplementedError
    
    async def clear(self) -> None:
        """Clear all entries from the DLQ."""
        raise NotImplementedError
    
    async def count(self) -> int:
        """Get count of entries in the DLQ."""
        raise NotImplementedError


class InMemoryDLQStorage(DLQStorage):
    """In-memory DLQ storage (default, for development/testing)."""
    
    def __init__(self, max_size: int = 1000):
        self._queue: Dict[str, DLQEntry] = {}
        self._max_size = max_size
        self._lock = asyncio.Lock()
    
    async def add(self, entry: DLQEntry) -> None:
        async with self._lock:
            # Remove oldest if at capacity
            if len(self._queue) >= self._max_size:
                oldest_id = min(
                    self._queue.keys(),
                    key=lambda k: self._queue[k].first_failure_time
                )
                await self.remove(oldest_id)
            
            self._queue[entry.event_id] = entry
            logger.warning(f"Added event {entry.event_id} to DLQ")
    
    async def get_all(self) -> List[DLQEntry]:
        async with self._lock:
            return list(self._queue.values())
    
    async def remove(self, event_id: str) -> bool:
        async with self._lock:
            if event_id in self._queue:
                del self._queue[event_id]
                logger.info(f"Removed event {event_id} from DLQ")
                return True
            return False
    
    async def clear(self) -> None:
        async with self._lock:
            self._queue.clear()
            logger.info("Cleared DLQ")
    
    async def count(self) -> int:
        async with self._lock:
            return len(self._queue)


class FileDLQStorage(DLQStorage):
    """File-based DLQ storage for persistence across restarts."""
    
    def __init__(self, file_path: str | Path, max_size: int = 1000):
        self.file_path = Path(file_path)
        self._max_size = max_size
        self._lock = asyncio.Lock()
        self._ensure_file_exists()
    
    def _ensure_file_exists(self):
        """Ensure the DLQ file exists."""
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            self.file_path.write_text("[]")
    
    def _read_entries(self) -> List[DLQEntry]:
        """Read entries from file."""
        try:
            data = json.loads(self.file_path.read_text())
            return [DLQEntry.from_dict(item) for item in data]
        except (json.JSONDecodeError, FileNotFoundError):
            return []
    
    def _write_entries(self, entries: List[DLQEntry]) -> None:
        """Write entries to file."""
        data = [entry.to_dict() for entry in entries]
        self.file_path.write_text(json.dumps(data, indent=2))
    
    async def add(self, entry: DLQEntry) -> None:
        async with self._lock:
            entries = self._read_entries()
            
            # Remove oldest if at capacity
            if len(entries) >= self._max_size:
                entries.sort(key=lambda e: e.first_failure_time)
                entries.pop(0)
            
            entries.append(entry)
            self._write_entries(entries)
            logger.warning(f"Added event {entry.event_id} to DLQ")
    
    async def get_all(self) -> List[DLQEntry]:
        async with self._lock:
            return self._read_entries()
    
    async def remove(self, event_id: str) -> bool:
        async with self._lock:
            entries = self._read_entries()
            original_count = len(entries)
            entries = [e for e in entries if e.event_id != event_id]
            
            if len(entries) < original_count:
                self._write_entries(entries)
                logger.info(f"Removed event {event_id} from DLQ")
                return True
            return False
    
    async def clear(self) -> None:
        async with self._lock:
            self._write_entries([])
            logger.info("Cleared DLQ")
    
    async def count(self) -> int:
        async with self._lock:
            return len(self._read_entries())


class DeadLetterQueue:
    """
    Dead Letter Queue manager for failed events.
    
    Provides functionality to:
    - Store failed events with full context
    - Inspect and query failed events
    - Replay failed events
    - Automatic cleanup of stale entries
    - Metrics and monitoring
    
    Example:
        dlq = DeadLetterQueue(storage=InMemoryDLQStorage(max_size=500))
        
        # Add failed event
        await dlq.record_failure(
            event=event,
            reason=FailureReason.MAX_RETRIES_EXCEEDED,
            error="Connection timeout after 3 retries",
            attempts=3,
        )
        
        # Inspect failures
        entries = await dlq.get_all()
        print(f"DLQ size: {len(entries)}")
        
        # Retry specific event
        await dlq.replay(event_id, handler_func)
    """
    
    def __init__(
        self,
        storage: Optional[DLQStorage] = None,
        auto_cleanup_interval_hours: int = 6,
        max_entry_age_hours: int = 72,
    ):
        self.storage = storage or InMemoryDLQStorage()
        self.auto_cleanup_interval_hours = auto_cleanup_interval_hours
        self.max_entry_age_hours = max_entry_age_hours
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start(self) -> None:
        """Start the DLQ background tasks."""
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("Dead Letter Queue started")
    
    async def stop(self) -> None:
        """Stop the DLQ background tasks."""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("Dead Letter Queue stopped")
    
    async def record_failure(
        self,
        event: Any,
        reason: FailureReason,
        error: str,
        attempts: int = 1,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Record a failed event in the DLQ.
        
        Args:
            event: The failed event object (must have event_id, event_type, session_id, payload)
            reason: Why the event failed
            error: Detailed error message
            attempts: Number of retry attempts made
            metadata: Additional context about the failure
        """
        now = datetime.now()
        
        entry = DLQEntry(
            event_id=getattr(event, "event_id", f"unknown_{now.timestamp()}"),
            event_type=getattr(event, "event_type", "unknown"),
            session_id=getattr(event, "session_id", "unknown"),
            payload=getattr(event, "payload", {}),
            failure_reason=reason,
            error_message=error,
            attempt_count=attempts,
            first_failure_time=now,
            last_failure_time=now,
            metadata=metadata or {},
        )
        
        await self.storage.add(entry)
    
    async def get_all(self) -> List[DLQEntry]:
        """Get all entries in the DLQ."""
        return await self.storage.get_all()
    
    async def get_by_session(self, session_id: str) -> List[DLQEntry]:
        """Get all failed events for a specific session."""
        entries = await self.storage.get_all()
        return [e for e in entries if e.session_id == session_id]
    
    async def get_by_reason(self, reason: FailureReason) -> List[DLQEntry]:
        """Get all failed events with a specific failure reason."""
        entries = await self.storage.get_all()
        return [e for e in entries if e.failure_reason == reason]
    
    async def remove(self, event_id: str) -> bool:
        """Remove a specific entry from the DLQ."""
        return await self.storage.remove(event_id)
    
    async def clear(self) -> None:
        """Clear all entries from the DLQ."""
        await self.storage.clear()
    
    async def count(self) -> int:
        """Get the number of entries in the DLQ."""
        return await self.storage.count()
    
    async def replay(
        self,
        event_id: str,
        handler: callable,
        remove_on_success: bool = True,
    ) -> bool:
        """
        Replay a failed event with the given handler.
        
        Args:
            event_id: ID of the event to replay
            handler: Async function to process the event
            remove_on_success: Whether to remove from DLQ on success
        
        Returns:
            True if replay succeeded, False otherwise
        """
        entries = await self.storage.get_all()
        entry = next((e for e in entries if e.event_id == event_id), None)
        
        if not entry:
            logger.error(f"Event {event_id} not found in DLQ")
            return False
        
        logger.info(f"Replaying event {event_id} (type: {entry.event_type})")
        
        try:
            # Reconstruct event object (simplified - may need customization)
            from .pipeline import ContextEvent, EventType
            
            event = ContextEvent(
                event_type=EventType(entry.event_type),
                session_id=entry.session_id,
                payload=entry.payload,
            )
            
            await handler(event)
            
            if remove_on_success:
                await self.remove(event_id)
                logger.info(f"Event {event_id} replayed successfully and removed from DLQ")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to replay event {event_id}: {e}")
            
            # Update last failure time
            entry.last_failure_time = datetime.now()
            entry.metadata["last_replay_error"] = str(e)
            await self.storage.add(entry)  # Update entry
            
            return False
    
    async def replay_all(
        self,
        handler: callable,
        batch_size: int = 10,
    ) -> Dict[str, Any]:
        """
        Replay all failed events.
        
        Args:
            handler: Async function to process events
            batch_size: Number of events to process in parallel
        
        Returns:
            Dictionary with success/failure counts
        """
        entries = await self.storage.get_all()
        total = len(entries)
        successes = 0
        failures = 0
        
        logger.info(f"Starting DLQ replay of {total} events")
        
        for i in range(0, total, batch_size):
            batch = entries[i:i + batch_size]
            tasks = [
                self.replay(entry.event_id, handler, remove_on_success=True)
                for entry in batch
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if result is True:
                    successes += 1
                else:
                    failures += 1
            
            logger.info(f"DLQ replay progress: {successes + failures}/{total}")
        
        return {
            "total": total,
            "successes": successes,
            "failures": failures,
        }
    
    async def cleanup_stale(self, max_age_hours: Optional[int] = None) -> int:
        """
        Remove stale entries from the DLQ.
        
        Args:
            max_age_hours: Maximum age in hours (uses instance default if not provided)
        
        Returns:
            Number of entries removed
        """
        max_age = max_age_hours or self.max_entry_age_hours
        entries = await self.storage.get_all()
        
        removed_count = 0
        for entry in entries:
            if entry.is_stale(max_age):
                await self.storage.remove(entry.event_id)
                removed_count += 1
        
        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} stale DLQ entries")
        
        return removed_count
    
    async def _cleanup_loop(self) -> None:
        """Background task to periodically clean up stale entries."""
        while self._running:
            try:
                await asyncio.sleep(self.auto_cleanup_interval_hours * 3600)
                if self._running:
                    await self.cleanup_stale()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"DLQ cleanup error: {e}")
    
    async def get_metrics(self) -> Dict[str, Any]:
        """Get DLQ metrics for monitoring."""
        entries = await self.storage.get_all()
        
        if not entries:
            return {
                "total_count": 0,
                "by_reason": {},
                "avg_age_hours": 0,
                "oldest_entry_age_hours": 0,
            }
        
        # Count by reason
        by_reason: Dict[str, int] = {}
        for entry in entries:
            reason_key = entry.failure_reason.value
            by_reason[reason_key] = by_reason.get(reason_key, 0) + 1
        
        # Calculate ages
        ages_hours = [e.age().total_seconds() / 3600 for e in entries]
        
        return {
            "total_count": len(entries),
            "by_reason": by_reason,
            "avg_age_hours": sum(ages_hours) / len(ages_hours),
            "oldest_entry_age_hours": max(ages_hours),
            "newest_entry_age_hours": min(ages_hours),
        }
