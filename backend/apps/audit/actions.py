"""必须记录的业务审计动作。"""
RECRUITMENT_DELETE = "recruitment_delete"
ADMIN_DELETE = "admin_delete"
RESUME_VIEW = "resume_view"
APPLICATION_UPDATE = "application_update"
PERMISSION_DENIED = "permission_denied"

ALL = frozenset(
    {RECRUITMENT_DELETE, ADMIN_DELETE, RESUME_VIEW, APPLICATION_UPDATE, PERMISSION_DENIED}
)
