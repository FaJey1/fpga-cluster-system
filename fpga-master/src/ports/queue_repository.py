from typing import List, Dict, Tuple
from src.entities.project import Project
from src.entities.task import Task


class QueueRepository:
    async def push_project(self, project: Project) -> None:
        raise NotImplementedError

    async def pop_project(self) -> Project:
        raise NotImplementedError

    async def list_queue(self) -> List[Dict]:
        raise NotImplementedError

    async def remove_project(self, project_id: str) -> Tuple[bool, Project]:
        raise NotImplementedError

    async def push_task(self, task: Task) -> None:
        raise NotImplementedError

    async def clear_tasks(self) -> None:
        raise NotImplementedError
