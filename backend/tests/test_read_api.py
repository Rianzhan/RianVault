from conftest import read_fixture
from fastapi.testclient import TestClient


def _import_sample(client: TestClient) -> dict:
    resp = client.post(
        "/api/imports",
        files={"file": ("conversations.json", read_fixture("chatgpt_export_sample.json"))},
    )
    assert resp.status_code == 200
    return resp.json()


class TestImportApi:
    def test_post_and_repost(self, client: TestClient) -> None:
        report = _import_sample(client)
        assert report["already_imported"] is False
        assert report["import_"]["status"] == "completed"

        again = client.post(
            "/api/imports",
            files={"file": ("conversations.json", read_fixture("chatgpt_export_sample.json"))},
        ).json()
        assert again["already_imported"] is True
        assert again["import_"]["id"] == report["import_"]["id"]

    def test_list_and_detail(self, client: TestClient) -> None:
        report = _import_sample(client)
        listing = client.get("/api/imports").json()
        assert len(listing) == 1
        detail = client.get(f"/api/imports/{report['import_']['id']}").json()
        assert detail["import_"]["stats"]["imported"] == 4

    def test_unrecognized_file_400(self, client: TestClient) -> None:
        resp = client.post(
            "/api/imports", files={"file": ("broken.json", read_fixture("broken.json"))}
        )
        assert resp.status_code == 400
        assert "无法识别" in resp.json()["detail"]

    def test_malformed_file_reports_failed_not_success(self, client: TestClient) -> None:
        resp = client.post(
            "/api/imports",
            files={"file": ("bad.json", read_fixture("chatgpt_malformed.json"))},
        )
        assert resp.status_code == 200  # 请求本身被处理
        body = resp.json()
        assert body["import_"]["status"] == "failed"  # 但结果绝不伪装成功
        assert body["import_"]["error"]


class TestConversationRead:
    def test_list_and_messages(self, client: TestClient) -> None:
        _import_sample(client)
        convs = client.get("/api/conversations").json()
        assert len(convs) == 1
        conv = convs[0]
        assert conv["message_count"] == 4
        assert conv["title"] == "合成测试会话"

        msgs = client.get(f"/api/conversations/{conv['id']}/messages").json()
        assert [m["source_message_id"] for m in msgs] == [
            "msg-u1",
            "msg-a1",
            "msg-u2",
            "msg-a2",
        ]
        assert msgs[1]["source_model"] == "gpt-4"
        assert msgs[1]["model_label_source"] == "export"
        # event_time（2023 发生的事）与 ingested_at（现在导入）分离
        assert msgs[0]["event_time"].startswith("2023-")
        assert not msgs[0]["ingested_at"].startswith("2023-")

    def test_around_window(self, client: TestClient) -> None:
        _import_sample(client)
        conv = client.get("/api/conversations").json()[0]
        msgs = client.get(f"/api/conversations/{conv['id']}/messages").json()
        anchor = msgs[2]  # msg-u2
        windowed = client.get(
            f"/api/conversations/{conv['id']}/messages",
            params={"around": anchor["id"], "window": 1},
        ).json()
        assert [m["source_message_id"] for m in windowed] == ["msg-a1", "msg-u2", "msg-a2"]

    def test_get_single_message(self, client: TestClient) -> None:
        _import_sample(client)
        conv = client.get("/api/conversations").json()[0]
        msgs = client.get(f"/api/conversations/{conv['id']}/messages").json()
        one = client.get(f"/api/messages/{msgs[0]['id']}").json()
        assert one["content_text"] == "你好，这是第一条。"

    def test_404s(self, client: TestClient) -> None:
        import uuid

        bad = uuid.uuid4()
        assert client.get(f"/api/conversations/{bad}").status_code == 404
        assert client.get(f"/api/messages/{bad}").status_code == 404
        assert client.get(f"/api/imports/{bad}").status_code == 404
