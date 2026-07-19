import asyncio
import logging
from collections import deque
from typing import Optional, Set

from riotgames_retrieve.client import RiotClient
from riotgames_retrieve.storage import Storage

logger = logging.getLogger(__name__)


class MatchCrawler:
    """Crawls matches across summoners starting from seed accounts."""

    def __init__(
        self,
        client: RiotClient,
        storage: Storage,
        region: str,
        max_matches: int = 1000,
        include_timeline: bool = True,
        max_queue_depth: int = 50000,
        batch_size: int = 100,
        queue_id: Optional[int] = None,
    ):
        self.client = client
        self.storage = storage
        self.region = region
        self.max_matches = max_matches
        self.include_timeline = include_timeline
        self.max_queue_depth = max_queue_depth
        self.batch_size = min(batch_size, 100)  # riot limit is 100
        self.queue_id = queue_id

        self._puuid_queue: deque[str] = deque()
        self._seen_puuids: Set[str] = set()
        self._seen_matches: Set[str] = set()
        self._saved_count = 0
        self._consecutive_errors = 0
        self._stop_requested = False

    def add_seeds(self, puuids: list[str]) -> None:
        for p in puuids:
            if p and p not in self._seen_puuids:
                self._seen_puuids.add(p)
                self._puuid_queue.append(p)

    def stop(self) -> None:
        self._stop_requested = True

    async def run(self) -> int:
        existing = self.storage.get_existing_match_ids()
        self._seen_matches.update(existing)
        logger.info("loaded %d existing match ids from storage", len(existing))

        while self._puuid_queue and not self._stop_requested:
            if self._saved_count >= self.max_matches:
                logger.info("reached max matches target (%d)", self.max_matches)
                break

            puuid = self._puuid_queue.popleft()
            try:
                await self._process_puuid(puuid)
                self._consecutive_errors = 0
            except Exception as exc:
                self._consecutive_errors += 1
                logger.warning("failed processing puuid %s (%d in a row): %s", puuid[:8], self._consecutive_errors, exc)
                if self._consecutive_errors > 25:
                    logger.error("too many consecutive errors, aborting crawl run")
                    break
                await asyncio.sleep(0.5)

        return self._saved_count

    async def _process_puuid(self, puuid: str) -> None:
        start_index = 0
        # Riot API sometimes returns empty list or duplicates if you page too far
        while start_index < 300 and not self._stop_requested:
            match_ids = await self.client.get_match_ids_by_puuid(
                self.region,
                puuid,
                start=start_index,
                count=self.batch_size,
                queue=self.queue_id,
            )
            if not match_ids:
                break

            new_in_batch = 0
            for match_id in match_ids:
                if self._stop_requested or self._saved_count >= self.max_matches:
                    break
                if match_id in self._seen_matches:
                    continue

                self._seen_matches.add(match_id)
                success = await self._fetch_and_save_match(match_id)
                if success:
                    self._saved_count += 1
                    new_in_batch += 1
                    if self._saved_count % 50 == 0:
                        logger.info("progress: %d/%d matches archived", self._saved_count, self.max_matches)

            # if all matches in this batch were already known, player history probably overlaps completely
            if new_in_batch == 0 and len(match_ids) == self.batch_size:
                # print(f"debug: skipping rest of history for {puuid[:8]}")
                break

            start_index += len(match_ids)
            if len(match_ids) < self.batch_size:
                break

    async def _fetch_and_save_match(self, match_id: str) -> bool:
        # FIXME: arena matches (queue 1700) occasionally return 200 with truncated participant info
        try:
            match_data = await self.client.get_match(self.region, match_id)
        except Exception as err:
            logger.debug("skipping match %s due to error: %s", match_id, err)
            return False

        if not match_data or "info" not in match_data:
            return False

        timeline_data = None
        if self.include_timeline:
            try:
                timeline_data = await self.client.get_timeline(self.region, match_id)
            except Exception as err:
                logger.warning("could not load timeline for %s: %s", match_id, err)

        self.storage.save_match(match_id, match_data, timeline_data)

        # don't explode memory if we already have plenty of accounts queued
        if len(self._puuid_queue) < self.max_queue_depth:
            metadata = match_data.get("metadata", {})
            participants = metadata.get("participants", [])
            for participant_puuid in participants:
                if participant_puuid not in self._seen_puuids:
                    self._seen_puuids.add(participant_puuid)
                    self._puuid_queue.append(participant_puuid)

        return True
