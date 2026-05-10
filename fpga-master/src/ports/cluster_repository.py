from typing import List, Dict

class ClusterRepository:
    async def register_master(self, node_id: str, info: Dict, ttl: int):
        raise NotImplementedError

    async def get_masters(self) -> List[Dict]:
        raise NotImplementedError

    async def register_worker(self, node_id: str, info: Dict, ttl: int):
        raise NotImplementedError

    async def get_workers(self) -> List[Dict]:
        raise NotImplementedError

    async def unregister(self, prefix: str, node_id: str):
        raise NotImplementedError