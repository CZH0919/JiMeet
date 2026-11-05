"""孤立简历清理任务包装预留；实际存储工具已在 storage 中提供。"""


def cleanup_orphans():
    """孤立文件引用查询与清理任务编排的预留入口。

    Raises:
        NotImplementedError: 任务编排尚未实现；底层 storage.cleanup_orphans 可独立调用。
    """
    raise NotImplementedError("reserved for week 2")
