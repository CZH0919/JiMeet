# JiMeet staging

Source of truth: `CZH0919/JiMeet`, branch `staging`. This deployment uses a separate
`/srv/jimeet-staging` tree, Linux user `jimeetstage`, application database
`jimeet_staging`, and regression database `jimeet_staging_ci`. It never deploys
into `/srv/jiMeet` or a member's home directory.

## Access

The initial endpoint is `http://121.36.228.209/`. Nginx asks for the team access
credentials before serving either the SPA or API. Credentials are generated on
the server in `/etc/jimeet-staging/access.json` (root only); do not commit them.
Only synthetic test data is appropriate for this initial HTTP deployment.
After adding HTTPS, update the trusted origin and `STAGING_HTTPS=true`.

Inside the website, allowed test identities are `qa01` to `qa06`, `Tqa01`, `Tqa02`
and `qaadmin`. Teachers have the T prefix. `qaadmin` is not an administrator
unless explicitly seeded by the operator. DEBUG stays false. Production settings
still disable development login. The backend listens only on 127.0.0.1:18081.

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

The public repository can be fetched without storing root SSH keys or GitHub tokens
in Actions. If the repository becomes private, configure a scoped read credential.
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
