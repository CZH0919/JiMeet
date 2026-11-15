"""Run once with staging settings to create synthetic team accounts."""
import os
import sys
sys.path.insert(0, os.getcwd())
import django
django.setup()
from django.conf import settings
from apps.accounts.services import login_with_sso
from apps.accounts.sso import DevSSOProvider

assert settings.DATABASES['default']['NAME']=='jimeet_staging'
assert getattr(settings,'STAGING_LOGIN_ENABLED',False)
for real_id in settings.STAGING_LOGIN_IDS:
    name=('测试管理员' if real_id=='qaadmin' else
          ('测试教师'+real_id[-2:] if real_id.startswith('T') else '测试学生'+real_id[-2:]))
    user=login_with_sso(DevSSOProvider().exchange({'real_id':real_id,'name':name}))
    user.nickname=name
    user.is_admin=(real_id=='qaadmin')
    user.email_notify_enabled=False
    user.save(update_fields=['nickname','is_admin','email_notify_enabled'])
    print(real_id, user.role, 'admin='+str(user.is_admin))
