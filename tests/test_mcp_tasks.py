"""ADR-045 P1: MCP task store + capability ids + kill-switch (#404)."""

import json
import time
from pathlib import Path
from unittest import mock

import pytest

from llm_council.mcp_tasks import (
    TaskStore,
    mcp_tasks_enabled,
    new_task_id,
    sdk_supports_tasks,
)


class TestKillSwitch:
    def test_enabled_by_default(self, monkeypatch):
        monkeypatch.delenv("LLM_COUNCIL_MCP_TASKS", raising=False)
        assert mcp_tasks_enabled() is True

    def test_kill_switch(self, monkeypatch):
        monkeypatch.setenv("LLM_COUNCIL_MCP_TASKS", "false")
        assert mcp_tasks_enabled() is False


class TestCapabilityIds:
    def test_128_bit_hex(self):
        tid = new_task_id()
        assert len(tid) == 32  # 128 bits as hex
        int(tid, 16)  # parses as hex

    def test_unique(self):
        assert len({new_task_id() for _ in range(100)}) == 100


class TestTaskStore:
    def test_round_trip(self, tmp_path):
        store = TaskStore(base_dir=tmp_path)
        tid = store.create(kind="consult_council")
        store.set_progress(tid, {"stage": 1, "message": "collecting"})
        store.complete(tid, {"synthesis": "answer", "usage": {"total_tokens": 5}})
        task = store.get(tid)
        assert task["status"] == "complete"
        assert task["result"]["synthesis"] == "answer"
        assert task["kind"] == "consult_council"

    def test_get_unknown_id_returns_none(self, tmp_path):
        store = TaskStore(base_dir=tmp_path)
        assert store.get("0" * 32) is None

    def test_no_enumeration_api(self, tmp_path):
        # Capability semantics: retrieval requires the id; no list method.
        store = TaskStore(base_dir=tmp_path)
        assert not hasattr(store, "list")
        assert not hasattr(store, "list_tasks")

    def test_expiry(self, tmp_path):
        store = TaskStore(base_dir=tmp_path, ttl_seconds=1)
        tid = store.create(kind="verify")
        store.complete(tid, {"ok": True})
        # Backdate created_at well past the TTL (round-2: TTL is measured
        # from created_at, not file mtime).
        f = next(tmp_path.glob("*.json"))
        data = json.loads(f.read_text())
        data["created_at"] = time.time() - 10
        f.write_text(json.dumps(data))
        assert store.get(tid) is None  # expired
        assert not f.exists()  # reaped on access

    def test_eviction_caps_task_count(self, tmp_path):
        store = TaskStore(base_dir=tmp_path, max_tasks=3)
        ids = [store.create(kind="k") for _ in range(5)]
        files = list(tmp_path.glob("*.json"))
        assert len(files) <= 3
        # Newest survive.
        assert store.get(ids[-1]) is not None

    def test_fail_marks_failed(self, tmp_path):
        store = TaskStore(base_dir=tmp_path)
        tid = store.create(kind="verify")
        store.fail(tid, "auth_error", "Payment required (402)")
        task = store.get(tid)
        assert task["status"] == "failed"
        assert task["error_status"] == "auth_error"

    def test_unwritable_dir_falls_back_to_memory(self, tmp_path, monkeypatch):
        target = tmp_path / "blocked"
        target.write_text("not a dir")  # a FILE where the dir should be
        store = TaskStore(base_dir=target)
        tid = store.create(kind="k")  # must not raise
        store.complete(tid, {"ok": 1})
        assert store.get(tid)["status"] == "complete"


class TestSdkDetection:
    def test_detection_returns_bool_and_never_raises(self):
        assert isinstance(sdk_supports_tasks(), bool)

    def test_current_pin_lacks_tasks(self):
        # Repo pins mcp <1.27; the Tasks primitive ships in SDK 2.x. If this
        # starts returning True after the stable-v2 bump, wire the exposure
        # (see mcp_tasks.maybe_expose_tasks note).
        assert sdk_supports_tasks() is False


