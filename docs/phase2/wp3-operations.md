# WP3 local authentication and consolidated rollout

WP3 adds local authentication to the shared foundation. The demo stays at `http://localhost:8000`. The admin API is at `http://admin.localhost:8000/api/v1`. The admin origin serves a short placeholder at its root and exposes the API without serving the demo HTML or scripts. Keep both hostnames on loopback. Use your configured `WEB_HOST_PORT` if it differs.

## Authentication contract

| Request under `/api/v1/auth` | Inputs | Success |
|---|---|---|
| `POST /login` | Configured `Origin` and JSON `username`, `password` | `204` with a new session cookie |
| `GET /me` | Session cookie | `200` with `id`, `username`, `display_name`, `institution_id`, `primary_unit_id`, `state`, `must_change_password`, and `csrf_token` |
| `POST /change-password` | Origin, session cookie, `X-CSRF-Token`, and JSON `current_password`, `new_password` | `204`, revokes all sessions for the account and clears the cookie |
| `POST /logout` | Origin, session cookie, and `X-CSRF-Token` | `204`, revokes this session and clears the cookie |

All auth responses use `Cache-Control: no-store`. Invalid login credentials and invalid sessions return `401`, prohibited Origin, CSRF, and restricted-session operations return `403`, invalid request bodies return `422`, and throttled logins return `429`. The error body and response header carry the WP2 request ID. nginx rejects payloads over 8 KiB on the admin host before they reach FastAPI. FastAPI validates password lengths on either network path.

The session cookie is host-only, `HttpOnly`, and `SameSite=Lax`. HTTPS origins use `Secure`. The explicit HTTP exception applies to `admin.localhost` in development or test. A successful login generates 32 random bytes and stores only a SHA-256 digest. Sessions expire eight hours after issuance. The cookie replaces the previous browser cookie. A presented session belonging to the same account is revoked during re-login, while sessions on other devices remain until logout, expiry, credential change, or account invalidation. A presented session belonging to a different account is not revoked by the new account's login.

An active, provisioned identity can authenticate. `PENDING` and `DISABLED` identities receive the same generic credential failure as an invalid password. An active identity with a temporary password receives a restricted session that permits `/me`, password change, and logout. Future protected routes must use `require_authenticated_user` from the auth router. That dependency rejects restricted sessions. WP4 must add its own permission and organizational scope checks.

The client fetches `/me` after login and retains the CSRF token in memory. The token is an HMAC keyed by the high-entropy session secret and labeled for CSRF. It changes with session rotation. Submit it in `X-CSRF-Token` with the exact Origin on writes. Using the direct API port still requires the same Origin, session, and CSRF checks. Automated tests can explicitly send the allowed Origin. For example, use `curl --resolve admin.localhost:8000:127.0.0.1 http://admin.localhost:8000/api/v1/health` when the local resolver requires help. Keep application passwords and tokens out of shell history and URL arguments.

Use 12–128 characters for new passwords, with a passphrase or a password manager. Argon2id uses 64 MiB of memory, three iterations, one lane, a 16-byte salt, and a 32-byte hash. Usernames are trimmed and lowercased using WP1's ASCII format. Passwords are preserved exactly. Unknown users follow a dummy password verification path. Use application passwords distinct from PostgreSQL passwords. The operator checks the login it uses, and the application checks its own runtime login on a password change.

## Login protection and concurrency

Login requires the exact configured browser origin before checking PostgreSQL. Within one write transaction the service acquires the login and address advisory locks in sorted order. An advisory lock is a PostgreSQL transaction lock on an agreed key. It does not require permission to update the user row. The service reads both counters, locates the person, locks that account, then reads fresh account and credential data before verifying the password and creating a session. Account writes and audit append commit together. On a rejected login the service commits its failure audit and applicable counters before returning the error.

Throttling permits five failures for a normalized username and 30 failures for a client address per fixed 15-minute UTC window. Later attempts in that bucket receive a generic `429`. An invalid normalized username uses a separate invalid-input bucket. A successful login preserves both failure counts until the window rolls over. Identifiers and addresses use keyed digests and only those digests are stored. Each login removes at most 100 buckets older than one day, skipping rows another transaction is operating on.

The local default ignores all forwarding headers and uses the direct socket peer. Consequently nginx-proxied requests can share its address bucket, while the username limit still separates accounts. For per-client throttling, set `AQ_UAI_AUTH_TRUSTED_PROXY_IP` to the exact private, non-loopback nginx socket peer only if the address is stable in your network. nginx overwrites `X-Forwarded-For` with one address. The application accepts one parseable address only from that configured peer. Keep Uvicorn's `--no-proxy-headers` flag so the application sees the actual peer. Leave the setting empty on the ordinary Compose setup or when the proxy changes IPs.

