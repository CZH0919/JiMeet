"""创建可校验的 PostgreSQL 备份，按数据库保留，恢复只写入新库。"""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from uuid import uuid4


SNAPSHOT_NAME = re.compile(r"([0-9]{8}T[0-9]{6}Z)-[0-9a-f]{8}")
STAMP = "%Y%m%dT%H%M%SZ"


def database_name(value):
    """只接受普通数据库名，避免被解释为连接字符串或命令选项。"""
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,62}", value or ""):
        raise ValueError("数据库名须以小写字母开头，仅含小写字母、数字或下划线")
    return value


def checksum(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prune(directory, cutoff):
    """仅轮换本工具生成且早于保留期的完整备份。"""
    for item in directory.iterdir():
        match = SNAPSHOT_NAME.fullmatch(item.name)
        if not match or item.is_symlink() or not item.is_dir():
            continue
        taken = datetime.strptime(match[1], STAMP).replace(tzinfo=timezone.utc)
        if taken >= cutoff:
            continue
        contents = list(item.iterdir())
        if {p.name for p in contents} != {"database.dump", "database.sha256"}:
            continue
        if all(p.is_file() and not p.is_symlink() for p in contents):
            for p in contents:
                p.unlink()
            item.rmdir()


def backup(root, keep_days):
    source = database_name(os.environ.get("PGDATABASE"))
    if not root.is_absolute() or keep_days < 30:
        raise ValueError("备份目录须使用绝对路径，备份至少保留 30 天")
    directory = root / source
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).replace(microsecond=0)
    target = directory / (now.strftime(STAMP) + "-" + uuid4().hex[:8])
    with tempfile.TemporaryDirectory(prefix=".pending-", dir=directory) as temporary:
        staging = Path(temporary)
        archive = staging / "database.dump"
        subprocess.run(["pg_dump", "--no-password", "--format=custom", "--file", archive, "--dbname", source], check=True)
        subprocess.run(["pg_restore", "--list", archive], stdout=subprocess.DEVNULL, check=True)
        (staging / "database.sha256").write_text(checksum(archive) + "\n", encoding="ascii")
        staging.rename(target)
    prune(directory, now - timedelta(days=keep_days))
    print(target)


def restore(snapshot, target):
    """先校验存档，再创建目标库并在单一事务中恢复。"""
    database_name(target)
    archive = snapshot / "database.dump"
    if target == snapshot.parent.name or target == os.environ.get("PGDATABASE"):
        raise ValueError("恢复目标须使用独立的新库名")
    if checksum(archive) != (snapshot / "database.sha256").read_text(encoding="ascii").strip():
        raise ValueError("备份校验失败")
    subprocess.run(["createdb", "--no-password", "--maintenance-db=postgres", "--template=template0", target], check=True)
    subprocess.run(["pg_restore", "--no-password", "--single-transaction", "--exit-on-error",
                    "--no-owner", "--no-privileges", "--dbname", target, archive], check=True)
    print(f"已恢复至 {target}")


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    save = commands.add_parser("backup")
    save.add_argument("--directory", type=Path, required=True)
    save.add_argument("--keep-days", type=int, default=30)
    load = commands.add_parser("restore")
    load.add_argument("snapshot", type=Path)
    load.add_argument("target")
    args = parser.parse_args()
    if args.operation == "backup":
        backup(args.directory, args.keep_days)
    else:
        restore(args.snapshot, args.target)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        sys.exit(str(exc))
