"""私有简历的扩展名、大小、文件头及展示名校验。"""
import io
import unicodedata
import zipfile

from apps.core.errors import ErrorCode, ValidationFailed

MAX_RESUME_SIZE = 10485760
RESUME_TYPES = frozenset({"pdf", "doc", "docx"})


def invalid_resume(reason: str) -> ValidationFailed:
    """构造带稳定原因码的简历校验异常。

    Args:
        reason: 原因标识，当前使用 type、size、signature。

    Returns:
        ValidationFailed: INVALID_RESUME_FILE、HTTP 400；原因位于 details.reason，由调用方抛出。
    """
    return ValidationFailed("简历文件格式或大小不符合要求", code=ErrorCode.INVALID_RESUME_FILE,
                            details={"reason": reason})


def resume_extension(name: str) -> str:
    """从文件名末段提取并校验受支持的扩展名。

    Args:
        name: 原始上传文件名。

    Returns:
        str: 小写的 pdf、doc 或 docx；该函数不检查文件内容。

    Raises:
        ValidationFailed: 扩展名缺失或不受支持，reason 为 type。
    """
    name = str(name).replace("\\", "/").rsplit("/", 1)[-1]
    extension = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if extension not in RESUME_TYPES:
        raise invalid_resume("type")
    return extension


def clean_resume_name(name: str, extension: str) -> str:
    """移除目录及控制字符，并生成长度受限的展示文件名。

    Args:
        name: 原始上传名称。
        extension: 已通过校验的小写扩展名。

    Returns:
        str: 不超过 255 个 UTF-8 字节的文件名；空文件主名替换为 resume。
    """
    basename = str(name).replace("\\", "/").rsplit("/", 1)[-1]
    basename = "".join(char for char in basename if not unicodedata.category(char).startswith("C"))
    stem = basename.rsplit(".", 1)[0] if "." in basename else basename
    # 展示名也不允许只有扩展名，截断时忽略末尾不完整的 UTF-8 字符。
    stem = stem.strip() or "resume"
    suffix = f".{extension}"
    stem = stem.encode("utf-8")[:255 - len(suffix.encode("utf-8"))].decode("utf-8", errors="ignore")
    return stem + suffix


def validate_resume(upload) -> None:
    """校验扩展名、声明/实际大小及文件特征，并恢复读取位置。

    最多读取上限加一个字节；DOCX 只检查 ZIP 目录条目，不解压到文件系统。

    Args:
        upload: 带 name、size 且支持 read、seek、tell 的上传对象。

    Returns:
        None: 文件满足当前校验规则，非空且不超过 10 MiB。

    Raises:
        ValidationFailed: 类型、大小或 PDF/DOC/DOCX 文件特征不合格。
        OSError: 文件读取或定位失败。
    """
    extension = resume_extension(upload.name)
    if upload.size is None or not 0 < upload.size <= MAX_RESUME_SIZE:
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
