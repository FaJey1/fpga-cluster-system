import json
import math
import time
import asyncio
import logging
from typing import List, Dict, Any, Optional

import httpx

from src.entities.project import Project
from src.entities.task import Task, TaskStatus
from src.entities.fpga_device import FPGADevice
from src.ports.cluster_repository import ClusterRepository
from src.ports.queue_repository import QueueRepository

logger = logging.getLogger(__name__)


class MasterUseCases:
    def __init__(
        self,
        node_id: str,
        cluster_repo: ClusterRepository,
        queue_repo: QueueRepository,
        lease_ttl: int = 10,
        token_uc=None,
    ):
        self.node_id = node_id
        self.cluster_repo = cluster_repo
        self.queue_repo = queue_repo
        self.lease_ttl = lease_ttl
        self.token_uc = token_uc
        self._lease = None

    # ── Cluster membership ──────────────────────────────────────────────────

    async def join_cluster(self, info: Dict):
        lease_scope = self.cluster_repo._client.grant_lease_scope(self.lease_ttl)
        self._lease = await lease_scope.__aenter__()
        await self.cluster_repo._client.put(
            f"/fpga/masters/{self.node_id}", json.dumps(info), lease=self._lease.id
        )
        return self._lease.id

    async def get_masters(self) -> List[Dict]:
        return await self.cluster_repo.get_masters()

    async def get_workers(self) -> List[Dict]:
        return await self.cluster_repo.get_workers()

    @staticmethod
    def _quorum_health(n: int) -> Dict:
        """
        Returns quorum validity for given master count.

        Valid configurations: 1 (standalone), 3, 5 (HA with fault tolerance).
        Any even number is invalid — split-brain risk, cluster enters WARNING.
        """
        if n == 0:
            return {"quorum_ok": False, "quorum_state": "no_masters",
                    "fault_tolerance": 0, "warning": "No masters registered"}
        if n % 2 == 0:
            return {"quorum_ok": False, "quorum_state": "warning",
                    "fault_tolerance": 0,
                    "warning": (
                        f"Even number of masters ({n}) — split-brain risk. "
                        "Use 1 (standalone), 3, or 5 masters for a valid quorum."
                    )}
        if n == 1:
            return {"quorum_ok": True, "quorum_state": "standalone",
                    "fault_tolerance": 0,
                    "warning": "Single master — no fault tolerance"}
        # n is odd and > 1 (3, 5, 7 …)
        fault_tolerance = (n - 1) // 2
        return {"quorum_ok": True, "quorum_state": "ha",
                "fault_tolerance": fault_tolerance, "warning": None}

    async def quorum_status(self) -> Dict:
        masters = await self.get_masters()
        n = len(masters)
        health = self._quorum_health(n)
        return {"master_count": n, "masters": masters, **health}

    async def is_quorum_master(self) -> Dict:
        masters = await self.get_masters()
        n = len(masters)
        health = self._quorum_health(n)

        if n == 0:
            return {"is_leader": False, "node_id": self.node_id, **health}

        # Leader election: node with lexicographically smallest node_id wins
        node_ids = sorted(m.get("node_id", "") for m in masters if m.get("node_id"))
        is_leader = bool(node_ids and node_ids[0] == self.node_id)

        # Backward-compat field kept alongside new name
        return {"is_master": is_leader, "is_leader": is_leader,
                "node_id": self.node_id, **health}

    # ── Worker registration ─────────────────────────────────────────────────

    async def register_worker(self, worker_id: str, info: Dict) -> Dict:
        await self.cluster_repo.register_worker(worker_id, info, ttl=30)
        logger.info("Worker %s registered", worker_id)
        return {"status": "ok", "worker_id": worker_id}

    async def update_worker_heartbeat(self, worker_id: str, status: Dict) -> Dict:
        # Merge with existing record to preserve tags, node_ip, max_capacity etc.
        existing: Dict = {}
        try:
            val, _ = await self.cluster_repo._client.get(f"/fpga/workers/{worker_id}")
            if val:
                existing = json.loads(val)
        except Exception:
            pass
        info = {**existing, "worker_id": worker_id, **status, "last_heartbeat": int(time.time())}
        await self.cluster_repo.register_worker(worker_id, info, ttl=30)
        return {"status": "ok"}

    # ── FPGA management ─────────────────────────────────────────────────────

    async def register_fpga(self, fpga: FPGADevice) -> Dict:
        key = f"/cluster/fpga/{fpga.fpga_id}"
        await self.cluster_repo._client.put(key, json.dumps(fpga.to_dict()))
        logger.info("FPGA %s registered on worker %s", fpga.fpga_id, fpga.worker_id)
        return fpga.to_dict()

    async def get_fpgas(self) -> List[Dict]:
        kvs = await self.cluster_repo._client.range("/cluster/fpga/")
        res = []
        for _, v in kvs:
            try:
                res.append(json.loads(v))
            except Exception:
                pass
        return res

    async def get_fpga(self, fpga_id: str) -> Optional[Dict]:
        val, _ = await self.cluster_repo._client.get(f"/cluster/fpga/{fpga_id}")
        if val is None:
            return None
        return json.loads(val)

    async def update_fpga_status(self, fpga_id: str, status: str) -> Dict:
        val, _ = await self.cluster_repo._client.get(f"/cluster/fpga/{fpga_id}")
        if val is None:
            return {"status": "not_found"}
        fpga_data = json.loads(val)
        fpga_data["status"] = status
        await self.cluster_repo._client.put(f"/cluster/fpga/{fpga_id}", json.dumps(fpga_data))
        logger.info("FPGA %s status → %s", fpga_id, status)
        return {"status": "ok", "fpga_id": fpga_id, "new_status": status}

    # ── Task management ─────────────────────────────────────────────────────

    async def submit_task(self, task: Task) -> Dict:
        key = f"/cluster/tasks/{task.task_id}"
        await self.cluster_repo._client.put(key, json.dumps(task.to_dict()))
        await self.queue_repo.push_task(task)
        logger.info("Task %s submitted for tag %s", task.task_id, task.worker_tag)
        return task.to_dict()

    async def get_task(self, task_id: str) -> Optional[Dict]:
        val, _ = await self.cluster_repo._client.get(f"/cluster/tasks/{task_id}")
        if val is None:
            return None
        return json.loads(val)

    async def complete_task(self, task_id: str, result: Dict) -> Dict:
        val, _ = await self.cluster_repo._client.get(f"/cluster/tasks/{task_id}")
        if val is None:
            return {"status": "not_found"}
        task_data = json.loads(val)
        status = TaskStatus.COMPLETED if result.get("status") == "success" else TaskStatus.FAILED
        task_data.update({
            "status": status.value,
            "completed_at": int(time.time()),
            "result": result,
        })
        await self.cluster_repo._client.put(
            f"/cluster/tasks/{task_id}", json.dumps(task_data)
        )
        return {"status": "ok", "task_id": task_id}

    async def list_tasks(self) -> List[Dict]:
        kvs = await self.cluster_repo._client.range("/cluster/tasks/")
        res = []
        for _, v in kvs:
            try:
                res.append(json.loads(v))
            except Exception:
                pass
        return res

    async def delete_worker(self, worker_id: str) -> Dict:
        await self.cluster_repo._client.delete(f"/fpga/workers/{worker_id}")
        logger.info("Worker %s deleted", worker_id)
        return {"status": "ok", "worker_id": worker_id}

    async def delete_fpga(self, fpga_id: str) -> Dict:
        await self.cluster_repo._client.delete(f"/cluster/fpga/{fpga_id}")
        logger.info("FPGA %s deleted", fpga_id)
        return {"status": "ok", "fpga_id": fpga_id}

    async def clear_tasks(self) -> Dict:
        await self.cluster_repo._client.delete_prefix("/cluster/tasks/")
        await self.queue_repo.clear_tasks()
        logger.info("All task history cleared")
        return {"status": "ok", "cleared": True}

    # ── Legacy project queue (kept for backward compat) ────────────────────

    async def list_queue(self):
        return await self.queue_repo.list_queue()

    async def put_project(self, project: Project):
        await self.queue_repo.push_project(project)

    async def remove_project(self, project_id: str):
        return await self.queue_repo.remove_project(project_id)

    async def pop_project(self):
        return await self.queue_repo.pop_project()

    # ── FPGA matching ───────────────────────────────────────────────────────

    @staticmethod
    def _match_fpga(task_data: Dict, all_fpgas: List[Dict]) -> Optional[Dict]:
        """
        Return the best idle FPGA for the task, or None.

        Routing rules:
        - Test FPGA  (fpga_id starts with "fpga-test-"): accepts any is_test=True task.
        - Dev FPGA   (fpga_id starts with "dev_"):  must match fpga_tag exactly.
        - Prod FPGA  (fpga_id starts with "prod_"): must match fpga_tag exactly.
        - board_name check: if both task.project_board and fpga.board_name are non-empty,
          they must be equal.
        - FPGA status must be "idle".
        """
        fpga_tag     = task_data.get("fpga_tag") or ""
        is_test      = bool(task_data.get("is_test", False))
        project_board = task_data.get("project_board", "")

        candidates: List[Dict] = []
        for fpga in all_fpgas:
            if fpga.get("status", "idle") not in ("idle", "running"):
                continue
            fid = fpga.get("fpga_id", "")

            if fid.startswith("fpga-test-"):
                if not is_test:
                    continue  # test FPGAs only handle test tasks
                # If task specifies a specific fpga-test-XXX, respect it
                if fpga_tag and fpga_tag.startswith("fpga-test-") and fpga_tag != fid:
                    continue
            elif fid.startswith("dev_") or fid.startswith("prod_"):
                # Must exactly match the requested fpga_tag
                if fpga_tag != fid:
                    continue
            else:
                # Custom FPGA: only accept if fpga_tag matches exactly
                if fpga_tag and fpga_tag != fid:
                    continue

            # Board compatibility check
            fpga_board = fpga.get("board_name", "")
            if project_board and fpga_board and project_board != fpga_board:
                continue

            candidates.append(fpga)

        if not candidates:
            return None
        # Prefer exact fpga_tag match
        for c in candidates:
            if c.get("fpga_id") == fpga_tag:
                return c
        return candidates[0]

    # ── Scheduling ──────────────────────────────────────────────────────────

    async def schedule_pending_tasks(self):
        """Dispatch pending tasks to available workers (master-push mode)."""
        tasks = await self.list_tasks()
        workers = await self.get_workers()
        all_fpgas = await self.get_fpgas()

        pending = [t for t in tasks if t.get("status") == "pending"]
        online_workers = {
            w["worker_id"]: w for w in workers
            if w.get("status") == "online" and w.get("worker_id")
        }

        for task_data in pending:
            tag = task_data.get("worker_tag", "")
            matching_workers = [
                w for w in online_workers.values()
                if tag in w.get("tags", [])
                   and w.get("current_load", 0) < w.get("max_capacity", 4)
            ]

            # FPGA matching
            matched_fpga = self._match_fpga(task_data, all_fpgas)
            if matched_fpga is None:
                # No available FPGA for this task → scheduling error
                task_data["status"] = "scheduling_error"
                task_data["scheduling_error"] = (
                    f"No idle FPGA matches fpga_tag='{task_data.get('fpga_tag', '')}'"
                    f" project_board='{task_data.get('project_board', '')}'"
                    f" is_test={task_data.get('is_test', False)}"
                )
                await self.cluster_repo._client.put(
                    f"/cluster/tasks/{task_data['task_id']}",
                    json.dumps(task_data),
                )
                logger.warning(
                    "Task %s → scheduling_error: %s",
                    task_data["task_id"], task_data["scheduling_error"],
                )
                continue

            # Set the resolved FPGA on the task
            task_data["target_fpga_id"] = matched_fpga["fpga_id"]

            # Prefer the worker that physically hosts the matched FPGA
            fpga_worker_id = matched_fpga.get("worker_id", "")
            if fpga_worker_id and fpga_worker_id in online_workers:
                worker = online_workers[fpga_worker_id]
            elif matching_workers:
                worker = min(matching_workers, key=lambda w: w.get("current_load", 0))
            else:
                continue  # no online worker with the right tag

            worker_url = f"http://{worker.get('node_ip', worker['worker_id'])}:3031"
            try:
                async with httpx.AsyncClient(timeout=10) as client:
                    await client.post(f"{worker_url}/tasks/execute", json=task_data)
                task_data["status"] = "assigned"
                task_data["assigned_worker_id"] = worker["worker_id"]
                await self.cluster_repo._client.put(
                    f"/cluster/tasks/{task_data['task_id']}",
                    json.dumps(task_data),
                )
            except Exception as exc:
                logger.warning("Could not dispatch task %s: %s", task_data["task_id"], exc)
