"""APScheduler 기반 주기 갱신."""
import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from .config import REFRESH_SCHEDULE
from .refresh import run_refresh

log = logging.getLogger("finance.scheduler")
_scheduler = None


def start():
    global _scheduler
    if not REFRESH_SCHEDULE:
        log.info("REFRESH_SCHEDULE 비어 있음 → 자동 갱신 비활성")
        return None
    _scheduler = BackgroundScheduler(timezone=None)
    trigger = CronTrigger.from_crontab(REFRESH_SCHEDULE)
    _scheduler.add_job(run_refresh, trigger, id="refresh", name="데이터 갱신", max_instances=1, coalesce=True)
    _scheduler.start()
    log.info("자동 갱신 스케줄: %s", REFRESH_SCHEDULE)
    return _scheduler


def next_run():
    if not _scheduler:
        return None
    job = _scheduler.get_job("refresh")
    return job.next_run_time.isoformat() if job and job.next_run_time else None


def stop():
    if _scheduler:
        _scheduler.shutdown(wait=False)
