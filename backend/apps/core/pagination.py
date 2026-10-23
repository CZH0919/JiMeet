"""页码分页。分页由调用方显式触发，不走 DRF 全局分页。"""
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
    """返回 (items, page, page_size, total)。"""
    page_number = _read_positive_int(request.query_params.get("page"), "page", DEFAULT_PAGE)
    page_size = _read_positive_int(
        request.query_params.get("page_size"), "page_size", DEFAULT_PAGE_SIZE
    )
    if page_size > MAX_PAGE_SIZE:
        raise ValidationFailed(details={"page_size": f"不得超过 {MAX_PAGE_SIZE}"})

    total = queryset.count()
    offset = (page_number - 1) * page_size
    items = list(queryset[offset : offset + page_size])
    return items, page_number, page_size, total
