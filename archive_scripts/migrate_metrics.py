"""
migrate_metrics.py — add consensus provenance and timing columns to blocks.

    python migrate_metrics.py

Adds five columns used by the protocol comparison:

    consensus       which protocol produced the block (CB-BFT / Raft / PBFT)
    scoring_ms      CRITIC scoring + adaptive clustering
    consensus_ms    leader election + voting
    onchain_ms      Besu transaction round-trip
    total_ms        whole donation pipeline

Existing blocks are left labelled 'CB-BFT' with zero timings. When comparing,
filter to blocks created AFTER this migration -- older rows predate the
instrumentation and their timings are not real measurements.

Safe to run more than once.
"""

import asyncio
from sqlalchemy import text
from database import engine

STATEMENTS = [
    "ALTER TABLE blocks ADD COLUMN IF NOT EXISTS consensus VARCHAR DEFAULT 'CB-BFT'",
    "ALTER TABLE blocks ADD COLUMN IF NOT EXISTS scoring_ms DOUBLE PRECISION DEFAULT 0",
    "ALTER TABLE blocks ADD COLUMN IF NOT EXISTS consensus_ms DOUBLE PRECISION DEFAULT 0",
    "ALTER TABLE blocks ADD COLUMN IF NOT EXISTS onchain_ms DOUBLE PRECISION DEFAULT 0",
    "ALTER TABLE blocks ADD COLUMN IF NOT EXISTS total_ms DOUBLE PRECISION DEFAULT 0",
    "CREATE INDEX IF NOT EXISTS idx_blocks_consensus ON blocks (consensus)",
]


async def main() -> None:
    async with engine.begin() as conn:
        for stmt in STATEMENTS:
            await conn.execute(text(stmt))
        print("✅ Added: consensus, scoring_ms, consensus_ms, onchain_ms, total_ms")

        result = await conn.execute(text(
            "SELECT consensus, COUNT(*) FROM blocks GROUP BY consensus"))
        rows = list(result)
        if rows:
            print("\nExisting blocks by label:")
            for r in rows:
                print(f"  {str(r[0]):<10} {r[1]} blocks")

        latest = await conn.execute(text("SELECT COALESCE(MAX(index), 0) FROM blocks"))
        m = latest.scalar() or 0
        print(f"\nHighest block index: {m}")
        print(f"\n>>> Set MIN_INDEX = {m} in export_results.py")
        print("    Blocks at or below that index predate the instrumentation")
        print("    and carry no real timings.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())