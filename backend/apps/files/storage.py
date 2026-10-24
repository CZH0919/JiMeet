"""私有简历存储及失败清理，不提供公开 URL。"""
import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import BinaryIO, Callable, Iterator
from uuid import uuid4

from django.conf import settings

from apps.core import clock
from apps.core.tx import assert_not_in_atomic
from apps.files.validators import (
    MAX_RESUME_SIZE, clean_resume_name, invalid_resume, resume_extension, validate_resume,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoredResume:
    """可写入 Application 的相对路径、展示名、实际大小及格式。"""

    path: str
    original_name: str
    size: int
    type: str


@dataclass(frozen=True)
class CleanupReport:
    """扫描文件数、成功删除数、删除失败数；不保存申请或用户明细。"""

    scanned: int
    deleted: int
    failed: int


def _resume_root() -> Path:
    """返回私有存储中的简历根目录，支持测试覆盖配置。"""
    return Path(settings.PRIVATE_FILE_ROOT) / "resumes"


def _checked_path(path: str) -> Path:
    """解析相对路径，拒绝绝对路径、越界及通过软链接逃逸的目标。"""
    root = _resume_root()
    candidate = Path(path)
    if candidate.is_absolute():
        raise PermissionError("简历路径必须为相对路径")
    resolved = (Path(settings.PRIVATE_FILE_ROOT) / candidate).resolve()
    # 同时要求根目录自身没有被链接到私有根目录之外。
    private = Path(settings.PRIVATE_FILE_ROOT).resolve()
    resolved_root = root.resolve()
    if not resolved_root.is_relative_to(private) or not resolved.is_relative_to(resolved_root) or resolved == resolved_root:
        raise PermissionError("简历路径超出私有目录")
    return resolved


def save_resume(upload) -> StoredResume:
    """事务外校验并以随机路径排他创建文件，写入失败清理不完整文件。"""
    assert_not_in_atomic() # 确定数据库连接不在外层事务中，避免锁住业务事务。
    validate_resume(upload)
    extension = resume_extension(upload.name)
    original_name = clean_resume_name(upload.name, extension)
    now = clock.now()
    relative = f"resumes/{now:%Y/%m}/{uuid4().hex}.{extension}"
    destination = _checked_path(relative)
    destination.parent.mkdir(parents=True, exist_ok=True)
    position = upload.tell()
    created = False
    try:
        # O_EXCL 确保碰撞时不会覆盖已有简历，失败时也不能删除别人的文件。
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
        with os.fdopen(descriptor, "wb") as output:
            upload.seek(0)
            size = 0
            while True:
                chunk = upload.read(65536)
                if not chunk:
                    break
                size += len(chunk)
                # 保存时再次限制实际大小，避免校验与写入间的内容变化导致超限。
                if size > MAX_RESUME_SIZE:
                    raise invalid_resume("size")
                output.write(chunk)
            if size == 0:
                raise invalid_resume("size")
            output.flush()
            os.fsync(output.fileno())
        return StoredResume(relative, original_name, size, extension)
    except BaseException:
        if created:
            discard_resume(relative)
        raise
    finally:
        upload.seek(position)


@contextmanager
def staged_resume(upload) -> Iterator[StoredResume]:
    """暂存新文件；调用块失败时清理，提交成功后由调用方另行删除旧文件。"""
    stored = save_resume(upload)
    try:
        yield stored
    except BaseException:
        discard_resume(stored.path)
        raise


def open_resume(path: str) -> BinaryIO:
    """校验私有路径后以二进制方式打开，权限判断由调用方负责。"""
    return _checked_path(path).open("rb")


def discard_resume(path: str) -> bool:
    """安全删除简历，不存在视为成功；失败只记录日志并返回 False。"""
    try:
        _checked_path(path).unlink(missing_ok=True)
        return True
    except (OSError, ValueError):
        # 不记录原始路径或文件名，避免失败日志泄露申请文件元数据。
        logger.warning("简历文件清理失败")
        return False


def cleanup_orphans(*, older_than: timedelta = timedelta(hours=24),
                    referenced: Callable[[list[str]], set[str]]) -> CleanupReport:
    """
    分批清理未被引用且超过年龄门槛的简历，门槛不得短于 24 小时。

    Args:
        older_than: 文件修改时间超过该阈值才会被清理
        referenced: 回调函数，参数为相对路径列表，返回仍被引用的相对路径集合
    Returns:
        CleanupReport，表示扫描文件数、成功删除数、删除失败数；不保存申请或用户明细。
    """
    assert_not_in_atomic()
    if older_than < timedelta(hours=24):
        raise ValueError("孤立文件清理门槛不得短于 24 小时")
    cutoff = clock.now().timestamp() - older_than.total_seconds()
    scanned = deleted = failed = 0
    batch = []

    def clean_batch(paths: list[str]) -> tuple[int, int]:
        """先批量核对数据库引用，再删除仍满足年龄要求的文件。"""
        used = referenced(paths)
        removed = errors = 0
        for path in paths:
            if path in used:
                continue
            try:
                # 查询后再次检查修改时间，避免删除扫描期间被重新写入的文件。
                if _checked_path(path).stat().st_mtime >= cutoff:
                    continue
            except FileNotFoundError:
                continue
            except (OSError, ValueError):
                logger.warning("孤立简历检查失败")
                errors += 1
                continue
            if discard_resume(path):
                removed += 1
            else:
                errors += 1
        return removed, errors

    for candidate in _resume_root().rglob("*"):
        # 不跟随文件软链接，避免扫描或删除链接指向的其他简历。
        if candidate.is_symlink() or not candidate.is_file():
            continue
        scanned += 1
        try:
            if candidate.stat().st_mtime >= cutoff:
                continue
        except FileNotFoundError:
            continue
        except OSError:
            logger.warning("孤立简历扫描失败")
            failed += 1
            continue
        batch.append(candidate.relative_to(Path(settings.PRIVATE_FILE_ROOT)).as_posix())
        if len(batch) >= 200:
            removed, errors = clean_batch(batch)
            deleted += removed
            failed += errors
            batch = []
    if batch:
        removed, errors = clean_batch(batch)
        deleted += removed
        failed += errors
    return CleanupReport(scanned, deleted, failed)
