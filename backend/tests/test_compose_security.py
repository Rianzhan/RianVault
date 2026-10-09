"""部署安全断言（不依赖 Docker，静态解析 compose 文件）：

- prod：db / qdrant 禁止发布任何端口（只允许内部网络）
- dev：所有发布端口必须绑定 127.0.0.1
"""

from pathlib import Path

import yaml

DEPLOY = Path(__file__).resolve().parents[2] / "deploy"


def _load(name: str) -> dict:
    return yaml.safe_load((DEPLOY / name).read_text(encoding="utf-8"))


def test_prod_db_and_qdrant_have_no_published_ports() -> None:
    prod = _load("compose.prod.yml")
    for svc_name in ("db", "qdrant"):
        svc = prod["services"][svc_name]
        assert "ports" not in svc, f"prod {svc_name} 不得发布端口"


def test_prod_internal_network_is_internal() -> None:
    prod = _load("compose.prod.yml")
    assert prod["networks"]["internal"].get("internal") is True


def test_dev_ports_bind_localhost_only() -> None:
    dev = _load("compose.dev.yml")
    for svc_name, svc in dev["services"].items():
        for mapping in svc.get("ports", []):
            host_part = str(mapping).split(":")[0]
            assert host_part == "127.0.0.1", f"dev {svc_name} 端口 {mapping} 必须绑定 127.0.0.1"
