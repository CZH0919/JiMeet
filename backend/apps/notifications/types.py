"""通知类型、目标关联及业务接收人分类。"""
APPLICATION_SUBMITTED = "application_submitted"
APPLICATION_ACCEPTED = "application_accepted"
APPLICATION_REJECTED = "application_rejected"
APPLICATION_WITHDRAWN = "application_withdrawn"
APPLICATION_UPDATED = "application_updated"
RECRUITMENT_CLOSED = "recruitment_closed"
RECRUITMENT_UPDATED = "recruitment_updated"
RECRUITMENT_DELETED = "recruitment_deleted"
ADMIN_REMOVED = "admin_removed"
ANNOUNCEMENT_ADMIN_REMOVED = "announcement_admin_removed"

ALL = frozenset(value for name, value in list(globals().items()) if name.isupper() and isinstance(value, str))
APPLICATION_EVENTS = frozenset(value for value in ALL if value.startswith("application_"))
PUBLISHER_APPLICATION_EVENTS = frozenset({APPLICATION_SUBMITTED, APPLICATION_UPDATED, APPLICATION_WITHDRAWN})
REQUIRES_APPLICATION = APPLICATION_EVENTS | {RECRUITMENT_UPDATED, RECRUITMENT_DELETED}
# 公告治理通知只关联公告，与招聘/申请关联互斥。
ANNOUNCEMENT_EVENTS = frozenset({ANNOUNCEMENT_ADMIN_REMOVED})
