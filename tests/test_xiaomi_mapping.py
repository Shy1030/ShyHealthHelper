from __future__ import annotations

import datetime
import json
import time

from app.config import settings
from app.xiaomi import service

TZ = datetime.timezone(datetime.timedelta(hours=8))


class FakeClient:
    def __init__(self, payloads):
        self.payloads = payloads

    def get_fitness_data_all(self, key, start_ms, end_ms, max_pages=200):
        return {"data_list": self.payloads.get(key, []), "has_more": False}

    def get_sport_records_all(self, start_ms, end_ms, max_pages=100):
        return {"sport_records": self.payloads.get("sport", []), "has_more": False}


class FakeCookies(dict):
    def get(self, key, default=None, domain=None, **kwargs):
        return super().get(key, default)


class FakeSession:
    def __init__(self):
        self.cookies = FakeCookies()


class FakeResponse:
    def __init__(self, text: str = "", headers=None, status_code: int = 200):
        self.text = text
        self.headers = headers or {}
        self.status_code = status_code

    def json(self):
        return json.loads(self.text) if self.text else {}


def test_finish_2fa_happy_path(monkeypatch):
    from app.xiaomi import login

    def fake_id_call(session, method, url, step, **kwargs):
        assert "verify" in url
        return FakeResponse(
            json.dumps(
                {
                    "location": "https://account.xiaomi.com/identity/result/check?context=abc"
                }
            )
        )

    def fake_req(session, method, url, tries=3, **kwargs):
        if "identity/result/check" in url:
            return FakeResponse(
                headers={
                    "Location": "https://account.xiaomi.com/pass/serviceLoginAuth2/end?x=1"
                }
            )
        if "serviceLoginAuth2/end" in url:
            return FakeResponse(
                headers={
                    "extension-pragma": json.dumps({"ssecurity": "c2Vj"}),
                    "Location": "https://sts-hlth.io.mi.com/healthapp/sts?ticket=1",
                }
            )
        if "pass/serviceLogin" in url:
            return FakeResponse(
                json.dumps(
                    {
                        "code": 0,
                        "ssecurity": "c2Vj",
                        "location": "https://sts-hlth.io.mi.com/healthapp/sts?ticket=1",
                        "cUserId": "cuser",
                        "userId": "user",
                        "passToken": "pass",
                    }
                )
            )
        if "sts-hlth" in url:
            session.cookies["serviceToken"] = "service-token"
            return FakeResponse()
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(login, "_id_call", fake_id_call)
    monkeypatch.setattr(login, "_req", fake_req)
    tokens = login.finish_2fa(FakeSession(), "123456", "context", flag=8)
    assert tokens["ssecurity"] == "c2Vj"
    assert tokens["service_token"] == "service-token"
    assert tokens["cuser_id"] == "cuser"
    assert tokens["user_id"] == "user"
    assert tokens["pass_token"] == "pass"


def test_finish_2fa_handles_302_redirect(monkeypatch):
    from app.xiaomi import login

    def fake_id_call(session, method, url, step, **kwargs):
        return FakeResponse(
            json.dumps(
                {
                    "location": "https://account.xiaomi.com/identity/result/check?context=abc"
                }
            )
        )

    def fake_req(session, method, url, tries=3, **kwargs):
        if "identity/result/check" in url:
            return FakeResponse(
                status_code=302,
                headers={
                    "Location": "https://account.xiaomi.com/pass/serviceLoginAuth2/end?x=1"
                },
            )
        if "serviceLoginAuth2/end" in url:
            return FakeResponse(
                status_code=302,
                headers={"Location": "https://sts-hlth.io.mi.com/healthapp/sts?ticket=1"},
            )
        if "pass/serviceLogin" in url:
            return FakeResponse(
                json.dumps(
                    {
                        "code": 0,
                        "ssecurity": "c2Vj",
                        "location": "https://sts-hlth.io.mi.com/healthapp/sts?ticket=1",
                        "cUserId": "cuser",
                        "userId": "user",
                        "passToken": "pass",
                    }
                )
            )
        if "sts-hlth" in url:
            session.cookies["serviceToken"] = "service-token"
            return FakeResponse()
        raise AssertionError(f"unexpected url: {url}")

    monkeypatch.setattr(login, "_id_call", fake_id_call)
    monkeypatch.setattr(login, "_req", fake_req)
    tokens = login.finish_2fa(FakeSession(), "123456", "context", flag=8)
    assert tokens["ssecurity"] == "c2Vj"
    assert tokens["service_token"] == "service-token"


