"""邮件发送接口预留；本周不发送邮件、不修改发送状态。"""
import logging

logger = logging.getLogger(__name__)


def dispatch(email_log_id: int) -> None:
    """记录提交后的调度入口，仅保留日志主键，不记录邮箱或正文。"""
    logger.info("email dispatch reserved", extra={"email_log_id": email_log_id})


def send_email_log(email_log_id: int) -> None:
    """预留单条邮件发送接口。"""
    raise NotImplementedError("reserved for week 2")


def retry_pending_emails(limit: int) -> None:
    """预留待发送邮件重试接口。"""
    raise NotImplementedError("reserved for week 2")
