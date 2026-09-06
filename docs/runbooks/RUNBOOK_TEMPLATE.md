# Runbook: <operation / incident name>

- **Applies to:** <service / flow / job>
- **Severity / trigger:** <when this runbook is used>
- **Owner:** <team / role>

## Summary

One paragraph: what this covers and the intended outcome.

## Preconditions / access

Credentials, dashboards, and permissions needed. (Secrets are server-side only.)

## Detection

Signals that indicate this situation — alerts, Sentry issues, metrics
(`calls_failed_total`, `webhook_processing_latency`, `celery_queue_depth`, …), traces.

## Diagnosis

Steps to confirm root cause. Use OpenTelemetry trace IDs (request/org/job/candidate/call/
Celery-task) to follow the chain UI → API → DB → Redis → Celery → Hunar/Apollo → webhook.

## Resolution

Ordered, reversible steps. Note any consequential action (data change, replay, retry) and
the audit it produces.

## Verification

How to confirm the issue is resolved (state, metrics, a test call in sandbox where safe).

## Rollback / recovery

How to undo if resolution makes things worse.

## Follow-up

Post-incident notes, ADRs to write, doc updates, preventive work.
