# JiMeet staging

Source of truth: `CZH0919/JiMeet`, branch `staging`. This deployment uses a separate
`/srv/jimeet-staging` tree, Linux user `jimeetstage`, application database
`jimeet_staging`, and regression database `jimeet_staging_ci`. It never deploys
into `/srv/jiMeet` or a member's home directory.

## Access

The endpoint is `http://121.36.228.209/`. Nginx Basic authentication is disabled,
so users can open the website without the former `tester` browser prompt.
Protected API operations still require a website session and normal authorization.
Only synthetic test data is appropriate for this initial HTTP deployment.
After adding HTTPS, update the trusted origin and `STAGING_HTTPS=true`.

Inside the website, the Sprint 2 UI uses account/password login. Existing test
identities are `qa01` to `qa06`, `Tqa01`, `Tqa02` and `qaadmin`. Their generated
passwords are stored in `/etc/jimeet-staging/test-accounts.json` (root only).
The account field accepts the
short identity; the frontend appends `@tongji.edu.cn`. Teachers have the T prefix.
`qaadmin` has the business administrator flag only because it was explicitly seeded.
DEBUG stays false. The staging development-login endpoint remains restricted to
the allowlist; production settings disable it. The backend listens only on
127.0.0.1:18081.

`init_staging_passwords.py` initializes only existing allowlisted test users with
unusable passwords; it refuses to replace a different usable password. Run it
with the staging environment and credentials JSON on stdin, never as part of
every deployment. Do not commit credentials files.

The staging compatibility middleware still maps backend API 401 responses to 403
while preserving their JSON business error codes. It was introduced for the former
Basic-auth gateway and does not grant access or implement Basic authentication.
The frontend recognizes `UNAUTHENTICATED` independently of transport status.
Production and local development keep their original 401 contract.

## Automatic updates

1. Merge into `staging`.
2. GitHub Actions `Staging checks` builds the frontend and runs the backend tests
   against an ephemeral PostgreSQL 15 service.
3. A dedicated server timer polls every two minutes. It deploys only the exact
   current staging commit with a successful `push` run of `staging.yml` in this repo.
4. It builds and tests again under the restricted service user, backs up only the
   staging DB, applies migrations, then switches the release and restarts only
   `jimeet-staging.service`. Failed builds/tests never switch the active version.
5. Refresh the browser after deployment. `/version.json` records the deployed SHA.

The controller reads the public branch SHA through GitHub's official API and
downloads that immutable commit from `codeload.github.com`, without depending on
the Git transport endpoint. It verifies the matching successful CI run and checks
the branch again before switching releases. No root SSH keys or GitHub tokens are
stored in Actions. If the repository becomes private, configure a scoped read credential.
Allow several minutes for CI, polling and deployment; GitHub API/network failures
leave the existing site active and are retried at the next timer run.

`cache_wheels.py` optionally warms the isolated wheel cache under
`/opt/jimeet-staging/wheels`. Mirrors are accepted only when wheel SHA256 matches
official PyPI metadata. Deployment tries that cache first and falls back to PyPI
when requirements change. No member's virtual environment is reused or modified.

## Operations

Services: `jimeet-staging`, `jimeet-staging-nginx`, `jimeet-staging-deploy.timer`.
Logs: `journalctl -u jimeet-staging` / `journalctl -u jimeet-staging-deploy`.
Disable automatic updates with `systemctl stop jimeet-staging-deploy.timer`.
Server secrets live in `/etc/jimeet-staging`, separate from releases.
Private uploads persist in `/srv/jimeet-staging/shared/private` and have no Nginx alias.

Deployment controller and service/nginx files are installed as root-owned copies;
changing their repository copies does not automatically alter privileged server
configuration. Those changes require explicit operator installation.

## Migration and rollback limits

Only backwards-compatible schema migrations belong in unattended deployments.
A failing post-start health check switches back to the previous code, but does not
undo database migrations. Destructive schema changes need an explicit maintenance
plan. Backups are written before migrations to `/srv/jimeet-staging/backups`.
Old releases/backups are retained; periodically review disk usage and remove only
reviewed staging artifacts. Concurrent deployments are blocked by a server lock.

Protect `staging` with PR reviews and required `Staging checks` status where your
repository permissions/plan allow. Deploy code only from trusted team members.

## Verification

Run `python deploy/smoke_http.py - http://121.36.228.209 <accounts-json>`
from a trusted operator machine. This creates marked synthetic recruitment,
application and announcement records and checks password login, CSRF, resume
access and administrator-only announcement publishing. Keep credentials outside
the repository. `snapshot_staging.py` can capture existing record identifiers,
statuses and private-file hashes before a migration and compare them afterward.