def make_payloads():
    now = int(datetime.datetime.now(TZ).timestamp())
    today = int(
        datetime.datetime.now(TZ)
        .replace(hour=12, minute=0, second=0, microsecond=0)
        .timestamp()
    )
    yesterday = today - 86400
    return {
        "steps": [
            {
                "time": today,
                "zone_offset": 28800,
                "value": json.dumps({"steps": 1200, "calories": 60}),
            },
            {
                "time": today - 60,
                "zone_offset": 28800,
                "value": json.dumps({"steps": 800, "calories": 30}),
            },
            {
                "time": yesterday,
                "zone_offset": 28800,
                "value": json.dumps({"steps": 5000, "calories": 200}),
            },
        ],
        "weight": [
            {
                "time": today,
                "zone_offset": 28800,
                "value": json.dumps(
                    {"weight": 58.2, "body_fat_rate": 24.1, "muscle_rate": 40.5}
                ),
            }
        ],
        "sleep": [
            {
                "time": today,
                "zone_offset": 28800,
                "value": json.dumps(
                    {
                        "bedtime": today - 3600 * 7,
                        "device_wake_up_time": today,
                        "sleep_deep_duration": 120,
                        "sleep_light_duration": 240,
                        "sleep_rem_duration": 60,
                    }
                ),
            }
        ],
        "sport": [
            {
                "time": today - 7200,
                "key": "outdoor_running",
                "zone_offset": 28800,
                "value": json.dumps(
                    {
                        "duration": 1800,
                        "distance": 5000,
                        "calories": 300,
                        "avg_hrm": 140,
                        "steps": 5200,
                    }
                ),
            }
        ],
    }


def test_xiaomi_mapping_into_body_and_exercise(client):
    payloads = make_payloads()
    fake = FakeClient(payloads)
    now = int(time.time() * 1000)
    start = now - 7 * 86400 * 1000

    result = service._sync_from_client(fake, start, now, 7)
    assert result["steps_days"] == 2
    assert result["weight_records"] == 1
    assert result["sleep_days"] == 1
    assert result["sport_records"] == 1

    records = client.get("/api/body/records?limit=10").json()["items"]
    by_date = {item["record_date"]: item for item in records}
    assert len(by_date) == 2

    today_record = sorted(records, key=lambda item: item["record_date"], reverse=True)[0]
    assert today_record["weight_kg"] == 58.2
    assert today_record["body_fat_pct"] == 24.1
    assert today_record["sleep_hours"] == 7.0
    assert today_record["steps"] == 2000

    logs = client.get("/api/exercise/logs").json()["items"]
    assert len(logs) == 1
    log = logs[0]
    assert log["activity"] == "跑步"
    assert log["duration_min"] == 30.0
    assert log["distance_km"] == 5.0
    assert log["calories"] == 300.0
    assert log["avg_heart_rate"] == 140
    assert log["source"] == "xiaomi"
    assert log["source_label"] == "小米手环"

    duplicate = service._sync_from_client(fake, start, now, 7)
    assert duplicate["sport_records"] == 0
    assert len(client.get("/api/exercise/logs").json()["items"]) == 1


def test_xiaomi_login_encrypts_credentials_and_logout(client, monkeypatch):
    client.post("/api/xiaomi/logout")

    def fake_login(username, password, **kwargs):
        return {
            "ssecurity": "c2VjdXJpdHk=",
            "service_token": "service-token-value",
            "cuser_id": "cuser-1",
            "user_id": "user-1",
            "pass_token": "pass-token-value",
            "ts": int(time.time()),
        }

    monkeypatch.setattr(service, "login_with_password", fake_login)
    response = client.post(
        "/api/xiaomi/login",
        json={"username": "demo@example.com", "password": "secret-pass", "region": "cn"},
    )
    assert response.status_code == 200
    assert response.json()["connected"] is True

    status = client.get("/api/xiaomi/status").json()
    assert status["connected"] is True
    assert status["username"] == "demo@example.com"
    assert status["has_password"] is True
    assert status["has_pass_token"] is True

    encrypted = settings.data_dir / "xiaomi_credentials.enc"
    assert encrypted.is_file()
    assert b"secret-pass" not in encrypted.read_bytes()
    assert b"demo@example.com" not in encrypted.read_bytes()

    logged_out = client.post("/api/xiaomi/logout").json()
    assert logged_out["connected"] is False
    assert client.get("/api/xiaomi/status").json()["connected"] is False
