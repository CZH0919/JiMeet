"""Exercise only the staging site using synthetic records and real HTTP cookies/CSRF.

Usage: python deploy/smoke_http.py - http://121.36.228.209 /path/to/accounts.json
Use '-' for the current public entry, or a gateway JSON for a legacy gated site.
The credential file is never printed. Leave one marked smoke-test record for review.
"""
import json
from pathlib import Path
import sys
from datetime import datetime, timedelta, timezone
import requests

credentials=json.loads(Path(sys.argv[1]).read_text()) if sys.argv[1] != '-' else None
base=sys.argv[2].rstrip('/')
accounts = ({a['account']: a for a in json.loads(Path(sys.argv[3]).read_text())['accounts']}
            if len(sys.argv) > 3 else {})
checks=[]

def session():
    s=requests.Session()
    s.trust_env=False
    if credentials:
        s.auth=(credentials['username'],credentials['password'])
    return s

def call(s, method, path, expected=200, **kwargs):
    headers=kwargs.pop('headers',{})
    if method not in ('GET','HEAD'):
        headers['X-CSRFToken']=s.cookies.get('csrftoken','')
    r=s.request(method,base+path,headers=headers,timeout=30,**kwargs)
    assert r.status_code==expected, (method,path,r.status_code,r.text[:350])
    checks.append(f'{method} {path}: {r.status_code}')
    return r

def login(real_id):
    s=session()
    call(s,'GET','/api/v1/auth/csrf')
    if accounts:
        account=accounts[real_id]
        call(s,'POST','/api/v1/auth/login',json={'email':account['email'],'password':account['password']})
    else:
        call(s,'POST','/api/v1/auth/dev-login',json={'real_id':real_id})
    call(s,'GET','/api/v1/me')
    return s

anonymous=requests.Session(); anonymous.trust_env=False
entry=anonymous.get(base+'/',timeout=20)
assert entry.status_code==(401 if credentials else 200)
if not credentials:
    assert 'WWW-Authenticate' not in entry.headers
checks.append('Gateway enabled: 401' if credentials else 'Public website entry: 200, no Basic challenge')
s=session()
html=call(s,'GET','/').text
assert 'id="root"' in html
call(s,'GET','/login')
call(s,'GET','/api/v1/healthz')
version=call(s,'GET','/version.json').json()
call(s,'GET','/api/v1/auth/csrf')
assert s.post(base+'/api/v1/auth/dev-login',json={'real_id':'qa01'},timeout=20).status_code==403
checks.append('Missing CSRF rejected: 403')
call(s,'POST','/api/v1/auth/dev-login',expected=403,json={'real_id':'outsider'})
publisher=login('qa01'); applicant=login('qa02'); stranger=login('qa03')
tags=call(publisher,'GET','/api/v1/tags').json()['data']['items']
stamp=datetime.now(timezone.utc).strftime('%m%d-%H%M%S')
payload={'title':'部署验证-'+stamp,'type':'competition',
         'description':'仅用于测试站部署验证的模拟招募，不对应真实活动。',
         'tag_ids':[tags[0]['id']], 'min_headcount':1, 'max_headcount':3,
         'deadline':(datetime.now(timezone.utc)+timedelta(days=14)).isoformat()}
recruitment=call(publisher,'POST','/api/v1/recruitments',201,json=payload).json()['data']
rid=recruitment['id']
call(applicant,'POST','/api/v1/me/privacy-consent',json={})
resume=b'%PDF-1.4\n% Synthetic staging smoke test; no personal data.\n%%EOF\n'
application=call(applicant,'POST',f'/api/v1/recruitments/{rid}/applications',201,
                 data={'note':'自动部署验证用模拟申请'},
                 files={'resume':('staging-test.pdf',resume,'application/pdf')}).json()['data']
aid=application['id']
assert call(publisher,'GET',f'/api/v1/applications/{aid}/resume').content==resume
call(stranger,'GET',f'/api/v1/applications/{aid}/resume',404)
accepted=call(publisher,'POST',f'/api/v1/applications/{aid}/accept',json={}).json()['data']
assert accepted['status']=='accepted'
call(applicant,'GET','/api/v1/notifications')
call(publisher,'GET','/api/v1/recruitments')
if accounts:
    admin=login('qaadmin')
    teacher=login('Tqa01')
    announcement_payload={'title':'新版部署验证公告-'+stamp,
        'content':'这是一条测试站模拟公告，用于验证新版首页与公告接口。',
        'time_kind':'event','event_at':payload['deadline'],'link_url':None,'recruitment_id':rid}
    call(applicant,'POST','/api/v1/announcements',403,json=announcement_payload)
    announcement=call(admin,'POST','/api/v1/announcements',201,json=announcement_payload).json()['data']
    call(applicant,'GET',f"/api/v1/announcements/{announcement['id']}")
    call(applicant,'GET','/api/v1/announcements')
print(json.dumps({'version':version,'checks':checks,'recruitment_id':rid,'application_id':aid},ensure_ascii=False,indent=2))
