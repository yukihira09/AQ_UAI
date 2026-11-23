# WP5 protected directory API

WP5 supplies the backend for the WP6 administration interface. The deployed browser interface and the MDL, QTA, and CRT APIs are separate work.

## Browser requests

- Use the same configured origin for the admin page and its API. The loopback convention is `http://admin.localhost:8000`, with the browser demo on `http://localhost:8000`.
- Send the existing session cookie with requests. The browser manages the host-only, HTTP-only cookie. Use relative URLs and `credentials: "same-origin"`. The current session endpoint remains `GET /api/v1/auth/me`.
- Every directory write needs the exact configured `Origin` and one `X-CSRF-Token` header. CSRF protection blocks writes induced by another website using the signed-in browser. The browser supplies `Origin`. Read `csrf_token` from `/auth/me` and keep it in memory. Refresh it after a new sign-in. A session requiring a password change can use `/auth/me`, change its password, and sign out. The password change revokes that session, so sign in again before loading directory data.
- All responses on these routes include `Cache-Control: no-store` and a server-generated `X-Request-ID`. Include the request ID when reporting a failure. Timestamps are timezone-aware ISO 8601 strings, and IDs are UUID strings.

## Endpoint inventory

All paths below are relative to `/api/v1`. Every operation requires an unrestricted authenticated session. The table states the additional permission. `GLOBAL` covers the actor's institution and `UNIT` is the exact unit carried by the relevant grant. The actor's primary unit grants no permission.

| Method and path | Permission | JSON input | Success |
| --- | --- | --- | --- |
| `GET /users` | `directory.read` in scope | — | 200 page of users |
| `GET /users/{user_id}` | `directory.read` in scope | — | 200 user |
| `POST /users` | GLOBAL `directory.manage` | `primary_unit_id`, `username`, `display_name`, `code_type`, `institutional_code`, optional `temporary_password` | 201 user |
| `PATCH /users/{user_id}/profile` | In-scope `directory.read` and `directory.profile.update` | `display_name` | 200 user |
| `PATCH /users/{user_id}/identity` | GLOBAL `directory.manage` and target visibility | One or more of `username`, `code_type`, `institutional_code` | 200 user |
| `POST /users/{user_id}/activate` | GLOBAL `directory.manage` and target visibility | Optional body with `temporary_password` for initial provisioning | 200 user |
| `POST /users/{user_id}/disable` | GLOBAL `directory.manage` and target visibility | — | 200 user |
| `POST /users/{user_id}/transfer` | GLOBAL `directory.manage` and target visibility | Destination `primary_unit_id` | 200 user |
| `GET /units` | `directory.read` in scope | — | 200 page of units |
| `GET /units/{unit_id}` | `directory.read` in scope | — | 200 unit |
| `POST /units` | GLOBAL `directory.manage` | `code`, `name` | 201 unit |
| `PATCH /units/{unit_id}` | GLOBAL `directory.manage` and target visibility | `code`, `name`, or both | 200 unit |
| `POST /units/{unit_id}/activate` | GLOBAL `directory.manage` and target visibility | — | 200 unit |
| `POST /units/{unit_id}/deactivate` | GLOBAL `directory.manage` and target visibility | — | 200 unit |
| `GET /groups` | GLOBAL `directory.read` | — | 200 page of groups |
| `GET /groups/{group_id}` | GLOBAL `directory.read` | — | 200 group |
| `POST /groups` | Group management permission for submitted `kind` | `code`, `name`, `kind` | 201 group |
| `PATCH /groups/{group_id}` | Group management permission and target visibility | `name` | 200 group |
| `POST /groups/{group_id}/activate` | Group management permission and target visibility | — | 200 group |
| `POST /groups/{group_id}/deactivate` | Group management permission and target visibility | — | 200 group |
| `GET /groups/{group_id}/members` | GLOBAL `directory.read` | — | 200 page of members |
| `PUT /groups/{group_id}/members/{user_id}` | Group management permission and visibility of both records | — | 200 member |
| `DELETE /groups/{group_id}/members/{user_id}` | Group management permission and visibility of both records | — | 204 |
| `GET /roles` | GLOBAL `authorization.manage` | — | 200 page of roles |
| `GET /users/{user_id}/role-assignments` | GLOBAL `authorization.manage` | — | 200 page of direct assignments |
| `POST /users/{user_id}/role-assignments` | GLOBAL `authorization.manage` | `role_code`, `scope`, optional `unit_id` | 201 assignment |
| `DELETE /users/{user_id}/role-assignments/{grant_id}` | GLOBAL `authorization.manage` | — | 204 |
| `GET /groups/{group_id}/role-assignments` | GLOBAL `authorization.manage` | — | 200 page of group assignments |
| `POST /groups/{group_id}/role-assignments` | GLOBAL `authorization.manage` | `role_code`, `scope`, optional `unit_id` | 201 assignment |
| `DELETE /groups/{group_id}/role-assignments/{grant_id}` | GLOBAL `authorization.manage` | — | 204 |
| `GET /audit-events` | GLOBAL `audit.read` | — | 200 page of audit events |
| `GET /audit-events/{event_id}` | GLOBAL `audit.read` | — | 200 audit event |
| `GET /directory/capabilities` | Authenticated session only | — | 200 capabilities |

