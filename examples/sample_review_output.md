## PR Review — https://github.com/example/app/pull/88

### Summary
This PR introduces parameterized queries to fix an SQL injection vulnerability, which is a critical improvement. However, the password comparison still uses a deprecated hashing algorithm and the new auth helper is missing unit tests for the failure path. Request changes before merge.

### Findings (3 total)

### 1. 🟠 `HIGH` — Weak password hashing algorithm (MD5)
**Category:** Security
**File:** `src/auth/helpers.py` (lines 24–24)

`hashlib.md5` is cryptographically broken and should not be used for password hashing. An attacker with the hash can brute-force the plaintext quickly using GPU-accelerated rainbow tables.

**Suggestion:** Replace with `bcrypt`, `argon2-cffi`, or at minimum `hashlib.sha256` with a random per-user salt stored alongside the hash.

---

### 2. 🟡 `MEDIUM` — Resource leak: DB connection not closed on exception
**Category:** Bug
**File:** `src/auth/db.py` (lines 41–55)

`get_connection()` is called but the connection object is never closed in the `except` block. If the query raises, the connection leaks and will exhaust the connection pool under load.

**Suggestion:** Use a `try/finally` block or a context manager (`with get_connection() as conn:`) to guarantee the connection is closed.

---

### 3. 🔵 `LOW` — No test for failed authentication path
**Category:** Test Coverage
**File:** `tests/test_auth.py` (lines 1–30)

`authenticate_user` is tested for the happy path (valid credentials) but there is no test for wrong password, unknown user, or DB error. The failure path contains the resource leak noted above.

**Suggestion:** Add `test_authenticate_user_wrong_password`, `test_authenticate_user_unknown_user`, and `test_authenticate_user_db_error` test cases.
