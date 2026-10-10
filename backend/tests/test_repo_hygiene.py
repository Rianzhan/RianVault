"""仓库卫生回归测试。

教训：.gitignore 里一条未锚定根目录的 `models/`（本意是忽略 ML 权重缓存）
把整个 backend/app/models/ ORM 包排除在版本控制之外，几个提交的 schema 定义
实际从未入库，而本地测试完全正常 —— 只有 clone 之后才会炸。

这里守住两条底线：源码目录不被忽略，且关键源码文件确实被 git 跟踪。
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# 必须处于版本控制之下的源码路径（相对仓库根）。
MUST_BE_TRACKED = (
    "backend/app/models/__init__.py",
    "backend/app/models/memory.py",
    "backend/app/models/memory_version.py",
    "backend/app/models/migration_review.py",
    "backend/app/services/memory_service.py",
    "backend/app/api/routes/memories.py",
)


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def _is_git_repo() -> bool:
    return _git("rev-parse", "--is-inside-work-tree").stdout.strip() == "true"


pytestmark = pytest.mark.skipif(not _is_git_repo(), reason="not a git working tree")


@pytest.mark.parametrize("rel_path", MUST_BE_TRACKED)
def test_source_files_are_tracked(rel_path: str) -> None:
    assert (REPO_ROOT / rel_path).exists(), f"源码文件缺失: {rel_path}"
    listing = _git("ls-files", "--error-unmatch", rel_path)
    assert listing.returncode == 0, f"{rel_path} 未纳入版本控制（可能被 .gitignore 排除）"


def test_no_source_package_is_ignored() -> None:
    """backend/app 下的 .py 文件不允许被 .gitignore 命中。"""
    ignored = _git(
        "ls-files",
        "--others",
        "--ignored",
        "--exclude-standard",
        "backend/app",
    ).stdout.split()
    offenders = [p for p in ignored if p.endswith(".py")]
    assert not offenders, f"源码被 .gitignore 排除: {offenders}"
