# Phase 2 local deployment note

**What this is:** a record of what is and is not known about the developer's local deployment and manual website testing of Phase 2. **Why:** the [WP7 report](wp7-report.md) says Docker Compose runtime checks were pending, while the developer has since reported local use; those two statements must not be silently merged. **Status of this note:** written during M0 from a verbal developer report; the developer must complete the pending fields.

## Developer-reported (not independently verified)

- Local deployment of the stack has been performed.
- Manual testing of the website has generally been successful.

These two statements are **developer-reported evidence**. No logs, commands, screenshots, dates, versions or test lists were provided or checked. No repository file or report records them, and no one re-ran the deployment for this note.

## Evidence categories (kept separate)

| Category | State | Source |
| --- | --- | --- |
| Automated tests on disposable infrastructure | 119 pytest + 13 browser/ops passed, as reported for WP7 | [WP7 report](wp7-report.md) (quoted, not re-run) |
| Docker Compose live run in a controlled/CI-style environment | **Pending** in WP7 (Docker socket denied). A later run is not documented in the repository | WP7 report |
| Developer local deployment | Developer-reported; details **pending documentation** | This note |
| Developer manual website testing | Developer-reported as generally successful; scenarios **pending documentation** | This note |
| Hosted GitHub Actions CI | **Unverified** | WP7 report |
| Formal Tech Lead / company acceptance | **None recorded** | [acceptance matrix](../acceptance-matrix.md) shows 0 of 33 accepted |

The developer's report does not close the Compose "pending" item in the WP7 report; it adds an informal data point. Do not describe Phase 2 as "live-verified" or "accepted" on this basis.

## Details to complete (pending documentation)

The developer should fill these in; none has been guessed here.

| Field | Value |
| --- | --- |
| Date(s) of deployment | Pending |
| Git commit deployed | Pending (repository HEAD at the time of M0 is `2c909e3`) |
| Fresh install or upgrade of an existing volume (backup taken?) | Pending |
| Exact commands used | Pending |
| Docker / Compose versions and host OS | Pending |
| Accounts and roles used for testing (no passwords) | Pending |
| Scenarios exercised (sign-in, directory CRUD, audit, demo module screens, restart) | Pending |
| Defects or surprises observed and their disposition | Pending |
| Whether the isolated disposable procedure in the WP7 report was followed | Pending |

## How to turn this into evidence

Follow the [handoff](phase2-handoff.md) and the disposable-project procedure in the [WP7 report](wp7-report.md#live-deployment-gate), record the fields above, keep secrets out of the note, and let a reviewer confirm. Only then update the WP7 status line; this note does not change it.
