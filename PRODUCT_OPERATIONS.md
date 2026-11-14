# Classroom release: operating requirements

## Delivered in this release
- Owner-only removal/restoration of group membership (work is retained), invitation links and code rotation.
- UTC deadlines, late-submission policy, teacher-controlled hints and solution examples.
- Scores 0–100, late labels and UTF-8 CSV export for Excel. CSV cells are protected against spreadsheet formula injection.
- Account-scoped local autosave plus explicit cloud save/restore with revision conflict detection. Cloud drafts are private to their author.
- School administrator, single-use teacher invitations (48 hours), group reassignment, staff revocation and a shared assignment library. An administrator must transfer their school before deleting their account. School group owners must transfer school groups before deletion.
- Contextual AI advice using the current task/code and two prior submissions. No hidden tests or reference solution are included in the prompt. Advice is not an execution verdict.
- Imported drafts reject conflicting outputs for identical inputs. Teacher-only reference code can be run against proposed tests in the browser. This checks code/test agreement, not semantic correctness of the task; teacher review remains necessary.
- Judge0 integration: server-side execution during both test preview and submission; client reports cannot override a server verdict. Hidden case inputs, outputs and diagnostics are redacted from learner APIs. No automatic acceptance: teacher review remains required.

## Judge0: free software, separate infrastructure
Judge0 CE can be self-hosted without a paid API plan. Hosting is a separate resource; the current Render web service does not supply the privileged sandbox/cgroup environment required by Judge0. Do not run pupil code as a subprocess on the API host.

1. Obtain a dedicated Linux VM with virtualization/cgroups and Docker supported by the current stable Judge0 CE release. Use the official maintained release and its installation/security instructions: https://github.com/judge0/judge0 . Do not use an unmaintained image.
2. Place Judge0 behind HTTPS and authentication. Keep Redis/Postgres private and unavailable from the internet. Permit access only from the application network/proxy. Never expose the raw worker.
3. Disable network access for submissions in Judge0 configuration and its worker network/firewall, including access to cloud metadata and internal services. API flags alone are insufficient. Set server-side CPU, wall-time, process, memory and output limits; disable caller overrides that loosen them.
4. Inspect `/languages` on YOUR instance and set matching language IDs. Defaults 71/63 correspond to Python and JavaScript on standard Judge0 installations; versions may differ.
5. Configure protected backend environment variables: `JUDGE0_URL=https://...`, `JUDGE0_AUTH_TOKEN=...`, `JUDGE0_PYTHON_ID=...`, `JUDGE0_JAVASCRIPT_ID=...`. Set `JUDGE0_ENABLED=true` only after the following checks pass.
6. Validate correct/incorrect code, syntax errors, infinite loops, large output, memory exhaustion, filesystem isolation and blocked outbound network. Use disposable tasks, never live learner data for this test.
7. Enable server checking in each assignment's settings. Server mode cannot be disabled later (to avoid exposing hidden tests during an outage). Previously public tests cannot retroactively become secret.

Server unavailability produces an explicit error and never silently falls back to a trusted browser verdict. This release does NOT provision or enable Judge0 automatically. Client cancellation stops waiting; already queued Judge0 jobs remain bounded by server limits.

## Backups and restoration
Existing `scripts/backup_database.py` creates encrypted consistent snapshots and restores only into a NEW offline file. Run with the same schema version as the application. Keep `BACKUP_ENCRYPTION_KEY` in a secret manager separately from backups.

Schedule daily backups on a persistent job host; write outside the repository; upload encrypted snapshots to private object storage; keep 30 daily copies. Alert on failed or older-than-24-hour snapshots. Once per month restore to an isolated database, verify row counts/integrity and exercise sign-in and group access using disposable accounts. Do not overwrite production to test restoration.

This repository does not configure an external scheduler or private storage. A script existing is NOT evidence of scheduled backups or successful production restoration.

## Monitoring / release gate
The existing `/health` and Prometheus `/metrics` endpoints support external uptime checks. Configure alerts for unavailability, server errors and latency. Never include code, email, credentials or verification tokens in error telemetry. Set up a real support inbox before advertising support response times.

Before calling this a production-ready school service: deploy and test Judge0 isolation, configure and drill backups, configure alerts and support handling, perform a load test at the expected class size and test real RU/UZ/mobile workflows on school Wi-Fi. No uptime or universal-code compatibility guarantee is made by these changes.
