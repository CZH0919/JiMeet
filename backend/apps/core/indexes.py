from django.db import models


class PostgreSQLIndex(models.Index):
    """
    使用 PostgreSQL 的 63 字节名称上限创建普通索引。

    本项目仅使用 PostgreSQL，允许沿用 database.md 中超过 Django 默认
    30 字符限制的索引名称；索引结构与普通 Index 一致。
    """

    max_name_length = 63
