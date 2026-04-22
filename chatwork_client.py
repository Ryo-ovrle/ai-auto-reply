import requests

BASE = "https://api.chatwork.com/v2"


def _headers(token: str) -> dict:
    return {"X-ChatWorkToken": token}


def get_rooms(token: str) -> list[dict]:
    try:
        res = requests.get(f"{BASE}/rooms", headers=_headers(token), timeout=10)
        res.raise_for_status()
        return res.json()
    except Exception as e:
        raise Exception(f"ルーム取得失敗: {e}")


def get_messages(token: str, room_id: str, force: bool = True) -> list[dict]:
    try:
        res = requests.get(
            f"{BASE}/rooms/{room_id}/messages",
            headers=_headers(token),
            params={"force": 1 if force else 0},
            timeout=10,
        )
        res.raise_for_status()
        return res.json() or []
    except Exception as e:
        raise Exception(f"メッセージ取得失敗: {e}")


def send_message(token: str, room_id: str, body: str) -> dict:
    try:
        res = requests.post(
            f"{BASE}/rooms/{room_id}/messages",
            headers=_headers(token),
            data={"body": body, "self_unread": 0},
            timeout=10,
        )
        res.raise_for_status()
        return res.json()
    except Exception as e:
        raise Exception(f"送信失敗: {e}")


def get_me(token: str) -> dict:
    try:
        res = requests.get(f"{BASE}/me", headers=_headers(token), timeout=10)
        res.raise_for_status()
        return res.json()
    except Exception:
        return {}
