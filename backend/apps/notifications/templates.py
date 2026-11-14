"""通知文案模板；context 只允许摘要字段，防止泄露简历或申请人信息。"""
from apps.notifications import types

_ALLOWED_CONTEXT = {"recruitment_title", "announcement_title", "status_label", "link", "auto", "reason_label"}
_TEMPLATES = {
    types.APPLICATION_SUBMITTED: ("收到新申请", "您的招聘《{recruitment_title}》收到一份新申请。"),
    types.APPLICATION_ACCEPTED: ("申请已接受", "您对《{recruitment_title}》的申请已被接受。"),
    types.APPLICATION_REJECTED: ("申请已拒绝", "您对《{recruitment_title}》的申请已被拒绝。"),
    types.APPLICATION_WITHDRAWN: ("申请已撤回", "您的招聘《{recruitment_title}》有一份申请已撤回。"),
    types.APPLICATION_UPDATED: ("申请已更新", "您的招聘《{recruitment_title}》有一份申请已更新。"),
    types.RECRUITMENT_CLOSED: ("招聘已关闭", "您的招聘《{recruitment_title}》已到期关闭。"),
    types.RECRUITMENT_UPDATED: ("招聘已更新", "您申请的招聘《{recruitment_title}》已更新，请查看最新信息。"),
    types.RECRUITMENT_DELETED: ("申请已失效", "关联招聘《{recruitment_title}》已删除，您的申请已失效。"),
    types.ADMIN_REMOVED: ("招聘已被管理员删除", "您的招聘《{recruitment_title}》已被管理员删除。"),
    types.ANNOUNCEMENT_ADMIN_REMOVED: ("公告已被管理员删除", "您的公告《{announcement_title}》已被管理员删除。"),
}


def render(type: str, context: dict | None) -> tuple[str, str]:
    """使用白名单摘要字段生成通知标题与正文。

    Args:
        type: 已定义通知类型。
        context: 摘要映射或 None；允许 recruitment_title、announcement_title、
            status_label、link、auto、reason_label。

    Returns:
        tuple[str, str]: 标题与正文，不包含简历或申请说明。

    Raises:
        ValueError: 通知类型未知或上下文包含未声明字段。
    """
    context = dict(context or {})
    if type not in _TEMPLATES:
        raise ValueError("未知通知类型")
    if context.keys() - _ALLOWED_CONTEXT:
        raise ValueError("通知 context 包含不允许的字段")
    title, template = _TEMPLATES[type]
    content = template.format(
        recruitment_title=context.get("recruitment_title", "招聘"),
        announcement_title=context.get("announcement_title", "公告"),
    )
    if type == types.RECRUITMENT_CLOSED and context.get("auto") is False:
        content = "您的招聘《{}》已手动关闭。".format(context.get("recruitment_title", "招聘"))
    if type == types.APPLICATION_REJECTED and context.get("auto"):
        content += "系统已自动处理。"
    elif type == types.APPLICATION_REJECTED:
        context.setdefault("reason_label", "发布者主动拒绝")
    for key, label in (("status_label", "当前状态"), ("reason_label", "原因"), ("link", "站内链接")):
        if context.get(key):
            content += f"{label}：{context[key]}。"
    return title, content
