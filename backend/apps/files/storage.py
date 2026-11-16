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
    """读取私有存储下的简历目录。

    Returns:
        Path: PRIVATE_FILE_ROOT/resumes，不创建目录。
    """
    return Path(settings.PRIVATE_FILE_ROOT) / "resumes"


def _checked_path(path: str) -> Path:
    """将存储相对路径解析为受限的绝对文件路径。

    Args:
        path: 相对 PRIVATE_FILE_ROOT 的简历路径，须位于 resumes 内。

    Returns:
        Path: 解析符号链接后的文件路径。

    Raises:
        PermissionError: 绝对路径、根目录或文件路径越界，含符号链接逃逸。
    """
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
    """在事务外校验上传并以随机路径排他创建私有文件。

    文件权限为 0600；不覆盖已有文件。失败只清理本次创建的文件，并恢复上传对象的读取位置。

    Args:
        upload: 可读、可定位的上传对象，含 name 与 size。

    Returns:
        StoredResume: 相对路径、清洗后的展示名、实际字节数及格式。

    Raises:
        RuntimeError: 调用方已在数据库事务中。
        ValidationFailed: 简历校验失败，或写入过程中实际内容为空/超限。
        OSError: 路径越界、随机名称碰撞、目录创建或文件写入失败。
    """
    assert_not_in_atomic()
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
    """暂存新简历，并在调用块抛出异常时清理。

    正常退出保留文件；调用方负责提交业务引用及在成功后清理被替换文件。保存和调用块异常继续向上传播。

    Args:
        upload: 传给 save_resume 的上传对象。

    Yields:
        StoredResume: 本次已保存的私有文件元数据。
    """
    stored = save_resume(upload)
    try:
        yield stored
    except BaseException:
        discard_resume(stored.path)
        raise


def open_resume(path: str) -> BinaryIO:
    """校验存储路径后以二进制模式打开简历。

    仅检查存储边界；业务身份及留存权限由调用方负责。

    Args:
        path: 相对 PRIVATE_FILE_ROOT 的简历路径。

    Returns:
        BinaryIO: 打开的只读文件句柄，由调用方关闭。

    Raises:
        OSError: 路径越界、文件缺失、权限不足或打开失败。
    """
    return _checked_path(path).open("rb")


def discard_resume(path: str) -> bool:
    """删除受限目录内的简历，不存在视为已清理。

    Args:
        path: 简历相对路径。

    Returns:
        bool: 删除成功或文件不存在为 True；路径无效或删除失败时记脱敏日志并返回 False。
    """
    try:
        _checked_path(path).unlink(missing_ok=True)
        return True
    except (OSError, ValueError):
        # 不记录原始路径或文件名，避免失败日志泄露申请文件元数据。
        logger.warning("简历文件清理失败")
        return False


def cleanup_orphans(*, older_than: timedelta = timedelta(hours=24),
                    referenced: Callable[[list[str]], set[str]]) -> CleanupReport:
    """分批删除超过年龄门槛且未被业务引用的简历。

    删除前再次核对修改时间；引用查询回调的异常向上传播。周期任务编排入口为预留能力。

    Args:
        older_than: 按修改时间计算的年龄门槛，默认 24 小时，不能短于 24 小时。
        referenced: 接收相对路径列表并返回仍被引用路径集合的回调。

    Returns:
        CleanupReport: 扫描、删除和失败数量；跳过符号链接，每批最多检查 200 个候选。

    Raises:
        RuntimeError: 调用方处于数据库事务中。
        ValueError: 年龄门槛小于 24 小时。
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
