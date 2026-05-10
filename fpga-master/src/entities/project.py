from dataclasses import dataclass
from typing import Optional

@dataclass
class Project:
    project_id: str
    project_name: str
    sources_url: str
    pipiline_id: str

    def to_dict(self):
        return {
                "project_id": self.project_id,
                "project_name": self.project_name,
                "sources_url": self.sources_url,
                "pipiline_id": self.pipiline_id,
            }

    @staticmethod
    def from_dict(d):
        return Project(
                project_id=str(d["project_id"]),
                project_name=d.get("project_name", ""),
                sources_url=d.get("sources_url", ""),
                pipiline_id=d.get("pipiline_id", ""),
            )