Group management requires GLOBAL `directory.manage` for `SYSTEM` and `AI_SPECIALIST`, and GLOBAL `authorization.manage` for `AUTHORIZATION`. Existing group and membership operations use the stored kind. Directory target visibility uses `directory.read`. Assignment routes use `authorization.manage` on the subject's institution. Audit routes use `audit.read` on the event's institution.

Send `Content-Type: application/json` when sending JSON. A dash on a mutation permits an absent body or an empty object. A `204` has an empty response body. Input models reject unlisted fields. Identity and unit patches require at least one non-null field. Names are trimmed and limited to 255 characters, codes to 64. They must be nonempty and free of control characters. Usernames use WP3 canonicalization. Temporary passwords use WP3's 12–128 character validation and Argon2id hashing. Passwords, hashes, session data, and throttle data are excluded from directory responses.

## Response records and lists

| Record | Fields |
| --- | --- |
| User | `id`, `institution_id`, `primary_unit_id`, `username`, `display_name`, `code_type` (`STAFF` or `STUDENT`), `institutional_code`, `state` (`PENDING`, `ACTIVE`, or `DISABLED`), `created_at`, `updated_at` |
| Unit | `id`, `institution_id`, `code`, `name`, `active` |
| Group | Unit fields plus `kind` (`SYSTEM`, `AUTHORIZATION`, or `AI_SPECIALIST`), `created_at`, `updated_at` |
| Member | `group_id`, `user` (user record), `active`, `created_at`, `updated_at` |
| Assignment | `id`, `institution_id`, `subject` (`USER` or `GROUP`), `subject_id`, `role_code`, `scope` (`GLOBAL` or `UNIT`), nullable `unit_id` |
| Role | `code`, `permissions` (list of permission codes) |
| Audit event | `id`, `institution_id`, nullable `actor_id`, `action`, `target_type`, nullable `target_id`, `outcome` (`SUCCESS` or `FAILURE`), `occurred_at`, `request_id`, `changes` (object) |
| Capabilities | `institution_id` and `permissions` keyed by the five permission codes, each with `institution_wide` and `unit_ids` |

List responses have the shape `{"items": [], "total": 0, "limit": 25, "offset": 0}`. Set `limit` from 1–100 and `offset` from 0–100000. The database filters rows by permission, institution, and the parameters below before counting or applying pagination. A count and a page are separate queries using the same filters. Concurrent writes can affect the next page or the count. Ordering includes a unique tie-breaker.

| List | Query parameters in addition to pagination | Order |
| --- | --- | --- |
| Users | `q` (name, username, or institutional code), `primary_unit_id`, `state`, `code_type` | Username, UUID |
| Units | `q` (code or name), `active` | Code, UUID |
| Groups | `q` (code or name), `kind`, `active` | Code, UUID |
| Members | `q` (user name, username, or institutional code), `active` (defaults to true, use false for removed memberships) | Username, UUID |
| Roles | `q` (role code) | Role code |
| Assignments | `role_code`, `scope`, `unit_id` | Role code, UUID |
| Audit | `action`, `actor_id`, `target_type`, `target_id`, `outcome`, `from_time` (inclusive), `to_time` (exclusive) | Newest event time, then UUID descending |

`q` uses a literal case-insensitive substring of up to 128 characters. Unit-scoped directory reads include only active granted units. Global directory readers may see inactive units and historical accounts. Capabilities express each permission's scopes independently. For example, `"directory.read": {"institution_wide": true, "unit_ids": []}` can coexist with `"directory.profile.update": {"institution_wide": false, "unit_ids": ["00000000-0000-4000-8000-000000000010"]}`. The server rechecks permissions on every operation.

