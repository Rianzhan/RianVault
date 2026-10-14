"""导入后自动建索引的**串行化**约束。

背景（真实事故）：bge-m3 建索引要走 torch 推理，两个线程同时推理会把整个进程搞崩
（access violation / 段错误，没有任何 Python 异常可以捕获）。
连着一次性导入十几个文件时，每个导入各起一个线程一起推理 → 必崩。
所以约定：**任一时刻只允许一个索引 worker 在跑**，后来的导入排队补一轮。

本文件把这条约束钉死，防止以后有人改成"每个导入各起一个线程"。
"""

from __future__ import annotations

import threading
import time

from app.api.routes import imports as imports_mod
from app.services import index_service


class FakeIndexState:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.passes = 0

    def fake_index_messages(self, db, **_kwargs):
        # 若出现并发，active 会在 sleep 期间被第二个线程抬到 2
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        self.passes += 1
        time.sleep(0.05)  # 留出第二个 schedule 撞进来的窗口
        self.active -= 1
        return {
            "messages": 0,
            "chunks": 0,
            "upserted": 0,
            "skipped_empty": 0,
            "model": "fake",
        }


def _reset_module_state() -> None:
    imports_mod._auto_index_running = False
    imports_mod._auto_index_pending = False


def test_concurrent_imports_do_not_run_two_indexers(monkeypatch) -> None:
    """连续两次安排索引：绝不能同时跑两个 worker，但两批都得建到。"""
    _reset_module_state()
    state = FakeIndexState()
    monkeypatch.setattr(index_service, "index_messages", state.fake_index_messages)

    imports_mod.schedule_auto_index()
    imports_mod.schedule_auto_index()  # 第二次应标记 pending，而不是再开一个线程

    deadline = time.time() + 5
    while time.time() < deadline and state.passes < 2:
        time.sleep(0.02)

    assert state.passes >= 2, "第二次安排的索引也必须跑到（pending 要被消费）"
    assert state.max_active == 1, "出现了并发建索引：会有段错误风险"

    # worker 收工后状态必须复位，否则之后的导入永远不会再自动建索引
    deadline = time.time() + 5
    while time.time() < deadline and imports_mod._auto_index_running:
        time.sleep(0.02)
    assert imports_mod._auto_index_running is False
    assert imports_mod._auto_index_pending is False


def test_auto_index_off_in_tests_so_no_real_model_loaded() -> None:
    """测试环境必须关掉自动建索引（否则拉真的 bge-m3，慢且崩）。"""
    from app.core.config import get_settings

    assert get_settings().auto_index_after_import is False


def test_only_one_auto_index_thread_is_ever_started(monkeypatch) -> None:
    """连着安排 5 次，最终也只应存在过一个叫 auto-index 的活跃线程。"""

    def count_alive() -> int:
        return sum(1 for t in threading.enumerate() if t.name == "auto-index" and t.is_alive())

    _reset_module_state()
    state = FakeIndexState()
    monkeypatch.setattr(index_service, "index_messages", state.fake_index_messages)

    for _ in range(5):
        imports_mod.schedule_auto_index()
        time.sleep(0.01)  # 让 worker 进入运行态，确保后续安排都会撞上"有人在跑"

    assert count_alive() <= 1, "同时存在多个 auto-index 线程（并发 torch 会崩进程）"

    deadline = time.time() + 5
    while time.time() < deadline and imports_mod._auto_index_running:
        time.sleep(0.02)
    assert imports_mod._auto_index_running is False
    assert state.max_active == 1
