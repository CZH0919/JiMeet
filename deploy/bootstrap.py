"""One-time root setup for the dedicated staging site; never touches /srv/jiMeet."""
import base64
import hashlib
import json
import os
from pathlib import Path
import pwd
import secrets
import subprocess as sp
import urllib.request

ROOT = Path('/srv/jimeet-staging')
CONF = Path('/etc/jimeet-staging')
USER = 'jimeetstage'

def run(*args, **kwargs):
    return sp.run(args, check=True, **kwargs)

def write(path, content, mode=0o644):
    path = Path(path)
    path.write_text(content)
    path.chmod(mode)

if ROOT.exists() or CONF.exists():
    raise SystemExit('Dedicated paths already exist; inspect before retrying bootstrap')
run('useradd', '--system', '--create-home', '--home-dir', '/var/lib/jimeet-stage', '--shell', '/usr/sbin/nologin', USER)
account = pwd.getpwnam(USER)
ROOT.mkdir(mode=0o755)
CONF.mkdir(mode=0o750)
os.chown(CONF, 0, account.pw_gid)
for name in ('releases', 'shared', 'backups'):
    (ROOT/name).mkdir()
    os.chown(ROOT/name, account.pw_uid, account.pw_gid)
(ROOT/'shared/private').mkdir(mode=0o700)
os.chown(ROOT/'shared/private', account.pw_uid, account.pw_gid)
password = secrets.token_hex(24)
ci_password = secrets.token_hex(24)
for role, secret, createdb in [('jimeet_staging', password, ''), ('jimeet_staging_ci', ci_password, 'CREATEDB')]:
    # Fixed fresh names and random hex passwords; no existing roles/databases are altered.
    run('runuser', '-u', 'postgres', '--', 'psql', '-X', '-v', 'ON_ERROR_STOP=1', '-c',
        f"CREATE ROLE {role} LOGIN PASSWORD '{secret}' {createdb};", stdout=sp.DEVNULL, cwd='/tmp')
    run('runuser', '-u', 'postgres', '--', 'createdb', '-O', role, role, cwd='/tmp')
env = dict(DJANGO_SETTINGS_MODULE='config.settings.staging', DJANGO_SECRET_KEY=secrets.token_hex(48),
           DJANGO_ALLOWED_HOSTS='121.36.228.209,127.0.0.1,localhost',
           DB_NAME='jimeet_staging', DB_USER='jimeet_staging', DB_PASSWORD=password,
           DB_HOST='127.0.0.1', DB_PORT='5432', PRIVATE_FILE_ROOT=str(ROOT/'shared/private'),
           STAGING_LOGIN_IDS='qa01,qa02,qa03,qa04,qa05,qa06,Tqa01,Tqa02,qaadmin',
           CSRF_TRUSTED_ORIGINS='http://121.36.228.209', STAGING_HTTPS='false',
           PYTHONDONTWRITEBYTECODE='1')
write(CONF/'app.env', ''.join(f'{k}={v}\n' for k,v in env.items()), 0o640)
os.chown(CONF/'app.env', 0, account.pw_gid)
write(CONF/'ci.json', json.dumps(dict(DB_NAME='jimeet_staging_ci', DB_USER='jimeet_staging_ci',
                                      DB_PASSWORD=ci_password, DB_HOST='127.0.0.1', DB_PORT='5432')), 0o600)
gate_password = secrets.token_urlsafe(18)
hashed = run('openssl', 'passwd', '-6', '-stdin', input=gate_password+'\n', text=True, capture_output=True).stdout.strip()
write(CONF/'htpasswd', 'tester:'+hashed+'\n', 0o640)
os.chown(CONF/'htpasswd', 0, pwd.getpwnam('www-data').pw_gid)
# Nginx workers need directory traversal, not access to app/CI secrets.
CONF.chmod(0o751)
write(CONF/'access.json', json.dumps({'username':'tester','password':gate_password}), 0o600)
node_root=Path('/opt/jimeet-staging')
node_root.mkdir()
base='https://nodejs.org/dist/latest-v22.x/'
lines=urllib.request.urlopen(base+'SHASUMS256.txt', timeout=30).read().decode().splitlines()
checksum, filename=next(line.split() for line in lines if line.endswith('-linux-x64.tar.xz'))
archive=node_root/filename
urllib.request.urlretrieve(base+filename, archive)
assert hashlib.sha256(archive.read_bytes()).hexdigest()==checksum
run('tar','-xJf',str(archive),'-C',str(node_root))
(node_root/'node').symlink_to(node_root/filename.removesuffix('.tar.xz'))
run('apt-get', 'update', env={**os.environ,'DEBIAN_FRONTEND':'noninteractive'}, stdout=sp.DEVNULL)
run('apt-get','install','-y','--no-install-recommends','nginx',
    env={**os.environ,'DEBIAN_FRONTEND':'noninteractive','NEEDRESTART_MODE':'l'}, stdout=sp.DEVNULL)
# Nginx was absent at preflight. Use a separate service/config, leaving package sites untouched.
run('systemctl','disable','--now','nginx')
print('BOOTSTRAP_COMPLETE: dedicated account, databases, configuration and dependencies created')
