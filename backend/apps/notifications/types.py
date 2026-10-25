"""通知类型及关联要求；申请事件前缀供留存清理复用。"""
APPLICATION_SUBMITTED = "application_submitted"
APPLICATION_ACCEPTED = "application_accepted"
APPLICATION_REJECTED = "application_rejected"
APPLICATION_WITHDRAWN = "application_withdrawn"
APPLICATION_UPDATED = "application_updated"
RECRUITMENT_CLOSED = "recruitment_closed"
RECRUITMENT_UPDATED = "recruitment_updated"
RECRUITMENT_DELETED = "recruitment_deleted"
ADMIN_REMOVED = "admin_removed"

ALL = frozenset(value for name, value in list(globals().items()) if name.isupper() and isinstance(value, str))
APPLICATION_EVENTS = frozenset(value for value in ALL if value.startswith("application_"))
# 删除通知也可发给发布者，因此其申请关联由 service 按接收人身份判断。
REQUIRES_APPLICATION = APPLICATION_EVENTS | {RECRUITMENT_UPDATED}
