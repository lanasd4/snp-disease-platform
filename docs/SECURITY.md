# Security

Review date: 2026-11-10. Tools: manual code review, `bandit`, `pip-audit`, `tests/test_security.py`.

## Configuration (no secrets in the code)

| Setting | Purpose | Default |
|---|---|---|
| `SNP_ADMIN_USERNAME` / `SNP_ADMIN_PASSWORD` | Creates the first admin, only when the database has no active admin | not set: no admin is created |
| `SNP_ALLOW_REGISTRATION` | Public self-registration (always role `user`) | `true` |
| `SNP_DATABASE_PATH` | Alternative SQLite file | `database/snp_platform.db` |

Read from environment variables, then Streamlit secrets (`core/settings.py`).
Never commit `.streamlit/secrets.toml`.

## Controls

| Area | Control |
|---|---|
| Credentials | No default account or password in code, docs or the published database |
| Published database | Ships without `UserAccount`, `UserSearchHistory`, `AdminActionLog`, `LoginThrottle` rows |
| Password storage | PBKDF2-HMAC-SHA256, 16-byte random salt, 600,000 iterations; older hashes upgraded on next login |
| Password rules | 8–128 characters; admin resets force a change at next login |
| Usernames | `^[A-Za-z0-9._-]{3,32}$`, so no markup or links can be injected through a name |
| Brute force | 5 failed attempts lock a username for 5 minutes; unknown names take the same time as real ones |
| Authorization | Admin page hidden and refused for non-admins; self-registration can never create an admin |
| SQL | Parameterized queries; table names only from fixed lists |
| HTML (XSS) | Every dynamic value inside `unsafe_allow_html` blocks is HTML-escaped |
| Uploads (admin) | Filename reduced to `[A-Za-z0-9._-]`, fixed upload folder, 25 MB limit; registry paths cannot leave the project folder |
| Subprocess | Only `ollama pull <validated model name>`, argument list, no shell |
| Server | `.streamlit/config.toml`: tracebacks hidden from visitors, XSRF protection on, headless |
| Dependencies | `requirements.txt` lower bounds include the fixes reported by `pip-audit` |

## Known limits

- SQLite on free hosting is not persistent: accounts and admin changes are lost on restart.
  Keep the public deployment read-mostly; do data management locally.
- Older git history still contains the previous default password and account hashes.
  Publish from a fresh repository (or rewritten history), not from the old history.
- The AI explanation page needs a local Ollama server and is unavailable on hosting.

## Checks

```bash
python -m pytest tests/test_security.py
python -m bandit -r app core pipeline -q
python -m pip_audit -r requirements.txt
```
