import os
import logging
from pathlib import Path
from zoneinfo import ZoneInfo  # Python 3.9+
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

# Import your runner
from weather_playlist import main as run_moodify

# Settings via .env or environment
TZ = os.getenv("TZ", "Europe/Dublin")          # your local timezone
RUN_TIME = os.getenv("RUN_TIME", "07:00")      # 24h "HH:MM"
TRACK_COUNT = os.getenv("TRACK_COUNT", None)   # optional override
DRY_RUN = os.getenv("DRY_RUN", None)           # "true"/"false" if you want

# Logging
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    filename=LOG_DIR / "scheduler.log",
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
console.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
logging.getLogger().addHandler(console)

# Parse RUN_TIME
try:
    HOUR, MINUTE = map(int, RUN_TIME.split(":"))
    assert 0 <= HOUR <= 23 and 0 <= MINUTE <= 59
except Exception:
    raise SystemExit("RUN_TIME must be in 'HH:MM' 24h format, e.g., 07:00")

def job():
    # Optional: set env overrides just for this run
    if TRACK_COUNT is not None:
        os.environ["TRACK_COUNT"] = TRACK_COUNT
    if DRY_RUN is not None:
        os.environ["DRY_RUN"] = DRY_RUN

    logging.info("Moodify run starting…")
    try:
        run_moodify()
        logging.info("Moodify run finished")
    except Exception:
        logging.exception("Moodify run failed")

if __name__ == "__main__":
    tz = ZoneInfo(TZ)
    sched = BlockingScheduler(timezone=tz)
    # coalesce=True -> if missed (machine slept), run once on resume
    # misfire_grace_time=3600 -> allow up to 1h late
    sched.add_job(
        job,
        CronTrigger(hour=HOUR, minute=MINUTE),
        id="moodify_daily",
        replace_existing=True,
        coalesce=True,
        misfire_grace_time=3600,
    )
    logging.info(f"Scheduled daily at {RUN_TIME} ({TZ}). Log: {LOG_DIR / 'scheduler.log'}")
    try:
        sched.start()
    except (KeyboardInterrupt, SystemExit):
        logging.info("Scheduler stopped.")