| HTTP status and code | Client handling |
| --- | --- |
| `401 AUTH_REQUIRED` | Sign in again when the session is missing, expired, or revoked. |
| `403 FORBIDDEN` | Check password-change state, permission, scope, Origin, and CSRF. A visible record may be outside a write permission's scope. |
| `404 NOT_FOUND` | Show the same message for missing records and records outside visibility. |
| `409 CONFLICT` | Refresh data. Common causes include duplicate identifiers or assignments, a conflicting state, or the last-administrator rule. |
| `422 VALIDATION_FAILED` | Check the submitted fields, UUIDs, or assignment requirements. |
| `500 DATABASE_ERROR` or `500 INTERNAL_ERROR` | Report the request ID. The database transaction rolls back on a failed write. |

An example error body is `{"code":"NOT_FOUND","message":"The resource was not found.","request_id":"00000000-0000-4000-8000-000000000001"}`. The request ID in the header matches the body.

## Account lifecycle

Create a user in an active unit. If the temporary password is omitted, the account is `PENDING` and cannot sign in. Provision its initial credential later through activation. Providing the temporary password at creation makes the account `ACTIVE` with the password-change requirement. The administrator communicates that password separately. Creation assigns no roles.

Activation requires the user's primary unit to be active. A disabled account with existing credentials can be reactivated with an empty body and retains its password and password-change flag. Sending a password for an account that already has credentials returns `409`. An account with no credentials needs a temporary password, even if it was disabled first. Use the WP3 operator recovery command for an active account that already has credentials. Repeating an account-state command after it has taken effect returns `409`.

Disablement preserves the user's UUID, credentials, memberships, and grants and revokes all sessions. A username change also revokes all sessions. A transfer validates the persisted source and requires an active destination in the same institution. It preserves explicit grant scopes, memberships, and the user's identity. A move to the current unit returns `409`. Deactivating a unit returns `409` while it has active users or any user or group assignments scoped to it, including assignments that currently confer no authority.

## Groups and assignments

New units and groups start active. Group `code`, `kind`, and institution are fixed at creation. Deactivating a group removes any effective group-derived authority. The retained links become eligible again after reactivation according to current policy. Repeating unit or group state changes returns `409`.

Use `PUT` to add or reactivate a member in an active group. Use `DELETE` to mark the link inactive, including in an inactive group. Repeated adds of an active link return its current record. Repeated removals of a missing or inactive link return `204` if both identifiers are visible and the operation is permitted. Unchanged membership calls create no extra audit record. Group member listings show stored membership state, so an inactive group can retain active membership rows. The reusable lookup uses the existing one-row-per-pair key. Future QTA eligibility can filter active memberships and active groups alongside its own rules.

An assignment ties a role to one user or group and one scope. `FOUNDATION_ADMIN` is direct GLOBAL only. `DIRECTORY_READER` is GLOBAL or UNIT. `UNIT_DIRECTORY_MANAGER` is UNIT only. Omit `unit_id` for GLOBAL. UNIT requires an active in-institution unit. A group must be active and of kind `AUTHORIZATION` to receive an assignment. Direct assignments may be prepared for pending or disabled accounts and become effective only when the account is eligible. Delete an assignment using the returned UUID under the original subject's path. Its audit history remains available. An attempt to delete another subject's assignment returns `404`.

An institution must retain an active administrator with a credential record and a direct GLOBAL `FOUNDATION_ADMIN` assignment. Temporary credentials count because their holder can complete the password-change flow. Disablement and administrator grant removal check the proposed state before committing, including when the caller changes their own account. A change that would leave no usable administrator returns `409`.

## Audits and transaction behavior

The API checks the session, acquires the institution lock, acquires the affected account locks when required, and rechecks the actor and target before writing. A lock coordinates concurrent database transactions. Authority changes use an exclusive institution lock, while profile and descriptive updates can share it. Membership preselects a visible group's immutable kind only to choose which WP4 operation permission can coordinate the target account. An unavailable hint ends that attempt with a safe absence response for a caller allowed to manage groups. State and authorization are checked again under the locks. A successful state change commits with its event. A database failure during the audit insert rolls back credentials, session revocations, or other associated changes.