WP5 must acquire `lock_account(db, user_id)` in the same write transaction before changing account state or login identity fields. To disable a user, acquire the lock, update state, revoke all sessions with `revoke_user_sessions`, and append the typed audit event before commit. Never take throttle locks after an account lock. If a future operation locks several accounts, take them in a consistent order. Requests started after a revocation commits must reject the old session. This lock protocol uses PostgreSQL read-committed transactions. The current service serializes password verification for an account while checking fresh state.

Operator bootstrap and reset audit events have no authenticated actor. Password-change and operator-reset events record a count of revoked sessions. Sign-in, failed sign-in, and logout events carry no credential or session-token fields. WP5 must decide how membership events identify both members of the `(group_id, user_id)` association before relying on those events for directory history.

## Database access

| Responsibility | Bootstrap owner | Schema owner / operator | API runtime |
|---|---|---|---|
| Provision managed roles and transfer legacy objects | Yes | No | No |
| Own and migrate application tables | Maintenance authority | Yes | No |
| Read metadata, revision, directory, grants, and catalog | Yes | Yes | Yes |
| Write identities, memberships, grants, and catalog | Yes | Yes | No |
| Read credentials and update hash, temporary flag, and timestamp | Yes | Yes | Yes |
| Read sessions, insert initialization fields, set revocation timestamps | Yes | Yes | Yes |
| Delete sessions or alter their expiry | Yes | Yes | No |
| Read and insert throttle buckets, update counts, clean up old buckets | Yes | Yes | Yes |
| Read and append audit rows | Yes | Yes | Yes |
| Change, delete, or truncate audit history | Maintenance authority | Maintenance authority | No |

WP3 uses the existing WP1 tables and revision. Provisioning and migration reapply WP3's grants. No application database password is shared across roles. Compose's API service receives only its runtime connection credentials and auth settings. Run PostgreSQL, migration, and API separately as documented. A Docker administrator remains privileged.

## Rollout after approval

For a **fresh installation**, create a private `.env` from `.env.example`, then run `bash scripts/dev-up.sh`. For a **Phase 1, WP1, or WP2 volume**, keep the original PostgreSQL database name, bootstrap username, and bootstrap password. Always use the original project and volume. Add or retain distinct `AQ_UAI_MIGRATION_PASSWORD` and `AQ_UAI_RUNTIME_PASSWORD` settings and add `AQ_UAI_AUTH_THROTTLE_KEY`. Generate each new secret independently, for example by redirecting `openssl rand -hex 32` to a private file created with `umask 077`. Set the throttle key to 64 hexadecimal characters. Keep `.env` private and out of Git. Compose derives the development Origin from `WEB_HOST_PORT`. Override `AQ_UAI_AUTH_ORIGIN` only for an explicit separately configured admin origin. Leave the local HTTP switch enabled only for the demo.

After configuring the values, follow the [backup-first transition](wp2-operations.md#existing-phase-1-or-wp1-installation). Verify the dump and, for valuable data, rehearse a restore on a separate instance. Keep the existing database running and stop the old API and web services. Run the provisioning job, then the migration job, before starting the rebuilt API and nginx. This one transition works whether the starting revision is Phase 1 or WP1 and whether WP2 privileges were ever installed.

Provisioning rolls back its own changes on failure. If a step fails, leave the API stopped, retain the backup and original volume, and resolve the reported role, schema, or connectivity issue before repeating it. If restoration is necessary, restore to a separate cluster and verify before switching. The deployment requires no database reset.

Run these only after the database is ready. Use an interactive terminal so application-password entry remains hidden.

```bash
docker compose --env-file .env -f infra/compose.yaml run --rm --no-deps migrate \
  python -m aq_uai_api.auth.operator bootstrap

docker compose --env-file .env -f infra/compose.yaml run --rm --no-deps migrate \
  python -m aq_uai_api.auth.operator reset-password
```

Bootstrap prompts for the institution and primary unit codes and names, the admin username and display name, and the staff code. It creates the credential and direct global admin grant atomically. It requires an empty institution directory and rejects repeated bootstrap. If an institution already exists, review the directory and existing administrator before proceeding. Reset prompts for an existing active username, assigns a temporary password, preserves the account's directory and role data, and revokes all of its sessions. It cannot activate a disabled account.

After rollout, run `python3 scripts/phase1_smoke.py`. Check `/api/v1/auth/me` on the admin hostname for `401` without a cookie and on the demo hostname for `404`. Requesting `/shared/core.js` or `/index.html` on the admin hostname must return `404`. On a disposable Compose project with synthetic values, run `scripts/verify_wp2_compose.py` with `--live` to verify scoped container environments and both database logins. The WP3 report records standalone verification and any Docker blockers.
