"""枚举取值，与 database.md 的 CHECK 约束逐字一致。"""
from django.db import models


class Role(models.TextChoices):
    """
    系统中可能的用户角色。

    ### Attributes
    - `STUDENT`: 学生角色，值为 "student"
    - `TEACHER`: 教师角色，值为 "teacher"
    """
    STUDENT = "student", "学生"
    TEACHER = "teacher", "教师"


class RecruitmentType(models.TextChoices):
    """
    系统中可能的招聘类型。

    ### Attributes
    - `COMPETITION`: 竞赛类型，值为 "competition"
    - `ACTIVITY`: 活动类型，值为 "activity"
    - `INTERNSHIP`: 实习类型，值为 "internship"
    """
    COMPETITION = "competition", "竞赛"
    ACTIVITY = "activity", "活动"
    INTERNSHIP = "internship", "实习"


class RecruitmentStatus(models.TextChoices):
    """
    系统中可能的招聘状态。

    ### Attributes
    - `OPEN`: 开放状态，值为 "open"
    - `FULL`: 满员状态，值为 "full"
    - `CLOSED`: 已关闭状态，值为 "closed"
    """
    OPEN = "open", "开放"
    FULL = "full", "满员"
    CLOSED = "closed", "已关闭"


class CloseReason(models.TextChoices):
    """
    系统中可能的关闭原因。
    ### Attributes
    - `DEADLINE`: 到期关闭，值为 "deadline"
    - `MANUAL`: 手动关闭，值为 "manual"
    """
    DEADLINE = "deadline", "到期"
    MANUAL = "manual", "手动"


class ApplicationStatus(models.TextChoices):
    """
    系统中可能的应用状态。

    ### Attributes
    - `PROCESSING`: 处理中，值为 "processing"
    - `ACCEPTED`: 已接受，值为 "accepted"
    - `REJECTED`: 已拒绝，值为 "rejected"
    - `WITHDRAWN`: 已撤回，值为 "withdrawn"
    - `INVALID`: 已失效，值为 "invalid"
    """
    PROCESSING = "processing", "处理中"
    ACCEPTED = "accepted", "已接受"
    REJECTED = "rejected", "已拒绝"
    WITHDRAWN = "withdrawn", "已撤回"
    INVALID = "invalid", "已失效"


class PublisherMark(models.TextChoices):
    """
    定义了系统中可能的发布者标记
    ### Attributes
    - `NONE`: 无标记，值为 "none"
    - `HOLD`: 暂留标记，值为 "hold"
    """
    NONE = "none", "无"
    HOLD = "hold", "暂留"


class ResumeType(models.TextChoices):
    """
    所有可能的简历文件格式

    ### Attributes
    - `PDF`: PDF格式，值为 "pdf"
    - `DOC`: DOC格式，值为 "doc"
    - `DOCX`: DOCX格式，值为 "docx"
    """
    PDF = "pdf", "PDF"
    DOC = "doc", "DOC"
    DOCX = "docx", "DOCX"


class EmailStatus(models.TextChoices):
    """
    系统中可能的邮件发送状态。
    ### Attributes
    - `PENDING`: 待发送状态，值为 "pending"
    - `SENT`: 已发送状态，值为 "sent"
    - `FAILED`: 发送失败状态，值为 "failed"
    """
    PENDING = "pending", "待发送"
    SENT = "sent", "已发送"
    FAILED = "failed", "发送失败"
