"""
scheduler.py — background monitor for the CB-BFT Besu network.

The node simulation that used to live here is gone. Validator attributes are no
longer invented in Postgres: CB-BFT derives them from block headers inside each
Besu node, so there is nothing for this process to score, cluster or elect.

What remains is a liveness probe. Every 60 seconds it asks the chain for its
head block and logs whether the height is advancing, which is the one thing the
application genuinely needs to know about the consensus layer.
"""

import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from blockchain_client import blockchain

logger    = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()

_last_height = {"value": None}


async def probe_chain():
    """Log chain progress. A stalled height is the signal that matters."""
    try:
        if not getattr(blockchain, "enabled", False):
            logger.warning("Chain probe skipped — blockchain client is disabled")
            return

        height = blockchain.w3.eth.block_number
        previous = _last_height["value"]
        _last_height["value"] = height

        if previous is None:
            logger.info(f"Chain probe — head at block {height}")
        elif height > previous:
            logger.info(f"Chain probe — head at block {height} (+{height - previous})")
        else:
            logger.warning(
                f"Chain probe — head still at block {height}; no new blocks since last probe"
            )

    except Exception as e:
        logger.error(f"Chain probe failed: {e}")


def start_scheduler():
    scheduler.add_job(
        probe_chain,
        trigger          = "interval",
        seconds          = 60,
        id               = "chain_probe",
        name             = "CB-BFT chain liveness probe",
        replace_existing = True,
    )
    scheduler.start()
    logger.info("Chain liveness probe started — every 60 seconds")


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Scheduler stopped")