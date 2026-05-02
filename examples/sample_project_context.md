# My Service — Project Context for PR Review

## Overview

A brief (1-3 sentence) description of what the project does and its main responsibilities.
Reviewers will use this to understand intent and skip irrelevant warnings.

## Tech Stack

- Language + runtime (e.g. Python 3.11, Node 20)
- Framework (e.g. FastAPI, Django, Express)
- Database + ORM (e.g. PostgreSQL + SQLAlchemy async)
- Caching / queuing (e.g. Redis, RabbitMQ)
- Auth mechanism (e.g. JWT HS256, OAuth2)

## Conventions

Document project-specific rules that would otherwise be flagged incorrectly:

- "All DB access goes through the repository layer — direct ORM calls in handlers are bugs."
- "Null checks: every function accepting a user-provided ID must validate before querying."
- "Secrets live in env vars only — no inline strings for keys or passwords."
- "Use context managers for sessions — never manually close."

## Review Instructions

Tell the reviewer what to prioritise or skip:

- "Flag any SQL built via string concatenation as critical."
- "N+1 queries (ORM calls inside loops) are high-severity performance bugs."
- "Every new public function needs a happy-path and an error-path test."
- "Do not flag missing docstrings — we do not require them."
- "Routes decorated with `@require_role` already enforce auth — do not flag missing checks there."

## Architecture Notes (optional)

Brief notes on modules reviewers should know about:

- `src/auth/` — handles all JWT issuance and validation; changes here need extra scrutiny.
- `src/repositories/` — the only place allowed to call the ORM directly.
- `tests/factories/` — use these factories in new tests instead of creating raw model instances.
