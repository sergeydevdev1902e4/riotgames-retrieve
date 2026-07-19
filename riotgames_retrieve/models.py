from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class Account:
    puuid: str
    game_name: str
    tag_line: str
    region: str
    summoner_id: Optional[str] = None
    account_id: Optional[str] = None
    last_crawled_at: Optional[datetime] = None


@dataclass
class MatchSummary:
    match_id: str
    region: str
    game_datetime: int
    game_duration: int
    queue_id: int
    game_version: str
    participants: List[str] = field(default_factory=list)
    timeline_downloaded: bool = False


@dataclass
class CrawlTask:
    task_id: Optional[int]
    target_id: str
    task_type: str
    region: str
    status: TaskStatus = TaskStatus.PENDING
    attempts: int = 0
    last_error: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


@dataclass
class RawPayload:
    # used when piping match/timeline ndjson directly to disk
    key: str
    kind: str
    region: str
    data: Dict[str, Any]
    fetched_at: datetime = field(default_factory=datetime.utcnow)
