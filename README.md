# riotgames-retrieve

I needed a script to back up full match histories and timeline dumps for high-elo accounts without constantly writing rate limiter loops every time.

Stores structured match data in a local SQLite file and dumps raw json timeline frames into compressed `.ndjson.zst` archives by match ID.

## Install

```bash
pip install .
```

For local dev and running tests:
```bash
pip install -e ".[dev]"
pytest
```

## Authentication

Export your key:

```bash
export RIOT_API_KEY="RGAPI-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

You can also pass `--api-key` on any command if you don't want it in your shell environment.

## Usage

Crawl games starting from a specific account:

```bash
riotgames-retrieve crawl --name "Faker" --tag "KR1" --region kr --count 200 --db kr_matches.db
```

Crawl ranked ladder matches directly from Challenger league:

```bash
riotgames-retrieve seed-ladder --region na1 --queue RANKED_SOLO_5x5 --tier CHALLENGER --max-matches 1000
```

Fetch a batch of raw match IDs from a text file:

```bash
riotgames-retrieve fetch-matches --input-file ids.txt --region euw1 --out-dir ./raw_timelines
```

Inspect database stats:

```bash
riotgames-retrieve stats --db kr_matches.db
```

## Rate limits

The client tracks response headers (`X-App-Rate-Limit`, `X-Method-Rate-Limit`) and sleeps proactively when the bucket fills up. If Riot sends back a 429 anyway, it honors `Retry-After` with jitter.

<!-- updated: 2026-09-14 -->
