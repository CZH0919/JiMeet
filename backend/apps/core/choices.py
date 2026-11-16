"""枚举取值，与 database.md 的 CHECK 约束逐字一致。"""
from django.db import models


class Role(models.TextChoices):
    """用户身份枚举：学生或教师；与管理员标记独立。"""
    STUDENT = "student", "学生"
    TEACHER = "teacher", "教师"


class RecruitmentType(models.TextChoices):
    """招募类型枚举：竞赛、活动或实习。"""
    COMPETITION = "competition", "竞赛"
    ACTIVITY = "activity", "活动"
    INTERNSHIP = "internship", "实习"


class RecruitmentStatus(models.TextChoices):
    """招募状态枚举：开放、满员或关闭；删除由 deleted_at 单独表示。"""
    OPEN = "open", "开放"
    FULL = "full", "满员"
    CLOSED = "closed", "已关闭"


class CloseReason(models.TextChoices):
    """招募首次关闭的原因枚举。"""
    DEADLINE = "deadline", "到期"
    MANUAL = "manual", "手动"


class ApplicationStatus(models.TextChoices):
    """申请状态枚举；暂留使用独立的发布者标记。"""
    PROCESSING = "processing", "处理中"
    ACCEPTED = "accepted", "已接受"
    REJECTED = "rejected", "已拒绝"
    WITHDRAWN = "withdrawn", "已撤回"
    INVALID = "invalid", "已失效"


class PublisherMark(models.TextChoices):
    """发布者私有标记枚举，不改变申请状态。"""
    NONE = "none", "无"
    HOLD = "hold", "暂留"


class ResumeType(models.TextChoices):
    """受支持的简历格式枚举。"""
    PDF = "pdf", "PDF"
    DOC = "doc", "DOC"
    DOCX = "docx", "DOCX"


class EmailStatus(models.TextChoices):
    """邮件发送记录状态枚举；真实投递尚未实现。"""
    PENDING = "pending", "待发送"
    SENT = "sent", "已发送"
    FAILED = "failed", "发送失败"


class AnnouncementTimeKind(models.TextChoices):
    """公告时间类型枚举：报名截止时间或活动时间。"""
    DEADLINE = "deadline", "报名截止时间"
    EVENT = "event", "活动时间"