| Actions | Allowed change data |
| --- | --- |
| `user.created` | `primary_unit_id`, `state` |
| `user.profile_updated`, `group.updated` | Previous and current names as `before` and `after` |
| `user.identity_updated` | `before` and `after` objects with `username`, `code_type`, `institutional_code` |
| `user.transferred` | Previous and current primary unit UUIDs as `before` and `after` |
| `user.state_changed` | Previous and current account states as `before` and `after` |
| `unit.created` | `code`, `name` |
| `unit.updated` | `before` and `after` objects with `code`, `name` |
| `unit.state_changed`, `group.state_changed` | Previous and current active booleans as `before` and `after` |
| `group.created` | `code`, `name`, `kind` |
| `membership.state_changed` | `user_id`, `before` (null on a new link), `after` |
| `role_assignment.created`, `role_assignment.removed` | `subject_type`, `subject_id`, `role_code`, `scope`, nullable `unit_id` |

The membership event uses `target_type: "group_membership"` and the group UUID as `target_id`. Assignment events use the assignment UUID as `target_id`. The audit reader projects allowlisted fields by action. Older two-state membership payloads can be read without inventing a user UUID. Operator events may have a null actor. Events without an institution are excluded. New event times use the database clock at insertion.

## WP6 examples

After sign-in and any required password change, load `GET /api/v1/directory/capabilities` and display controls using the corresponding permission and scope. For a new pending user, the browser can send:

```js
const me = await fetch("/api/v1/auth/me", { credentials: "same-origin" }).then(r => r.json());
const created = await fetch("/api/v1/users", {
  method: "POST",
  credentials: "same-origin",
  headers: { "Content-Type": "application/json", "X-CSRF-Token": me.csrf_token },
  body: JSON.stringify({
    primary_unit_id: "00000000-0000-4000-8000-000000000010",
    username: "demo.researcher",
    display_name: "Demo Researcher",
    code_type: "STAFF",
    institutional_code: "DEMO-017"
  })
});
```

Use an existing unit UUID. A `201` response includes the new user's UUID. Use it in `POST /api/v1/users/{user_id}/activate` with `{"temporary_password":"demo-only-passphrase-17"}` for a synthetic activation test. Use the same Origin and CSRF handling on every write.

Add the user to an existing group with `PUT /api/v1/groups/{group_id}/members/{user_id}` and remove them with `DELETE` on that path. To grant exact-unit reading, send `{"role_code":"DIRECTORY_READER","scope":"UNIT","unit_id":"00000000-0000-4000-8000-000000000010"}` to `POST /api/v1/users/{user_id}/role-assignments`. Revoke the resulting assignment by appending its `id` to that path and sending `DELETE`. Query `GET /api/v1/audit-events?action=membership.state_changed&target_id={group_id}&limit=25` to see changes for both new and reactivated memberships.

## Database access and rollout

Runtime grants allow only the columns used for directory writes. Reads required by earlier packages and runtime audit appends continue.

| Table | Additional INSERT columns | Additional UPDATE columns | DELETE |
| --- | --- | --- | --- |
| `units` | `institution_id`, `code`, `name` | `code`, `name`, `active` | — |
| `users` | `institution_id`, `primary_unit_id`, `username`, `display_name`, `code_type`, `institutional_code`, `state` | `primary_unit_id`, `username`, `display_name`, `code_type`, `institutional_code`, `state`, `updated_at` | — |
| `account_groups` | `institution_id`, `code`, `name`, `kind` | `name`, `active`, `updated_at` | — |
| `group_memberships` | `institution_id`, `group_id`, `user_id`, `active` | `active`, `updated_at` | — |
| `user_role_assignments` | `institution_id`, `user_id`, `role_code`, `scope`, `unit_id` | — | Yes |
| `group_role_assignments` | `institution_id`, `group_id`, `role_code`, `scope`, `unit_id` | — | Yes |

The WP3 credential INSERT grant covers initial credentials. PostgreSQL enforces column grants, key and reference constraints, and runtime audit immutability. The API enforces the actor's scopes, valid active-state transitions, last-administrator protection, and the requirement that writes include a matching audit event. A compromised runtime connection can issue SQL within its grants, including assignment changes and directory writes without matching audit events. The authenticated service is the policy boundary.

For an approved rollout, run the current provisioning and migration procedure for the target database to reconcile the WP5 grants. The Alembic head remains `0002_identity_foundation`, so an installation with outdated runtime grants can still report ready. Verify a directory write after the rollout as well as readiness. [Existing rollout procedure](wp3-operations.md#rollout-after-approval)
