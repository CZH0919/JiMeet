"""Read generated test credentials from stdin; initialize only existing passwordless test users."""
import io, json, os, sys
from unittest.mock import patch
sys.path.insert(0,os.getcwd())
import django
django.setup()
from django.conf import settings
from django.core.management import call_command
from apps.accounts.models import User
assert settings.DATABASES['default']['NAME']=='jimeet_staging'
assert getattr(settings,'STAGING_LOGIN_ENABLED',False)
entries=json.load(sys.stdin)['accounts']
for entry in entries:
    assert entry['account'] in settings.STAGING_LOGIN_IDS
    user=User.objects.get(real_id=entry['account'])
    assert user.email.lower()==entry['email'].lower()
    if user.has_usable_password():
        if not user.check_password(entry['password']):
            raise RuntimeError('Refusing to replace an existing password: '+entry['account'])
        continue
    with patch('sys.stdin',io.StringIO(entry['password']+'\n')):
        call_command('init_password',email=user.email)
print('Test account passwords initialized; existing identities and records retained.')
