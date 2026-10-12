"""首页统计：只给计数，不给正文（日志/响应都不允许夹带私人文本）。"""


def test_stats_returns_counts_only(client, seeded_stats) -> None:
    r = client.get("/api/stats")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["conversations"] == 1
    assert body["messages"] >= 4
    assert body["memories"] == 1
    assert body["spans"] == 1
    assert body["unreviewed_candidates"] == 0
    assert body["actor"] == "owner"
    # 统计接口不得返回任何正文字段
    assert "content_text" not in str(body)
    assert "body" not in str(body)


def test_stats_requires_token(anon_client) -> None:
    assert anon_client.get("/api/stats").status_code == 401


def test_stats_excludes_deleted_memories(client, seeded_stats, db_session) -> None:
    from sqlalchemy import select

    from app.models import Memory

    mem = db_session.scalars(select(Memory)).first()
    r = client.request("DELETE", f"/api/memories/{mem.id}", json={})
    assert r.status_code == 200, r.text
    assert client.get("/api/stats").json()["memories"] == 0
