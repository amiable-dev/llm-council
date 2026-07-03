"""ADR-045 P3: two-instance stateless smoke (#406).

Simulates a load-balanced deployment: two independent server instances
(separate TaskStore objects, separate processes) sharing only the durable
store directory. Correctness must not depend on which instance handles a
given request.
"""

import json
import subprocess
import sys
from pathlib import Path

from llm_council.mcp_tasks import TaskStore


class TestTwoInstanceTaskStore:
    def test_task_created_on_a_visible_on_b(self, tmp_path):
        a = TaskStore(base_dir=tmp_path)
        b = TaskStore(base_dir=tmp_path)
        tid = a.create(kind="consult_council")
        task = b.get(tid)
        assert task is not None and task["status"] == "pending"

    def test_lifecycle_split_across_instances(self, tmp_path):
        # create on A, progress on B, complete on A, read on B — the exact
        # LB-routing pattern Tasks-backed deliberation must survive.
        a = TaskStore(base_dir=tmp_path)
        b = TaskStore(base_dir=tmp_path)
        tid = a.create(kind="verify")
        b.set_progress(tid, {"stage": 2})
        a.complete(tid, {"verdict": "pass"})
        task = b.get(tid)
        assert task["status"] == "complete"
        assert task["result"]["verdict"] == "pass"

    def test_terminal_state_enforced_across_instances(self, tmp_path):
        a = TaskStore(base_dir=tmp_path)
        b = TaskStore(base_dir=tmp_path)
        tid = a.create(kind="k")
        a.complete(tid, {"ok": 1})
        b.fail(tid, "late", "must not overwrite")  # racing instance
        # BOTH instances must agree on the terminal state — asserting only
        # the writer would miss a split-brain (#426 council review).
        assert a.get(tid)["status"] == "complete"
        assert b.get(tid)["status"] == "complete"


class TestTwoProcessSmoke:
    def test_separate_processes_share_durable_tasks(self, tmp_path):
        # A genuinely separate OS process (instance B) completes a task
        # created by this process (instance A).
        a = TaskStore(base_dir=tmp_path)
        tid = a.create(kind="consult_council")
        script = (
            "import sys, json\n"
            "from llm_council.mcp_tasks import TaskStore\n"
            "from pathlib import Path\n"
            "store = TaskStore(base_dir=Path(sys.argv[1]))\n"
            "store.complete(sys.argv[2], {'synthesis': 'from-instance-b'})\n"
        )
        subprocess.run(
            [sys.executable, "-c", script, str(tmp_path), tid],
            check=True,
            cwd=Path(__file__).resolve().parent.parent,
        )
        task = a.get(tid)
        assert task["status"] == "complete"
        assert task["result"]["synthesis"] == "from-instance-b"

    def test_concurrent_instance_writes_never_torn(self, tmp_path):
        # Two processes hammering the same store directory: every surviving
        # task file must parse as valid JSON (atomic-write guarantee).
        script = (
            "import sys\n"
            "from llm_council.mcp_tasks import TaskStore\n"
            "from pathlib import Path\n"
            "store = TaskStore(base_dir=Path(sys.argv[1]))\n"
            "for i in range(25):\n"
            "    tid = store.create(kind=f'k{sys.argv[2]}-{i}')\n"
            "    store.complete(tid, {'i': i, 'proc': sys.argv[2]})\n"
        )
        procs = [
            subprocess.Popen(
                [sys.executable, "-c", script, str(tmp_path), tag],
                cwd=Path(__file__).resolve().parent.parent,
            )
            for tag in ("a", "b")
        ]
        for p in procs:
            assert p.wait() == 0
        files = list(tmp_path.glob("*.json"))
        assert files, "no task files written"
        for f in files:
            json.loads(f.read_text())  # must never be torn/partial
