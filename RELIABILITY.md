# Reliability and support

## Available
- Main editor: per-account local draft snapshots, five versions, explicit restore; no sample code is injected on page load. Snapshots stay in this browser. The newest version is updated during typing; previous checkpoints are retained every 30 seconds. Storage failures are shown. Classroom drafts also support explicit cloud save/restore with revision checks.
- Support: sidebar → Support. Tickets and staff replies are stored in the application database; users see only their tickets. No email is sent. No code, history, token or password is collected automatically. Optional diagnostics include only error counts, locale and online/offline state. Staff see the latest 100 tickets.
- The verified account in `support-admins.json` is the support administrator. `SUPPORT_ADMIN_EMAILS` overrides this deployment-controlled list (comma-separated); an empty override disables all staff. Users cannot grant themselves staff access. Passwords are not configured here.
- Server HTTP 5xx errors emit structured records to hosting logs with a random request ID, route template, status, exception class and duration. Request bodies, query strings, account identifiers and exception messages are excluded. A server failure response contains a reference ID. This is error recording, not external alert delivery.
- Password recovery is available on sign-in and in Settings → Access and data. Account deletion is in Settings → Account management. School/group ownership must be transferred first. Tickets and cloud drafts are deleted with the account; local drafts for that account are cleared after successful deletion.

## Daily backup activation — still needs repository administrator access
Workflow: `.github/workflows/backup.yml`, daily at 01:15 UTC. Each run creates an encrypted snapshot, restores a fresh offline copy and checks SQLite integrity and foreign keys. Encrypted artifacts are retained 30 days. The encryption key must be stored separately from the artifacts.

As checked on 2026-11-14, recent runs were **skipped**. The current integration gets HTTP 403 when reading or modifying Actions variables/secrets, so activation could not be verified or completed.

In GitHub → repository Settings → Secrets and variables → Actions:
1. Set repository variable `BACKUPS_ENABLED` to `true`.
2. Set secret `DATABASE_URL` to the existing backend database connection string (or the Turso URL and token if using Turso). Never put these in an issue, chat or source code.
3. Generate a Fernet key in a trusted local terminal: `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`. Save it in a password manager and secret `BACKUP_ENCRYPTION_KEY`.
4. Actions → Encrypted database backup → Run workflow. Verify the run succeeds and the encrypted artifact is present. This is the first evidence that production backups actually work.
5. Enable GitHub notifications for failed workflows. Configure an external uptime service against `/health` and a hosting log alert for `mentor.reliability` / `server_error`; these external alerts have not been provisioned by this release.

Local tests verify encrypted backup/restore of the current school/draft schema. This does not substitute for a successful production backup run. Keep access to backup artifacts restricted to repository operators. Periodically restore and test workflows on an isolated instance; never restore over the live database for a drill.
