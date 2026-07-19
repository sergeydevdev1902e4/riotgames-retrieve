import time
import logging
import httpx
from typing import Any, Dict, List, Optional
from riotgames_retrieve.limiter import RateLimiter
from riotgames_retrieve.regions import platform_to_regional

log = logging.getLogger(__name__)

class RiotClient:
    """HTTP transport handling rate limits, exponential backoff, and regional routing."""

    def __init__(
        self,
        api_key: str,
        limiter: Optional[RateLimiter] = None,
        timeout: float = 15.0,
        max_retries: int = 5,
    ):
        self.api_key = api_key
        self.limiter = limiter
        self.timeout = timeout
        self.max_retries = max_retries
        self._client = httpx.Client(
            timeout=httpx.Timeout(timeout, connect=5.0),
            headers={
                "X-Riot-Token": api_key,
                "User-Agent": "riotgames-retrieve/0.2.0",
            },
        )

    def _get(self, host: str, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"https://{host}.api.riotgames.com{path}"
        
        for attempt in range(self.max_retries):
            if self.limiter:
                self.limiter.acquire(host)

            try:
                resp = self._client.get(url, params=params)
            except (httpx.ConnectError, httpx.ReadTimeout) as err:
                if attempt == self.max_retries - 1:
                    raise
                log.warning("network glitch on %s: %s (attempt %d)", url, err, attempt + 1)
                time.sleep(1.0 * (attempt + 1))
                continue

            # print(f"DEBUG: {resp.status_code} {url} headers={dict(resp.headers)}")
            
            if self.limiter and "X-App-Rate-Limit-Count" in resp.headers:
                self.limiter.update_from_headers(host, resp.headers)

            if resp.status_code == 200:
                return resp.json()

            if resp.status_code == 404:
                return None

            if resp.status_code == 429:
                raw_retry = resp.headers.get("Retry-After")
                retry_after = int(raw_retry) if raw_retry and raw_retry.isdigit() else (2 ** attempt)
                # Riot occasionally returns 429 under extreme burst without Retry-After
                log.info("hit rate limit on %s, backing off for %ds", host, retry_after)
                time.sleep(retry_after + 0.1)
                continue

            if resp.status_code in (500, 502, 503, 504):
                wait = 0.5 * (2 ** attempt)
                log.warning("riot server error %d on %s, retrying in %.1fs", resp.status_code, url, wait)
                time.sleep(wait)
                continue

            resp.raise_for_status()

        raise RuntimeError(f"request failed after {self.max_retries} retries: {url}")

    def get_account_by_riot_id(self, regional_host: str, game_name: str, tag_line: str) -> Optional[Dict[str, Any]]:
        path = f"/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
        return self._get(regional_host, path)

    def get_account_by_puuid(self, regional_host: str, puuid: str) -> Optional[Dict[str, Any]]:
        path = f"/riot/account/v1/accounts/by-puuid/{puuid}"
        return self._get(regional_host, path)

    def get_match_ids(
        self,
        regional_host: str,
        puuid: str,
        start: int = 0,
        count: int = 100,
        queue: Optional[int] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> List[str]:
        params: Dict[str, Any] = {"start": start, "count": min(count, 100)}
        if queue is not None:
            params["queue"] = queue
        if start_time is not None:
            params["startTime"] = start_time
        if end_time is not None:
            params["endTime"] = end_time

        path = f"/lol/match/v5/matches/by-puuid/{puuid}/ids"
        res = self._get(regional_host, path, params=params)
        return res or []

    def get_match(self, regional_host: str, match_id: str) -> Optional[Dict[str, Any]]:
        path = f"/lol/match/v5/matches/{match_id}"
        return self._get(regional_host, path)

    def get_timeline(self, regional_host: str, match_id: str) -> Optional[Dict[str, Any]]:
        path = f"/lol/match/v5/matches/{match_id}/timeline"
        return self._get(regional_host, path)

    def get_summoner_by_puuid(self, platform_host: str, puuid: str) -> Optional[Dict[str, Any]]:
        path = f"/lol/summoner/v4/summoners/by-puuid/{puuid}"
        return self._get(platform_host, path)

    def close(self) -> None:
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
