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
ANNOUNCEMENT_REMOVED = "announcement_removed"
ANNOUNCEMENT_SUBMISSION_APPROVED = "announcement_submission_approved"
ANNOUNCEMENT_SUBMISSION_REJECTED = "announcement_submission_rejected"

ANONYMOUS_WITHDRAWAL = "anonymous_withdrawal"

ALL = frozenset(value for name, value in list(globals().items()) if name.isupper() and isinstance(value, str))
APPLICATION_EVENTS = frozenset(value for value in ALL if value.startswith("application_"))
PUBLISHER_APPLICATION_EVENTS = frozenset({APPLICATION_SUBMITTED, APPLICATION_UPDATED, APPLICATION_WITHDRAWN})
REQUIRES_APPLICATION = APPLICATION_EVENTS | {RECRUITMENT_UPDATED, RECRUITMENT_DELETED}
APPLICATION_RETENTION_EVENTS = REQUIRES_APPLICATION | {ANONYMOUS_WITHDRAWAL}
# 公告关联事件只关联公告，与招聘/申请关联互斥；投稿驳回通知不带目标关联。
ANNOUNCEMENT_EVENTS = frozenset({
    ANNOUNCEMENT_ADMIN_REMOVED, ANNOUNCEMENT_REMOVED, ANNOUNCEMENT_SUBMISSION_APPROVED,
})
# 公告删除结果通知：接收人为发布人或投稿人（相同只通知一次，由业务服务去重）。
ANNOUNCEMENT_DELETION_EVENTS = frozenset({ANNOUNCEMENT_ADMIN_REMOVED, ANNOUNCEMENT_REMOVED})
