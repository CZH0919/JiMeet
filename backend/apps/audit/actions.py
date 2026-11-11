"""必须记录的业务审计动作。"""
RECRUITMENT_DELETE = "recruitment_delete"
ADMIN_DELETE = "admin_delete"
RESUME_VIEW = "resume_view"
APPLICATION_UPDATE = "application_update"
PERMISSION_DENIED = "permission_denied"
ANNOUNCEMENT_PUBLISH = "announcement_publish"
ANNOUNCEMENT_UPDATE = "announcement_update"
ANNOUNCEMENT_DELETE = "announcement_delete"

ALL = frozenset(
    {
        RECRUITMENT_DELETE,
        ADMIN_DELETE,
        RESUME_VIEW,
        APPLICATION_UPDATE,
        PERMISSION_DENIED,
        ANNOUNCEMENT_PUBLISH,
        ANNOUNCEMENT_UPDATE,
        ANNOUNCEMENT_DELETE,
    }
)
