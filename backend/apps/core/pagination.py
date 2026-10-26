from apps.core.errors import ValidationFailed

DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 50


def _read_positive_int(raw, field: str, default: int) -> int:
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
    """
    对 queryset 进行分页，返回 (items, page, page_size, total)。

    Args:
        queryset: 可分页的查询集
        request: DRF Request 对象，包含分页参数
    Returns:
        tuple: (items, page_number, page_size, total_count)
    Raises:
        ValidationFailed: 当分页参数无效时抛出
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
