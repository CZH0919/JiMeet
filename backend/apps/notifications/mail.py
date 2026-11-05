"""邮件投递接口；dispatch 仅记录调度日志，实际发送与重试尚未实现。"""
import logging

logger = logging.getLogger(__name__)


def dispatch(email_log_id: int) -> None:
    """记录提交后的邮件调度意图，不执行真实投递。

    Args:
        email_log_id: 已提交的 EmailLog 主键，仅作为日志元数据。

    Returns:
        None: 不修改发送状态，不输出邮箱或正文。
    """
    logger.info("email dispatch reserved", extra={"email_log_id": email_log_id})


def send_email_log(email_log_id: int) -> None:
    """邮件发送或重试的预留入口。

    Args:
        email_log_id: 待发送 EmailLog 主键。

    Raises:
        NotImplementedError: 当前实现始终拒绝执行，尚未接入真实邮件服务。
    """
    raise NotImplementedError("reserved for week 2")


def retry_pending_emails(limit: int) -> None:
    """邮件发送或重试的预留入口。

    Args:
        limit: 计划处理的记录数量上限，当前预留实现不使用。

    Raises:
        NotImplementedError: 当前实现始终拒绝执行，尚未接入真实邮件服务。
    """
    raise NotImplementedError("reserved for week 2")
