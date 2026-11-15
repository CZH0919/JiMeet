"""Root-owned deployment controller. Application/build commands always run as jimeetstage.

Initial: deploy.py --archive /tmp/jimeet-staging-source.tar --sha <commit>
Automatic: deploy.py (poll staging; only publish a successful Staging checks push run).
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import pwd
import re
import subprocess as sp
import time
import urllib.request
from datetime import datetime, timezone

ROOT = Path('/srv/jimeet-staging')
CONF = Path('/etc/jimeet-staging')
REPO = 'CZH0919/JiMeet'
NODE = '/opt/jimeet-staging/node/bin'
USER = 'jimeetstage'

def run(args, **kwargs):
    return sp.run(args, check=True, **kwargs)

def app_run(args, cwd, env):
    return run(['runuser','-u',USER,'--',*args], cwd=cwd, env=env)

def api(path):
    req=urllib.request.Request('https://api.github.com/repos/'+REPO+path,
                               headers={'User-Agent':'JiMeet-staging-deployer','Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(req,timeout=30) as response:
        return json.load(response)

def healthy():
    for _ in range(20):
        try:
            with urllib.request.urlopen('http://127.0.0.1:18081/api/v1/healthz',timeout=3) as r:
                if r.status==200 and json.load(r).get('data',{}).get('status')=='ok':
                    return True
        except Exception:
            pass
        time.sleep(1)
    return False

def switch(release):
    link=ROOT/'current.next'
    if link.is_symlink(): link.unlink()
    link.symlink_to(release)
    link.replace(ROOT/'current')

parser=argparse.ArgumentParser()
parser.add_argument('--archive')
parser.add_argument('--sha')
args=parser.parse_args()
lock=open('/run/lock/jimeet-staging-deploy.lock','w')
try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
except BlockingIOError: raise SystemExit('Another deployment is running')
base_env={**os.environ,'PATH':NODE+':/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin','PYTHONDONTWRITEBYTECODE':'1',
          'HOME':'/var/lib/jimeet-stage','DEV_API_TARGET':'http://127.0.0.1:18081',
          'PIP_DISABLE_PIP_VERSION_CHECK':'1'}
if args.archive:
    sha=args.sha
    archive=Path(args.archive)
else:
    repo=ROOT/'repository'
    if not repo.exists():
        repo.mkdir()
        account=pwd.getpwnam(USER)
        os.chown(repo,account.pw_uid,account.pw_gid)
        app_run(['git','clone','--bare','https://github.com/'+REPO+'.git',str(repo)],ROOT,base_env)
    app_run(['git','fetch','origin','+refs/heads/staging:refs/heads/staging'],repo,base_env)
    sha=run(['runuser','-u',USER,'--','git','-C',str(repo),'rev-parse','refs/heads/staging'],
            capture_output=True,text=True,env=base_env).stdout.strip()
    if (ROOT/'deployed-sha').exists() and (ROOT/'deployed-sha').read_text().strip()==sha:
        print('Already deployed '+sha); raise SystemExit(0)
    runs=api('/actions/workflows/staging.yml/runs?branch=staging&event=push&per_page=20')['workflow_runs']
    match=next((r for r in runs if r['head_sha']==sha and r['head_repository']['full_name']==REPO),None)
    if not match or match['status']!='completed' or match['conclusion']!='success':
        print('Waiting for successful Staging checks for '+sha); raise SystemExit(0)
    archive=ROOT/'candidate.tar'
    with archive.open('wb') as output:
        run(['runuser','-u',USER,'--','git','-C',str(repo),'archive',sha],stdout=output,env=base_env)
if not sha or not re.fullmatch('[0-9a-f]{40}',sha): raise SystemExit('Expected exact commit SHA')
release=ROOT/'releases'/(sha[:12]+'-'+str(int(time.time())))
release.mkdir()
run(['tar','-xf',str(archive),'-C',str(release),'--no-same-owner'])
run(['chown','-R',USER+':'+USER,str(release)])
venv=release/'.venv'
app_run(['/opt/python/3.12.15/bin/python3.12','-m','venv',str(venv)],release,base_env)
python=str(venv/'bin/python')
try:
    app_run([python,'-m','pip','install','--no-index','--find-links','/opt/jimeet-staging/wheels',
             '-r','backend/requirements/staging.txt'],release,base_env)
except sp.CalledProcessError:
    app_run([python,'-m','pip','install','--index-url','https://pypi.org/simple',
             '--timeout','60','--retries','3','-r','backend/requirements/staging.txt'],release,base_env)
app_run(['npm','ci','--no-audit','--no-fund'],release,base_env)
app_run(['npm','run','build'],release,base_env)
test_env={**base_env,**json.loads((CONF/'ci.json').read_text()),'DJANGO_SETTINGS_MODULE':'config.settings.staging_ci'}
# Tests create/drop only test_jimeet_staging_ci, never the staging application database.
app_run([python,'manage.py','test','--noinput'],release/'backend',test_env)
env={**base_env}
for line in (CONF/'app.env').read_text().splitlines():
    key,value=line.split('=',1); env[key]=value
if env['DB_NAME']!='jimeet_staging' or env['DB_USER']!='jimeet_staging':
    raise SystemExit('Refusing non-staging database')
backup=ROOT/'backups'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.dump')
run(['pg_dump','-h','127.0.0.1','-U','jimeet_staging','-d','jimeet_staging','-Fc','-f',str(backup)],
    env={**base_env,'PGPASSWORD':env['DB_PASSWORD']})
backup.chmod(0o600)
app_run([python,'manage.py','check'],release/'backend',env)
app_run([python,'manage.py','migrate','--noinput'],release/'backend',env)
app_run([python,'manage.py','seed_tags'],release/'backend',env)
version={'commit':sha,'deployed_at':datetime.now(timezone.utc).isoformat(),'branch':'staging','repository':REPO}
(release/'dist/version.json').write_text(json.dumps(version))
old=(ROOT/'current').resolve() if (ROOT/'current').is_symlink() else None
run(['systemctl','stop','jimeet-staging.service'])
switch(release)
try:
    run(['systemctl','start','jimeet-staging.service'])
    if not healthy(): raise RuntimeError('New backend health check failed')
except Exception:
    if old:
        switch(old)
        run(['systemctl','restart','jimeet-staging.service'])
    raise
# Schema migrations are not automatically reversed; only compatible migrations may auto-deploy.
(ROOT/'deployed-sha').write_text(sha+'\n')
print('DEPLOYED '+sha,flush=True)
