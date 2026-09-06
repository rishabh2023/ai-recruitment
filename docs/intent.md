# Intent

## Who this is for

- **Recruiter** — creates and manages jobs, resolves/approves hiring workflows and stage
  criteria, imports or sources candidates, launches outreach and interviews, reviews
  evidence, moves candidates, makes pipeline decisions.
- **Hiring manager** — reviews jobs, workflows, and interview evidence; approves or rejects
  at the stages where their sign-off is required.
- **Organization admin / owner** — organization settings, hiring workflow templates,
  high-level metrics, user management.

## The problem

Recruiting teams need to run AI-driven candidate conversations at scale without turning
recruiters into AI-infrastructure operators. The bottleneck is not the ability to place a
voice call — Hunar already does that. The bottleneck is everything around it: defining how
a company hires, keeping candidate and pipeline state durable and auditable, enforcing when
and how candidates are contacted, carrying information across stages, capturing
evidence-backed decisions, and recovering cleanly when calls, webhooks, or integrations
fail.

This platform solves the **workflow**, and uses Hunar for the **conversation**.

## The two connected core journeys

1. **Existing-candidate interviewing** — the organization already has candidates (ATS,
   spreadsheet, prior sourcing). They are imported, may already carry known information, and
   may enter the workflow at a later stage. The platform runs the configured AI stages and
   captures evidence for review.

2. **People search & outreach** — the recruiter starts from a job, searches Apollo, selects
   candidates, and Hunar runs an outreach/screening conversation. Interested candidates are
   progressively enriched and can progress into interview stages. **Journey 2 naturally
   feeds Journey 1.**

Both journeys enter the **same configurable job workflow**. Candidates differ only in where
they enter it and how complete their profile is.

## The separate future module

- **Attendance / workforce operations** — a distinct module built only after the
  recruitment core (Journeys 1 and 2) is stable. It is preserved in the roadmap (Phase 6),
  not dropped, and not started early.

## Product promise

Recruiters manage **jobs, workflows, stages, candidates, evidence, and decisions** — not
Hunar agent IDs, prompts, queues, telephony carriers, Celery, Redis, or retry scheduling.
Those are infrastructure concerns the platform hides.

## Human approval

Consequential AI-generated configuration is always drafted, then reviewed/edited, then
approved by a human before it executes: JD interpretation, hiring workflows, rubrics, and
stage criteria. AI produces drafts, never authoritative hiring processes.

## Non-goals

- Not a generic ATS, generic workflow/BPMN engine, or microservice platform.
- Not a rebuild of Hunar's conversation, telephony, speech, or evaluation capabilities.
- Not a multi-vendor voice abstraction, deep-agent framework, or multi-agent system.
- No recruiter-visible catalog of per-language/per-skill agents.
- No UI control built around an unverified vendor capability.
- No sophisticated enterprise RBAC for V1 — simple role-based capabilities only.
- No call-recording controls unless Hunar documents that capability.
