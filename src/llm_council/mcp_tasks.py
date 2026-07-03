"""MCP Tasks support layer (ADR-045 Phase 1, #404).

The MCP 2026-07-28 specification promotes the Tasks primitive (SEP-1686,
experimental since 2025-11-25) for long-running operations — purpose-built for
30–600s council deliberations that outlive client transports.

This module is the **SDK-independent core**: a durable task store with
capability-id semantics, expiry/eviction, and a kill-switch — all per the
ADR-045 council-review feedback. The actual MCP wiring is feature-detected:
the repo pins ``mcp>=1.22,<1.27`` while Tasks ships in SDK 2.x (stable v2 is
scheduled alongside the spec on 2026-07-28), so ``sdk_supports_tasks()``
returns False today and the server keeps its synchronous behaviour
byte-identical. When the stable v2 pin lands, exposure activates via
``maybe_expose_tasks`` without touching the sync path.

Security model (council feedback): a task id is a **capability** — 128 bits of
randomness returned only to the creating client; retrieval requires it, and
the store deliberately has no enumeration API.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_TTL_SECONDS = 24 * 3600  # council feedback: 24h expiry
DEFAULT_MAX_TASKS = 200  # size-capped eviction


def mcp_tasks_enabled() -> bool:
    """Kill-switch (council feedback): ``LLM_COUNCIL_MCP_TASKS=false`` disables
    task exposure even on a task-capable SDK. Default enabled-when-supported."""
    return os.getenv("LLM_COUNCIL_MCP_TASKS", "true").lower() not in (
        "false",
        "0",
        "no",
    )


def new_task_id() -> str:
    """A capability id: 128 bits of CSPRNG randomness, hex-encoded."""
    return secrets.token_hex(16)


def sdk_supports_tasks() -> bool:
    """Feature-detect Tasks support in the installed ``mcp`` SDK.

    Detection is by capability, not version string, so it lights up on
    whatever release actually carries the types — note mcp 1.26 already ships
    the EXPERIMENTAL SEP-1686 types (within our ``<1.27`` pin), while the
    stable primitive lands in SDK 2.x alongside the 2026-07-28 spec. Never
    raises.
    """
    try:
        import mcp.types as mcp_types  # type: ignore

        return hasattr(mcp_types, "Task") or hasattr(mcp_types, "CreateTaskResult")
    except Exception:
        return False


class TaskStore:
    """Durable store for long-running deliberation results.

    On-disk under ``.council/tasks/`` (same durability class as transcripts),
    one JSON file per task keyed by the capability id. Falls back to an
    in-memory dict when the directory is unusable — degrading to
    within-process semantics, never crashing (council feedback).
    """

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        max_tasks: int = DEFAULT_MAX_TASKS,
    ) -> None:
        self._ttl = ttl_seconds
        self._max_tasks = max_tasks
        self._memory: Dict[str, Dict[str, Any]] = {}
        self._dir: Optional[Path] = None
        # Reentrant: state transitions call get() internally while holding it.
        self._lock = threading.RLock()
        try:
            directory = base_dir if base_dir is not None else Path(".council") / "tasks"
            directory.mkdir(parents=True, exist_ok=True)
            probe = directory / ".probe"
            probe.write_text("")
            probe.unlink()
            self._dir = directory
        except Exception as exc:
            logger.warning(
                "task store directory unusable (%s); falling back to in-memory "
                "(tasks will not survive the process)",
                exc,
            )

    # -- internals ----------------------------------------------------------

    def _path(self, task_id: str) -> Optional[Path]:
        return (self._dir / f"{task_id}.json") if self._dir is not None else None

    def _write(self, task_id: str, task: Dict[str, Any]) -> None:
        path = self._path(task_id)
        if path is None:
            self._memory[task_id] = task
            return
        try:
            # Atomic write (round-2): tmp + os.replace so a concurrent reader
            # never sees a torn/partial JSON file.
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(json.dumps(task))
            os.replace(tmp, path)
            # A successful disk write is authoritative: drop any memory copy
            # so reads can never see a stale divergent state (no split-brain).
            self._memory.pop(task_id, None)
        except Exception as exc:
            logger.debug("task write failed (%s); using memory", exc)
            self._memory[task_id] = task

    def _expired(self, task: Dict[str, Any]) -> bool:
        # TTL is measured from created_at (round-2): frequent progress writes
        # must not immortalize a task the way an mtime-based check would.
        # A record with no parseable created_at is treated as expired.
        created = task.get("created_at")
        if not isinstance(created, (int, float)):
            return True
        return time.time() - created > self._ttl

    def _evict(self) -> None:
        # Memory entries are capped unconditionally (round-3): even with a
        # usable directory, per-write disk failures fall back to memory and
        # must not accumulate unbounded.
        while len(self._memory) > self._max_tasks:
            self._memory.pop(next(iter(self._memory)))
        if self._dir is None:
            return
        try:
            # Size-cap eviction deliberately orders by mtime (least recently
            # UPDATED goes first) — distinct from TTL, which is absolute from
            # created_at. An active long-running task should survive the size
            # cap; the TTL still bounds its total lifetime.
            files = sorted(self._dir.glob("*.json"), key=lambda f: f.stat().st_mtime)
            for f in files[: max(0, len(files) - self._max_tasks)]:
                f.unlink(missing_ok=True)
        except Exception as exc:
            logger.debug("task eviction failed (ignored): %s", exc)

    # -- public API (no enumeration by design) ------------------------------

    def create(self, kind: str) -> str:
        """Create a pending task; returns its capability id."""
        task_id = new_task_id()
        with self._lock:
            self._write(
                task_id,
                {"kind": kind, "status": "pending", "created_at": time.time()},
            )
            self._evict()
        return task_id

    def set_progress(self, task_id: str, progress: Dict[str, Any]) -> None:
        with self._lock:
            task = self.get(task_id)
            if task is None:
                return
            if task.get("status") in ("complete", "failed"):
                # Terminal states are final (round-2): late progress (e.g.
                # racing a cancellation) must not revert them to "running".
                logger.debug("set_progress() on terminal task %s ignored", task_id)
                return
            task["status"] = "running"
            task["progress"] = progress
            self._write(task_id, task)

    def complete(self, task_id: str, result: Dict[str, Any]) -> None:
        with self._lock:
            task = self.get(task_id)
            if task is None:
                # Never create/resurrect a task for an unknown or expired id —
                # capability ids must not be forgeable via state-transition calls.
                logger.debug("complete() for unknown/expired task %s ignored", task_id)
                return
            if task.get("status") in ("complete", "failed"):
                # Terminal states are first-writer-wins (round-3).
                logger.debug("complete() on terminal task %s ignored", task_id)
                return
            task["status"] = "complete"
            task["result"] = result
            self._write(task_id, task)

    def fail(self, task_id: str, error_status: str, error_detail: str) -> None:
        with self._lock:
            task = self.get(task_id)
            if task is None:
                logger.debug("fail() for unknown/expired task %s ignored", task_id)
                return
            if task.get("status") in ("complete", "failed"):
                logger.debug("fail() on terminal task %s ignored", task_id)
                return
            task["status"] = "failed"
            task["error_status"] = error_status
            task["error_detail"] = error_detail
            self._write(task_id, task)

    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve by capability id; expired tasks are reaped on access.

        Memory is checked FIRST: it is only ever populated when a disk write
        failed, so a memory entry is by construction newer than any disk copy
        (split-brain prevention — successful disk writes purge it).
        """
        with self._lock:
            if task_id in self._memory:
                task = self._memory[task_id]
                if self._expired(task):
                    self._memory.pop(task_id, None)
                    return None
                return task
            path = self._path(task_id)
            if path is None:
                return None
            try:
                if not path.exists():
                    return None
                task = json.loads(path.read_text())
                if self._expired(task):
                    path.unlink(missing_ok=True)
                    return None
                return task
            except Exception as exc:
                logger.debug("task read failed (%s)", exc)
                return None


def maybe_expose_tasks(server: Any) -> bool:
    """Activate MCP task exposure iff the SDK supports it AND the kill-switch
    allows it. Returns whether exposure happened.

    NOTE (blocked-pending-SDK): with the current pin (``mcp<1.27``) this is
    always a no-op — the Tasks primitive ships in SDK 2.x (stable targeted
    2026-07-28). When the pin is bumped, implement the wiring here: register
    task-augmented variants of ``consult_council``/``verify`` backed by a
    ``TaskStore``, leaving the synchronous tools untouched.
    """
    if not mcp_tasks_enabled():
        logger.info("MCP tasks disabled by LLM_COUNCIL_MCP_TASKS")
        return False
    if not sdk_supports_tasks():
        logger.debug("mcp SDK lacks Tasks support (pin < 2.x); sync-only mode")
        return False
    # mcp 1.26 within the current pin already advertises the EXPERIMENTAL
    # types, so this path is routine — log at info, not warning, to avoid
    # noise on every server start.
    logger.info(
        "mcp SDK reports Tasks types but exposure wiring is deferred to the "
        "stable SDK v2 pin bump (ADR-045 P1 follow-up, spec final 2026-07-28)"
    )
    return False
