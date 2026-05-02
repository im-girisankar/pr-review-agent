# Acme API — Project Context for PR Review

## Overview

Acme API is a Python FastAPI service providing secure REST endpoints for user and billing management.
All authentication uses JWT tokens via the `auth_module`. Never flag missing auth checks in routes
decorated with `@require_role` — these are handled by middleware.

## Tech Stack

- Python 3.11, FastAPI, SQLAlchemy (async), PostgreSQL
- JWT-based authentication (HS256, 24h expiry)
- Redis for query cache (TTL 300s by default)
- pytest + factory_boy for testing

## Conventions

- All database queries must go through the repository layer (`src/repositories/`). Direct ORM calls in route handlers are bugs.
- Null checks: all public functions that accept user-provided IDs must validate against None before querying.
- Resource cleanup: always use context managers (`async with`) for DB sessions — never manually close.
- Secrets must live in environment variables. No inline strings for keys or passwords.

## Review Instructions

- Flag any SQL built via string concatenation as a critical security issue.
- Performance: treat any ORM query inside a loop as an N+1 bug.
- Test coverage: every new public function must have at least one happy-path and one error-path test.
- Do not flag missing docstrings — we don't require them.
