# Dev log — Implementation 011: agent registry, per-agent identity, red-team arena

**Date:** 2026-08-21
**Domain:** Implementation
**Fulfills:** SOL-018 (turn two declared-but-stretched fleet components into real ones)
**Verification:** offline suite **347 passed / 8 skipped** (was 290/6; +57 tests); registry endpoint and capability denials exercised locally; red-team arena run live against the production armor screener.

## Why this cycle existed

A compliance review of our own claims found two fleet components were asserted
rather than built: the "agent registry" was a *prompt* registry, and "agent
identity" was a single service-level account. Both are now real.

## Agent registry derived from the running system

`core/fleet/` builds the catalog from live configuration — per agent: model id,
stage bindings, capability scope, identity principal, bound prompt variant and
a content hash of the effective definition, so a version change is detectable.
`GET /fleet/registry` (bearer auth) returns 11 agents and 14 principals with a
fleet summary; the operations console renders it as a Fleet panel.

The registry immediately paid for itself: it reported agent #7 (schema repair)
as `deterministic` while the README claimed Flash-Lite. The code is a bounded
retry loop that re-invokes the caller's own evaluator and holds no model and no
capability — the registry was right and the documentation was stretched. README
now reads "ten model-backed agents and one deterministic repair component", and
states that the table is verifiable against the endpoint. Derived values are
never adjusted to match prose.

## Per-agent identity, enforced

Each agent maps to a principal with a least-privilege capability set, checked at
five call sites before any network call, with the principal recorded in
telemetry spans and the provenance ledger. Proven by tests that revoke a
capability at runtime: revoking `sis.write` completes the batch with zero SIS
writes and a denial per student in the audit trail; revoking `llm.invoke`
isolates every submission with a `CapabilityDenied` span.

Cloud side, deliberately narrow (`docs/architecture/agent-identity.md`): a
separate GCP account per agent would be cosmetic while all agents share one
process, so only the principal whose blast radius leaves the system gets one —
the SIS writer. Created `gradesync-sis-writer` with `roles/datastore.user`; the
runtime account may only mint tokens for it
(`roles/iam.serviceAccountTokenCreator`), which makes every elevation an
auditable `GenerateAccessToken` in Cloud Audit Logs. Impersonation is wired into
the deploy and falls back to the ambient identity when disabled.

## Red-team arena

`scripts/run_red_team.py` renders attack payloads onto generated exam pages and
scores them against the real armor screener with clean twins, measuring catch
rate, false positives and whether the grade moved. Verified live against
production Vertex. The Gemma-backed payload generator is implemented behind a
provider seam with its live test present and skipping: enabling Gemma billing
was declined for now, so the measured campaign uses scripted payloads and is
labelled as such — the integration is unexercised by choice, not broken.
