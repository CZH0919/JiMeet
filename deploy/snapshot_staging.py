"""Read-only evidence for preserving staging records across a release."""
import os, sys, json, hashlib
from pathlib import Path
sys.path.insert(0, os.getcwd())
import django
django.setup()
from django.conf import settings
from apps.accounts.models import User
from apps.recruitments.models import Recruitment
from apps.applications.models import Application
assert settings.DATABASES['default']['NAME']=='jimeet_staging'
snapshot={
    'users':list(User.objects.order_by('pk').values('id','uid','real_id','role','is_admin')),
    'recruitments':list(Recruitment.objects.order_by('pk').values('id','publisher_id','status')),
    'applications':list(Application.objects.order_by('pk').values('id','recruitment_id','applicant_id','status','resume_file')),
    'files':{str(p.relative_to(settings.PRIVATE_FILE_ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
             for p in Path(settings.PRIVATE_FILE_ROOT).rglob('*') if p.is_file()},
}
print(json.dumps(snapshot,ensure_ascii=False))
