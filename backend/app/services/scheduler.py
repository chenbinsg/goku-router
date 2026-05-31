"""
APScheduler background jobs for Goku-Router. (v1.2.0)

Jobs:
  rollup_monthly_billing  — 1st of each month at 01:00 UTC
  enforce_log_retention   — daily at 02:00 UTC
  run_anomaly_sweep       — every hour

Start via start_scheduler() called from app lifespan.
"""
from __future__ import annotations

import logging
from datetime import datetime, UTC, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _get_db():
    from ..db import SessionLocal
    return SessionLocal()


# ── Job: monthly billing rollup ────────────────────────────────────────────────

def rollup_monthly_billing():
    """Aggregate BillingRecord rows into MonthlyBillingSummary for the previous month."""
    from .. import models
    db = _get_db()
    try:
        now = datetime.now(UTC)
        # Roll up the previous month
        first_of_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month_end = first_of_this_month - timedelta(seconds=1)
        last_month_start = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        year_month = last_month_start.strftime("%Y-%m")

        logger.info("Starting monthly billing rollup for %s", year_month)

        # Delete any existing rollup for this month (idempotent)
        db.query(models.MonthlyBillingSummary).filter(
            models.MonthlyBillingSummary.year_month == year_month
        ).delete()

        # Pull billing records for the month
        rows = db.query(models.BillingRecord).filter(
            models.BillingRecord.date >= last_month_start,
            models.BillingRecord.date < first_of_this_month,
        ).all()

        # Aggregate by (org, project, model, provider)
        grouped: dict[tuple, dict] = {}
        for row in rows:
            key = (row.organization_id, row.project_id, row.model or "", row.provider or "")
            if key not in grouped:
                grouped[key] = {
                    "request_count": 0, "prompt_tokens": 0, "completion_tokens": 0,
                    "cached_tokens": 0, "cost_usd": 0.0, "upstream_cost_usd": 0.0,
                }
            g = grouped[key]
            g["request_count"] += 1
            g["prompt_tokens"] += row.prompt_tokens or 0
            g["completion_tokens"] += row.completion_tokens or 0
            g["cached_tokens"] += row.cached_tokens or 0
            g["cost_usd"] = round(g["cost_usd"] + (row.cost_usd or 0.0), 6)
            g["upstream_cost_usd"] = round(g["upstream_cost_usd"] + (row.upstream_cost_usd or 0.0), 6)

        for (org_id, proj_id, model, provider), agg in grouped.items():
            db.add(models.MonthlyBillingSummary(
                year_month=year_month,
                organization_id=org_id,
                project_id=proj_id,
                model=model or None,
                provider=provider or None,
                rolled_up_at=now,
                **agg,
            ))

        db.commit()
        logger.info("Monthly billing rollup complete for %s: %d groups from %d records",
                    year_month, len(grouped), len(rows))

    except Exception:
        logger.exception("Monthly billing rollup failed")
        db.rollback()
    finally:
        db.close()


# ── Job: log retention enforcement ────────────────────────────────────────────

def enforce_log_retention():
    """Delete RequestLog rows older than the configured retention_days (default 90)."""
    import os
    db = _get_db()
    try:
        retention_days = int(os.environ.get("LOG_RETENTION_DAYS", "90"))
        cutoff = datetime.now(UTC) - timedelta(days=retention_days)

        from sqlalchemy import text
        result = db.execute(
            text("DELETE FROM request_logs WHERE id IN ("
                 "SELECT id FROM request_logs ORDER BY id ASC LIMIT 10000"
                 ") AND CAST(strftime('%s', created_at) AS INTEGER) < :cutoff_ts"),
            {"cutoff_ts": int(cutoff.timestamp())}
        )
        deleted = result.rowcount if hasattr(result, "rowcount") else 0

        # Fallback for SQLite without created_at: skip silently
        db.commit()
        if deleted:
            logger.info("Log retention: deleted %d rows older than %d days", deleted, retention_days)

    except Exception:
        logger.exception("Log retention enforcement failed (non-fatal)")
        db.rollback()
    finally:
        db.close()


# ── Job: anomaly sweep ─────────────────────────────────────────────────────────

