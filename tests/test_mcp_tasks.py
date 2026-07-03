"""ADR-045 P1: MCP task store + capability ids + kill-switch (#404)."""

import json
import time
from pathlib import Path

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
        # Backdate the file well past the TTL.
        f = next(tmp_path.glob("*.json"))
        old = time.time() - 10
        import os
        os.utime(f, (old, old))
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
