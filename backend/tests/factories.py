import uuid
from datetime import timedelta

from apps.core.clock import now


def _unique(prefix: str) -> str:
    return f"{prefix}{uuid.uuid4().hex[:8]}"


def make_user(real_id=None, role="student", is_admin=False, privacy=True, **overrides):
    from apps.accounts.models import User

    real_id = real_id or _unique("t" if role == "teacher" else "s")
    fields = {
        "name": overrides.pop("name", f"用户{real_id}"),
        "email": overrides.pop("email", f"{real_id}@tongji.edu.cn"),
        "role": role,
        "is_admin": is_admin,
        "privacy_consented_at": now() if privacy else None,
    }
    fields.update(overrides)
    return User.objects.create_user(real_id, fields.pop("name"), fields.pop("email"), **fields)


def make_tag(name=None, active=True, **overrides):
    from apps.recruitments.models import Tag

    fields = {"name": name or _unique("tag"), "is_active": active}
    fields.update(overrides)
    return Tag.objects.create(**fields)


def make_recruitment(publisher, **overrides):
    from apps.recruitments.models import Recruitment

    fields = {
        "publisher": publisher,
        "title": _unique("招聘"),
        "description": "描述",
        "type": "competition",
        "status": "open",
        "max_headcount": 3,
        "accepted_count": 0,
        "deadline": now() + timedelta(days=7),
    }
    fields.update(overrides)
    return Recruitment.objects.create(**fields)


def make_application(recruitment, applicant, status="processing", **overrides):
    from apps.applications.models import Application

    fields = {
        "recruitment": recruitment,
        "applicant": applicant,
        "status": status,
        "resume_path": f"resumes/2026/01/{uuid.uuid4().hex}.pdf",
        "resume_original_name": "resume.pdf",
        "resume_size": 1024,
        "resume_type": "pdf",
    }
    if status != "processing":
        fields["decided_at"] = now()
    fields.update(overrides)
    return Application.objects.create(**fields)