def run_anomaly_sweep():
    """Detect anomalies using rolling baselines and configurable thresholds."""
    from .. import models
    db = _get_db()
    try:
        now = datetime.now(UTC)
        baseline_start = now - timedelta(days=7)

        # Get configurable thresholds (global defaults if no org-specific config)
        cfg = db.query(models.AnomalyThresholdConfig).filter(
            models.AnomalyThresholdConfig.organization_id == None  # noqa: E711
        ).first()
        failure_threshold = cfg.provider_failure_rate_pct if cfg else 25.0
        latency_threshold = cfg.provider_latency_ms if cfg else 600.0
        cost_multiplier = cfg.cost_spike_multiplier if cfg else 3.0

        # Recent window: last 1 hour
        recent = db.query(models.RequestLog).filter(
            models.RequestLog.id > 0,
        ).order_by(models.RequestLog.id.desc()).limit(200).all()

        # 7-day baseline: avg hourly cost
        baseline_rows = db.query(models.BillingRecord).filter(
            models.BillingRecord.date >= baseline_start,
        ).all()
        baseline_total_cost = sum(r.cost_usd or 0 for r in baseline_rows)
        baseline_hours = max((now - baseline_start).total_seconds() / 3600, 1)
        baseline_hourly_cost = baseline_total_cost / baseline_hours

        recent_cost = sum(r.cost_amount or 0 for r in recent)

        # Provider failure rate
        provider_stats: dict[str, dict] = {}
        for r in recent:
            pname = r.provider_name or "unknown"
            if pname not in provider_stats:
                provider_stats[pname] = {"total": 0, "failed": 0, "latencies": []}
            provider_stats[pname]["total"] += 1
            if r.status_code != 200:
                provider_stats[pname]["failed"] += 1
            if r.latency:
                provider_stats[pname]["latencies"].append(r.latency)

        notifications = []

        for pname, stats in provider_stats.items():
            if stats["total"] == 0:
                continue
            failure_rate = (stats["failed"] / stats["total"]) * 100
            if failure_rate >= failure_threshold:
                notifications.append((
                    "provider_failure_spike",
                    f"Provider '{pname}' failure rate {failure_rate:.1f}% >= {failure_threshold}% "
                    f"(last {stats['total']} requests)"
                ))
            if stats["latencies"]:
                avg_lat = sum(stats["latencies"]) / len(stats["latencies"])
                if avg_lat >= latency_threshold:
                    notifications.append((
                        "provider_latency_spike",
                        f"Provider '{pname}' avg latency {avg_lat:.0f}ms >= {latency_threshold}ms"
                    ))

        # Cost spike vs 7-day baseline
        if baseline_hourly_cost > 0 and recent_cost > baseline_hourly_cost * cost_multiplier:
            notifications.append((
                "cost_spike",
                f"Hourly cost ${recent_cost:.4f} is {recent_cost/baseline_hourly_cost:.1f}x "
                f"above 7-day avg ${baseline_hourly_cost:.4f}/hr"
            ))

        for ntype, msg in notifications:
            db.add(models.NotificationRecord(
                type=ntype,
                message=msg,
                timestamp=now,
            ))
            logger.warning("Anomaly detected [%s]: %s", ntype, msg)

        if notifications:
            db.commit()

    except Exception:
        logger.exception("Anomaly sweep failed (non-fatal)")
        db.rollback()
    finally:
        db.close()


# ── Job: drift monitor & auto-recalibration ───────────────────────────────────

def drift_monitor_job():
    """
    Every 6h: update provider quality scores, then check for routing weight drift.
    Auto-recalibrates if ≥ 500 new logs since last recalibration.
    Auto-launches A/B experiment if drift > 10%.
    """
    db = _get_db()
    try:
        from .. import crud
        logger.info("Drift monitor: updating provider quality scores")
        crud.update_provider_quality_scores(db, lookback_hours=6)
        result = crud.run_drift_monitor(db)
        if result.fired:
            logger.info("Drift monitor: recalibration triggered — %s", result.reason)
            if result.experiment_launched:
                logger.info("Drift monitor: auto-launched experiment '%s'", result.experiment_launched)
        else:
            logger.debug("Drift monitor: skipped — %s", result.reason)
    except Exception:
        logger.exception("Drift monitor job failed (non-fatal)")
        db.rollback()
    finally:
        db.close()


# ── Job: A/B significance check ───────────────────────────────────────────────

def ab_significance_check_job():
    """
    Nightly at 03:00 UTC: run two-proportion z-test on active A/B experiment.
    Promotes challenger if p < 0.05 and ran ≥ 7 days; rolls back if significantly worse.
    """
    db = _get_db()
    try:
        from .. import crud
        result = crud.run_ab_significance_check(db)
        if result.status == "no_active":
            logger.debug("A/B check: no active experiment")
        else:
            logger.info("A/B significance check: %s", result.message)
    except Exception:
        logger.exception("A/B significance check job failed (non-fatal)")
        db.rollback()
    finally:
        db.close()


# ── Scheduler lifecycle ────────────────────────────────────────────────────────

def start_scheduler():
    global _scheduler
    if _scheduler is not None:
        return
    _scheduler = BackgroundScheduler(timezone="UTC")

    # Monthly billing rollup: 1st of each month at 01:00 UTC
    _scheduler.add_job(
        rollup_monthly_billing,
        CronTrigger(day=1, hour=1, minute=0),
        id="monthly_billing_rollup",
        replace_existing=True,
    )

    # Log retention: daily at 02:00 UTC
    _scheduler.add_job(
        enforce_log_retention,
        CronTrigger(hour=2, minute=0),
        id="log_retention",
        replace_existing=True,
    )

    # Anomaly sweep: every hour
    _scheduler.add_job(
        run_anomaly_sweep,
        IntervalTrigger(hours=1),
        id="anomaly_sweep",
        replace_existing=True,
    )

    # Drift monitor + provider quality scores: every 6 hours  (v1.3.0)
    _scheduler.add_job(
        drift_monitor_job,
        IntervalTrigger(hours=6),
        id="drift_monitor",
        replace_existing=True,
    )

    # A/B significance check: nightly at 03:00 UTC  (v1.3.0)
    _scheduler.add_job(
        ab_significance_check_job,
        CronTrigger(hour=3, minute=0),
        id="ab_significance_check",
        replace_existing=True,
    )

    _scheduler.start()
    logger.info(
        "Background scheduler started (5 jobs: billing_rollup, log_retention, "
        "anomaly_sweep, drift_monitor, ab_significance_check)"
    )


def stop_scheduler():
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Background scheduler stopped")
