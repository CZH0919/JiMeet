from apps.core.errors import ValidationFailed

DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50


def _read_positive_int(raw, field: str, default: int) -> int:
    """解析分页整数，空值回退到指定默认值。

    Args:
        raw: 原始参数值，通常是查询字符串、空字符串或 None。
        field: 校验错误中使用的字段名。
        default: raw 为 None 或空字符串时采用的值。

    Returns:
        int: 解析后的正整数或默认值。

    Raises:
        ValidationFailed: 值无法转换为整数，或转换结果小于 1。
    """
    if raw in (None, ""):
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValidationFailed(details={field: "必须是整数"}) from None
    if value < 1:
        raise ValidationFailed(details={field: "必须大于 0"})
    return value


def paginate(queryset, request):
    """按查询参数分页，越界页返回空列表。

    Args:
        queryset: 已完成权限和业务过滤、排序的查询集。
        request: DRF 请求；page 默认 1，page_size 默认 20、最大 50。

    Returns:
        tuple: (记录列表, 页码, 每页数量, 过滤后的总数)。

    Raises:
        ValidationFailed: 分页值不是正整数，或 page_size 超过 50。
    """
    page_number = _read_positive_int(request.query_params.get("page"), "page", DEFAULT_PAGE)
    page_size = _read_positive_int(
        request.query_params.get("page_size"), "page_size", DEFAULT_PAGE_SIZE
    )
    if page_size > MAX_PAGE_SIZE:
        raise ValidationFailed(details={"page_size": f"不得超过 {MAX_PAGE_SIZE}"})

    total = queryset.count()
    offset = (page_number - 1) * page_size
    # 越界页无需访问数据切片，也避免极大页码转为数据库 OFFSET 时溢出。
    items = [] if offset >= total else list(queryset[offset : offset + page_size])
    return items, page_number, page_size, total