class TestCouncilRound1Findings:
    def test_complete_on_unknown_id_is_noop_no_phantom(self, tmp_path):
        # #423 round-1: complete()/fail() must NOT create/resurrect a task for
        # an unknown or expired id (the capability id would become forgeable).
        store = TaskStore(base_dir=tmp_path)
        ghost = "f" * 32
        store.complete(ghost, {"ok": 1})
        assert store.get(ghost) is None
        store.fail(ghost, "error", "detail")
        assert store.get(ghost) is None
        assert list(tmp_path.glob("*.json")) == []

    def test_expired_task_cannot_be_resurrected(self, tmp_path):
        store = TaskStore(base_dir=tmp_path, ttl_seconds=1)
        tid = store.create(kind="k")
        f = next(tmp_path.glob("*.json"))
        data = json.loads(f.read_text())
        data["created_at"] = time.time() - 10
        f.write_text(json.dumps(data))
        store.complete(tid, {"late": True})  # arrives after expiry
        assert store.get(tid) is None

    def test_no_split_brain_memory_wins_after_disk_failure(self, tmp_path, monkeypatch):
        # #423 round-1: if a mid-lifecycle disk write fails and falls back to
        # memory, subsequent reads must see the NEWER memory state, not the
        # stale disk copy.
        store = TaskStore(base_dir=tmp_path)
        tid = store.create(kind="k")  # lands on disk as 'pending'
        original_write_text = Path.write_text

        def failing_write(self, *a, **kw):
            if self.parent == tmp_path and self.suffix == ".json":
                raise OSError("disk full")
            return original_write_text(self, *a, **kw)

        monkeypatch.setattr(Path, "write_text", failing_write)
        store.complete(tid, {"ok": 1})  # disk write fails -> memory fallback
        monkeypatch.undo()
        task = store.get(tid)
        assert task["status"] == "complete"  # memory (newer) wins over stale disk


class TestCouncilRound2Findings:
    def test_memory_tasks_expire_too(self, tmp_path):
        target = tmp_path / "blocked"
        target.write_text("not a dir")  # force memory mode
        store = TaskStore(base_dir=target, ttl_seconds=1)
        tid = store.create(kind="k")
        # Backdate the in-memory created_at past the TTL.
        store._memory[tid]["created_at"] = time.time() - 10
        assert store.get(tid) is None

    def test_ttl_measured_from_created_at_not_mtime(self, tmp_path):
        # Frequent progress writes must not immortalize a task.
        store = TaskStore(base_dir=tmp_path, ttl_seconds=1)
        tid = store.create(kind="k")
        f = next(tmp_path.glob("*.json"))
        data = json.loads(f.read_text())
        data["created_at"] = time.time() - 10  # created long ago
        f.write_text(json.dumps(data))  # fresh mtime, stale created_at
        assert store.get(tid) is None

    def test_progress_cannot_revert_completed_task(self, tmp_path):
        store = TaskStore(base_dir=tmp_path)
        tid = store.create(kind="k")
        store.complete(tid, {"ok": 1})
        store.set_progress(tid, {"stage": 2})  # late progress after completion
        assert store.get(tid)["status"] == "complete"


class TestCouncilRound3Findings:
    def test_terminal_states_are_first_writer_wins(self, tmp_path):
        store = TaskStore(base_dir=tmp_path)
        tid = store.create(kind="k")
        store.fail(tid, "timeout", "deadline exceeded")
        store.complete(tid, {"late": True})  # must not overwrite failed
        assert store.get(tid)["status"] == "failed"
        tid2 = store.create(kind="k")
        store.complete(tid2, {"ok": 1})
        store.fail(tid2, "late", "ignored")  # must not overwrite complete
        assert store.get(tid2)["status"] == "complete"

    def test_memory_fallback_entries_are_capped_even_with_dir_set(self, tmp_path):
        # Per-write disk failures fall back to memory while _dir is set;
        # those entries must still respect max_tasks.
        store = TaskStore(base_dir=tmp_path, max_tasks=3)
        real_write_text = Path.write_text

        def failing_write(self, *a, **kw):
            if self.parent == tmp_path and self.name.endswith(".tmp"):
                raise OSError("disk full")
            return real_write_text(self, *a, **kw)

        with mock.patch.object(Path, "write_text", failing_write):
            for _ in range(6):
                store.create(kind="k")
        assert len(store._memory) <= 3
