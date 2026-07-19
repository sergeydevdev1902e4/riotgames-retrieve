import argparse
import os
import sys
import logging
from pathlib import Path
from riotgames_retrieve.client import RiotClient
from riotgames_retrieve.storage import StorageEngine
from riotgames_retrieve.crawler import MatchCrawler
from riotgames_retrieve.regions import Platform, resolve_regional_route

logger = logging.getLogger("riotgames_retrieve")


def setup_logging(verbose: bool):
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def cmd_account(args):
    api_key = args.api_key or os.getenv("RIOT_API_KEY")
    if not api_key:
        sys.exit("Error: RIOT_API_KEY not set in environment or passed via --api-key")

    client = RiotClient(api_key=api_key)
    platform = Platform(args.region.lower())
    region_route = resolve_regional_route(platform)

    if "#" not in args.riot_id:
        sys.exit("Error: riot id must be in format GameName#TagLine")

    name, tag = args.riot_id.split("#", 1)
    account = client.get_account_by_riot_id(region_route, name, tag)
    if not account:
        print(f"Account {args.riot_id} not found.")
        return 1

    print(f"Game Name: {account.game_name}#{account.tag_line}")
    print(f"PUUID:     {account.puuid}")
    return 0


def cmd_backfill(args):
    api_key = args.api_key or os.getenv("RIOT_API_KEY")
    if not api_key:
        sys.exit("Error: RIOT_API_KEY not set in environment or passed via --api-key")

    # quick sanity check for output dirs
    Path(args.ndjson_dir).mkdir(parents=True, exist_ok=True)

    platform = Platform(args.region.lower())
    storage = StorageEngine(args.db, ndjson_dir=args.ndjson_dir)
    client = RiotClient(api_key=api_key)
    crawler = MatchCrawler(client=client, storage=storage)

    puuid = args.puuid
    if not puuid:
        if not args.riot_id or "#" not in args.riot_id:
            sys.exit("Error: provide --puuid or --riot-id Name#Tag")
        name, tag = args.riot_id.split("#", 1)
        region_route = resolve_regional_route(platform)
        acc = client.get_account_by_riot_id(region_route, name, tag)
        if not acc:
            sys.exit(f"Error: account {args.riot_id} not found")
        puuid = acc.puuid

    # print(f"debug: starting crawl on {puuid}")
    print(f"Starting backfill for {puuid} ({platform.value})...")
    crawler.backfill_player(
        puuid=puuid,
        platform=platform,
        max_matches=args.count,
        queue_id=args.queue,
        include_timeline=not args.no_timeline,
        start_time=args.start_time,
    )
    return 0


def cmd_export(args):
    storage = StorageEngine(args.db, ndjson_dir=args.ndjson_dir)
    out_file = args.out

    # TODO: add parquet export option once pyarrow is considered as optional dep
    count = storage.export_summary(out_file, fmt=args.format)
    print(f"Exported {count} match summaries to {out_file}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="riot-retrieve",
        description="Bulk archive matches and timelines from Riot API without hitting limits.",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument("--api-key", help="Riot API key (defaults to RIOT_API_KEY env var)")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # account lookup
    p_acc = subparsers.add_parser("account", help="Resolve Riot ID to PUUID")
    p_acc.add_argument("riot_id", help="Riot ID in Name#Tag format")
    p_acc.add_argument("--region", default="na1", help="Platform region (e.g. na1, euw1, kr)")
    p_acc.set_defaults(func=cmd_account)

    # backfill matches
    p_back = subparsers.add_parser("backfill", help="Download match history and timelines")
    p_back.add_argument("--riot-id", help="Riot ID (GameName#TagLine)")
    p_back.add_argument("--puuid", help="Target player PUUID (skips account lookup if provided)")
    p_back.add_argument("--region", default="na1", help="Platform region (default: na1)")
    p_back.add_argument("--count", type=int, default=100, help="Max matches to check (default: 100)")
    p_back.add_argument("--queue", type=int, default=None, help="Queue ID filter (e.g. 420 for Solo/Duo, 440 for Flex)")
    p_back.add_argument("--start-time", type=int, default=None, help="Epoch timestamp in seconds to filter matches after")
    p_back.add_argument("--no-timeline", action="store_true", help="Skip downloading timeline ndjson data")
    p_back.add_argument("--db", default="matches.db", help="SQLite file path (default: matches.db)")
    p_back.add_argument("--ndjson-dir", default="timelines", help="Folder for compressed timelines")
    p_back.set_defaults(func=cmd_backfill)

    # export
    p_exp = subparsers.add_parser("export", help="Export saved matches into json or csv format")
    p_exp.add_argument("--db", default="matches.db", help="SQLite database path")
    p_exp.add_argument("--ndjson-dir", default="timelines", help="Folder for compressed timelines")
    p_exp.add_argument("-o", "--out", default="matches_export.csv", help="Output file path")
    p_exp.add_argument("--format", choices=["csv", "json"], default="csv", help="Export format")
    p_exp.set_defaults(func=cmd_export)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    setup_logging(args.verbose)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\nAborted by user.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main() or 0)
