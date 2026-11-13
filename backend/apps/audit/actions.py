"""必须记录的业务审计动作。"""
RECRUITMENT_DELETE = "recruitment_delete"
ADMIN_DELETE = "admin_delete"
RESUME_VIEW = "resume_view"
APPLICATION_UPDATE = "application_update"
PERMISSION_DENIED = "permission_denied"
ANNOUNCEMENT_PUBLISH = "announcement_publish"
ANNOUNCEMENT_UPDATE = "announcement_update"
ANNOUNCEMENT_DELETE = "announcement_delete"
ADMIN_GRANT = "admin_grant"
ADMIN_REVOKE = "admin_revoke"
PASSWORD_INIT = "password_init"

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
        ADMIN_GRANT,
        ADMIN_REVOKE,
        PASSWORD_INIT,
    }
)

# 由受控管理命令触发、允许不带登录操作者的动作。
SYSTEM_MANAGED = frozenset({PERMISSION_DENIED, ADMIN_GRANT, ADMIN_REVOKE, PASSWORD_INIT})
