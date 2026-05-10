import asyncio
import time
import logging
from typing import List, Dict, Any, Optional

from fpga_worker.entities.fpga import FPGA, FPGAStatus, InterfaceType, FPGASpecs
from fpga_worker.entities.task import Task, TaskStatus, TaskMode
from fpga_worker.ports.fpga_repository import FPGARepository
from fpga_worker.ports.task_queue import TaskQueue
from fpga_worker.ports.master_client import MasterClient
from fpga_worker.ports.connection_port import ConnectionFactory

logger = logging.getLogger(__name__)


def _load_test_vectors(tests_url: str) -> List[Dict[str, Any]]:
    """Simulate loading test vectors from S3. In production would fetch from tests_url."""
    import hashlib
    seed = int(hashlib.md5(tests_url.encode()).hexdigest()[:8], 16)
    import random as _rnd
    _rnd.seed(seed)
    count = _rnd.randint(10, 14)
    vectors = []
    for i in range(count):
        inp = [_rnd.randint(0, 255) for _ in range(4)]
        expected = [x ^ 0xAA for x in inp]
        vectors.append({
            "label": f"vec_{i:03d}",
            "input": inp,
            "expected_output": expected,
        })
    return vectors


class WorkerUseCases:
    def __init__(
        self,
        worker_id: str,
        tags: List[str],
        fpga_repo: FPGARepository,
        task_queue: TaskQueue,
        master_client: MasterClient,
        connection_factory: ConnectionFactory,
    ):
        self.worker_id = worker_id
        self.tags = tags
        self.fpga_repo = fpga_repo
        self.task_queue = task_queue
        self.master_client = master_client
        self.connection_factory = connection_factory
        self._running_tasks: Dict[str, bool] = {}

    async def register_fpga(self, fpga_data: Dict[str, Any]) -> FPGA:
        specs = FPGASpecs.from_dict(fpga_data.get("specs", {}))
        fpga = FPGA(
            fpga_id=fpga_data["fpga_id"],
            worker_id=self.worker_id,
            model=fpga_data["model"],
            vendor=fpga_data["vendor"],
            serial_number=fpga_data["serial_number"],
            interface=InterfaceType(fpga_data.get("interface", "usb")),
            emulator_url=fpga_data.get("emulator_url", ""),
            specs=specs,
        )
        await self.fpga_repo.save(fpga)
        logger.info("Registered FPGA %s on worker %s", fpga.fpga_id, self.worker_id)
        return fpga

    async def list_fpgas(self) -> List[FPGA]:
        return await self.fpga_repo.list()

    async def get_fpga(self, fpga_id: str) -> Optional[FPGA]:
        return await self.fpga_repo.get(fpga_id)

    async def get_worker_status(self) -> Dict[str, Any]:
        fpgas = await self.fpga_repo.list()
        busy = sum(1 for f in fpgas if f.status == FPGAStatus.BUSY)
        return {
            "worker_id": self.worker_id,
            "tags": self.tags,
            "status": "online",
            "fpga_count": len(fpgas),
            "busy_fpga_count": busy,
            "running_tasks": list(self._running_tasks.keys()),
            "last_heartbeat": int(time.time()),
        }

    async def execute_task(self, task: Task) -> Dict[str, Any]:
        """Execute a task: program FPGA, optionally run tests."""
        logger.info("Executing task %s on FPGA %s", task.task_id, task.target_fpga_id)
        self._running_tasks[task.task_id] = True

        fpga = await self.fpga_repo.get(task.target_fpga_id)
        if fpga is None:
            # pick any idle FPGA
            fpgas = await self.fpga_repo.list()
            idle = [f for f in fpgas if f.status == FPGAStatus.IDLE]
            if not idle:
                self._running_tasks.pop(task.task_id, None)
                return {"status": "failed", "error": "no idle FPGA available"}
            fpga = idle[0]

        await self.fpga_repo.update_status(fpga.fpga_id, FPGAStatus.BUSY.value)
        await self.master_client.update_fpga_status(fpga.fpga_id, "uploading")
        try:
            conn = self.connection_factory.create(fpga.interface.value, fpga.emulator_url)

            # Program the FPGA
            program_result = await conn.program(task.bitstream_url)
            if not program_result.get("success"):
                raise RuntimeError(f"Programming failed: {program_result}")

            result: Dict[str, Any] = {
                "status": "success",
                "fpga_id": fpga.fpga_id,
                "bitstream_url": task.bitstream_url,
                "programmed_at": int(time.time()),
                "report_url": f"s3://fpga-reports/{task.task_id}/report.json",
            }

            # Run structured test sequence if task is marked as test
            if task.is_test and task.tests_url:
                await self.master_client.update_fpga_status(fpga.fpga_id, "testing")
                test_vectors = _load_test_vectors(task.tests_url)
                seq_result = await conn.run_test_sequence(test_vectors)
                result["test_sequence_results"] = seq_result
                if not seq_result.get("success"):
                    result["status"] = "failed"
                    result["error"] = (
                        f"Test sequence failed: {seq_result.get('failed', '?')} "
                        f"of {seq_result.get('total', '?')} cases failed"
                    )
            elif task.mode == TaskMode.TEST and task.test_config:
                # Legacy test_config path
                await self.master_client.update_fpga_status(fpga.fpga_id, "testing")
                test_result = await conn.run_tests(task.test_config)
                result["test_results"] = test_result

            # Test tasks return FPGA to idle; deployment tasks leave it in "running"
            final_status = "idle" if task.is_test else "running"
            await self.fpga_repo.update_status(
                fpga.fpga_id, FPGAStatus.IDLE.value, task.bitstream_url
            )
            await self.master_client.update_fpga_status(fpga.fpga_id, final_status)

            # Report back to master
            await self.master_client.report_task_result(task.task_id, result)
            return result

        except Exception as exc:
            logger.exception("Task %s failed: %s", task.task_id, exc)
            await self.fpga_repo.update_status(fpga.fpga_id, FPGAStatus.IDLE.value)
            await self.master_client.update_fpga_status(fpga.fpga_id, "idle")
            error_result = {"status": "failed", "error": str(exc)}
            try:
                await self.master_client.report_task_result(task.task_id, error_result)
            except Exception:
                pass
            return error_result
        finally:
            self._running_tasks.pop(task.task_id, None)

    async def poll_and_execute(self):
        """Poll queue for each tag and execute tasks. Called by background loop."""
        for tag in self.tags:
            task = await self.task_queue.pop(tag)
            if task:
                asyncio.create_task(self.execute_task(task))

    async def send_heartbeat(self):
        status = await self.get_worker_status()
        try:
            await self.master_client.send_heartbeat(self.worker_id, status)
        except Exception as exc:
            logger.warning("Heartbeat failed: %s", exc)
