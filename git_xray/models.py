from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FileChange:
    path: str
    additions: int  # -1 for binary files
    deletions: int  # -1 for binary files

    @property
    def churn(self) -> int:
        if self.additions < 0 or self.deletions < 0:
            return 0
        return self.additions + self.deletions


@dataclass
class Commit:
    hash: str
    author_name: str
    author_email: str
    timestamp: int
    subject: str
    files: list[FileChange] = field(default_factory=list)

    @property
    def date(self) -> datetime:
        return datetime.fromtimestamp(self.timestamp)


@dataclass
class Hotspot:
    path: str
    commit_count: int
    total_additions: int
    total_deletions: int
    total_churn: int
    risk_score: float  # 0.0 - 1.0


@dataclass
class BusFactorEntry:
    directory: str
    bus_factor: int
    total_commits: int
    top_contributors: list[tuple[str, int, float]]  # (name, commits, pct)
    risk: str  # CRITICAL, WARNING, OK


@dataclass
class CouplingEntry:
    file_a: str
    file_b: str
    score: float  # 0.0 - 1.0
    co_commits: int
    total_a: int
    total_b: int
    cross_directory: bool


@dataclass
class DecayEntry:
    path: str
    last_author: str
    last_date: datetime
    days_stale: int
    author_active: bool
    risk: str  # STALE, AGING, FRESH


@dataclass
class TrendPeriod:
    label: str
    commit_count: int
    total_additions: int
    total_deletions: int
    avg_churn: float
    file_count: int
    direction: str  # UP, DOWN, STABLE
