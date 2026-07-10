#!/usr/bin/env python3
"""Inspect / clean up Qdrant collections.

Collections are named <base>_<embedding_dim> (documents_768, …), so switching
embedding providers never corrupts data — it just orphans the old dimension's
collections. This script lists what exists and deletes what you no longer want.

  uv run python scripts/migrate_qdrant.py --list
  uv run python scripts/migrate_qdrant.py --drop documents_1536
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from qdrant_client import AsyncQdrantClient

from src.configs.settings import get_settings  # noqa: E402


async def list_collections(client: AsyncQdrantClient) -> None:
    s = get_settings()
    active = {
        s.documents_collection,
        s.history_collection,
        s.search_cache_collection,
        s.mem0_collection,
    }
    collections = (await client.get_collections()).collections
    if not collections:
        print("No collections.")
        return
    print(f"{'collection':<28} {'dim':>6} {'points':>8}  status")
    for c in sorted(collections, key=lambda c: c.name):
        info = await client.get_collection(c.name)
        dim = info.config.params.vectors.size
        points = info.points_count or 0
        status = "ACTIVE" if c.name in active else "orphaned (safe to --drop)"
        print(f"{c.name:<28} {dim:>6} {points:>8}  {status}")
    print(f"\nActive set for the current config ({s.embedding_provider}, "
          f"dim={s.embedding_dim}): {', '.join(sorted(active))}")


async def drop_collection(client: AsyncQdrantClient, name: str) -> None:
    s = get_settings()
    active = {
        s.documents_collection,
        s.history_collection,
        s.search_cache_collection,
        s.mem0_collection,
    }
    if name in active:
        confirm = input(
            f"'{name}' is ACTIVE for the current embedding config — its data "
            "will be lost and re-ingestion will be needed. Type the collection "
            "name to confirm: "
        )
        if confirm.strip() != name:
            print("Aborted.")
            return
    if not await client.collection_exists(name):
        print(f"'{name}' does not exist.")
        return
    await client.delete_collection(name)
    print(f"Dropped '{name}'.")


async def main() -> None:
    ap = argparse.ArgumentParser(description="Qdrant collection maintenance")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="list collections + status")
    group.add_argument("--drop", metavar="NAME", help="delete a collection by exact name")
    args = ap.parse_args()

    client = AsyncQdrantClient(url=get_settings().qdrant_url)
    try:
        if args.list:
            await list_collections(client)
        else:
            await drop_collection(client, args.drop)
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
