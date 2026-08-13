"""
Interval-based background process that runs workers.sync_data_content's
run_full_sync() (structural drift sync + data-content refresh + doc
regen + incremental re-embed) on a schedule.

Pure-Python (APScheduler), not tied to Windows Task Scheduler / cron /
systemd — the same `python -m workers.scheduler` process is meant to run
unchanged whether started by hand in a dev shell today or as a
systemd/Docker service later.

Run: python -m workers.scheduler
Configure the interval via the SYNC_INTERVAL_MINUTES env var (default 60).
"""

import logging
import os
from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from dotenv import load_dotenv

from app.db.session import get_connection
from workers.sync_data_content import run_full_sync

load_dotenv()

SYNC_INTERVAL_MINUTES = int(os.getenv("SYNC_INTERVAL_MINUTES", "60"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def sync_job():
    """One scheduled tick: run the full sync, log the outcome, never let a
    failure kill the scheduler process."""

    connection = get_connection()

    try:
        result = run_full_sync(connection)

        drift_detected = result["drift_result"]["drift_detected"]
        reindex_result = result["reindex_result"]

        logger.info(
            "Sync complete: drift_detected=%s embedded=%d unchanged=%d deleted=%d",
            drift_detected,
            len(reindex_result["embedded"]),
            reindex_result["unchanged"],
            len(reindex_result["deleted"]),
        )

    except Exception:
        logger.exception("Sync job failed")

    finally:
        connection.close()


def main():

    logger.info("Starting metadata sync scheduler (every %d minutes)...", SYNC_INTERVAL_MINUTES)

    scheduler = BlockingScheduler()
    # next_run_time=now so the first sync fires immediately on startup,
    # then repeats every SYNC_INTERVAL_MINUTES from there.
    scheduler.add_job(sync_job, "interval", minutes=SYNC_INTERVAL_MINUTES, next_run_time=datetime.now())

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
