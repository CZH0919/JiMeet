"""私有简历的扩展名、大小、文件头及展示名校验。"""
import io
import unicodedata
import zipfile

from apps.core.errors import ErrorCode, ValidationFailed

MAX_RESUME_SIZE = 10485760
RESUME_TYPES = frozenset({"pdf", "doc", "docx"})


def invalid_resume(reason: str) -> ValidationFailed:
    """
    生成带稳定原因码的文件校验异常。
    Args:
        reason: 异常原因
    Returns:
        ValidationFailed: 文件校验异常
    """
    return ValidationFailed("简历文件格式或大小不符合要求", code=ErrorCode.INVALID_RESUME_FILE,
                            details={"reason": reason})


def resume_extension(name: str) -> str:
    """
    读取最后一个路径段的扩展名，并检查是否在允许范围内；
    比起直接相信 Content-Type 或上传对象的 name 属性，额外检查文件头以防止伪造。

    Args:
        name: 上传文件名
    Returns:
        str: 扩展名（小写），若无扩展名则返回空
    Raises:
        ValidationFailed: 扩展名不在允许范围内
    """
    name = str(name).replace("\\", "/").rsplit("/", 1)[-1]
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if extension not in RESUME_TYPES:
        raise invalid_resume("type")
    return extension


def clean_resume_name(name: str, extension: str) -> str:
    """
    移除目录和控制字符，按 UTF-8 字节数截断并保留扩展名。

    Args:
        name: 上传文件名
        extension: 已知扩展名（小写）
    Returns:
        str: 展示名，长度不超过 255 字节
    
    """
    basename = str(name).replace("\\", "/").rsplit("/", 1)[-1] # 仅保留最后一个路径段
    basename = "".join(char for char in basename if not unicodedata.category(char).startswith("C"))
    stem = basename.rsplit(".", 1)[0] if "." in basename else basename
    # 展示名也不允许只有扩展名，截断时忽略末尾不完整的 UTF-8 字符。
    stem = stem.strip() or "resume"
    suffix = f".{extension}"
    stem = stem.encode("utf-8")[:255 - len(suffix.encode("utf-8"))].decode("utf-8", errors="ignore")
    return stem + suffix


def validate_resume(upload) -> None:
    """
    校验声明大小与实际内容，结束后恢复调用前读取位置。

    Args:
        upload: 上传对象，必须支持 tell、seek、read 方法

    Returns:
        None(成功)
    
    Raises:
        ValidationFailed: 文件大小或文件头不符合要求
        
    """
    extension = resume_extension(upload.name)
    if upload.size is None or not 0 < upload.size <= MAX_RESUME_SIZE:
        # 如果上传对象没有 size 属性，或 size 为 0 或超过限制，则直接拒绝。
        raise invalid_resume("size")
    position = upload.tell()
    try:
        upload.seek(0)
        # 最多多读一个字节即可判定超限，避免将任意大的上传读入内存。
        content = upload.read(MAX_RESUME_SIZE + 1)
        if not content or len(content) > MAX_RESUME_SIZE:
            raise invalid_resume("size")
        valid = False

        # 通过文件头判断类型，避免仅依赖扩展名或 Content-Type。
        if extension == "pdf":
            valid = content.startswith(b"%PDF-")
        elif extension == "doc":
            valid = content.startswith(bytes.fromhex("D0 CF 11 E0 A1 B1 1A E1"))
        elif extension == "docx" and content.startswith(b"PK\x03\x04"):
            try:
                # 只检查目录，不解压内容，避免解压膨胀及文件路径写入。
                with zipfile.ZipFile(io.BytesIO(content)) as archive:
                    names = archive.namelist()
                    valid = "[Content_Types].xml" in names and any(name.startswith("word/") for name in names)
            except (zipfile.BadZipFile, ValueError):
                valid = False
        if not valid:
            raise invalid_resume("signature")
    finally:
        upload.seek(position)
