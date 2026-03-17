from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class Status:
    id: str
    name: str
    type: str  # backlog, unstarted, started, completed, canceled

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Label:
    id: str
    name: str
    color: str
    scope: str = "issue"  # "issue" or "project"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Comment:
    id: str
    issue_id: str
    body: str
    created_at: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Issue:
    id: str
    identifier: str       # e.g., "LAN-42"
    title: str
    description: str
    status: Status
    priority: int          # 0=None, 1=Urgent, 2=High, 3=Normal, 4=Low
    project_id: str | None
    project_name: str | None
    labels: list[Label]
    parent_id: str | None
    blocked_by: list[str] = field(default_factory=list)
    url: str = ""
    branch_name: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Project:
    id: str
    name: str
    url: str
    labels: list[Label] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProjectLink:
    id: str
    label: str
    url: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class User:
    id: str
    name: str
    email: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Team:
    id: str
    name: str
    key: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Document:
    id: str
    title: str
    url: str = ""

    def to_dict(self) -> dict:
        return asdict(self)
