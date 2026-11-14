# Platform administration

The verified account listed in `platform-admins.json` can access `/admin/*`. `PLATFORM_ADMIN_EMAILS` overrides the list; an explicitly empty override disables platform administrators. This is independent of teacher workspace and support roles. No role can be self-assigned through the API.

Features:
- Search users with pagination. Responses contain identity and status only, never password hashes, reset tokens or verification codes.
- Block/unblock users, revoke existing sessions through token versions. Administrators cannot block themselves or other deployment-designated administrators. Unblocked users must sign in again.
- List schools/groups, assign verified active accounts as teachers or school administrators, archive/restore groups. Assigning a school group adds its new teacher to school staff. Existing work is retained. Group pupils cannot become teachers of that same group.
- Daily analysis quotas (UTC), global enable/disable for new analysis, mentor and AI import requests. In-progress requests finish. Mentor/import frequency limits remain separate. AI usage currently includes recorded analysis calls only; money cost is not estimated.
- Health, Judge0 configuration state, latest verified uploaded backup, latest 100 safe server error records in the current process, and 50 latest administrative actions.

Backup workflow now runs daily unless `BACKUPS_ENABLED` is explicitly `false`; manual dispatch always runs. It uses the active `DATABASE_URL` secret or the previously verified migration connection as fallback. Only after encrypted upload and restore verification succeed does it record a successful backup in `admin_operations`. An absent record is displayed as unknown, and a copy older than 24h is flagged as stale. A missing/invalid secret fails the workflow rather than showing success. No credentials are returned to the frontend.

All mutations require platform admin authentication and are recorded with actor, target, action and time. No bulk-delete or password-view action is exposed in the panel.
