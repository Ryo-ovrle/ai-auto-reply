import requests


def send_line_message(to_user_id: str, message: str, channel_access_token: str) -> dict:
    url = "https://api.line.me/v2/bot/message/push"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {channel_access_token}",
    }
    payload = {
        "to": to_user_id,
        "messages": [{"type": "text", "text": message}],
    }
    resp = requests.post(url, json=payload, headers=headers, timeout=10)
    return {"status_code": resp.status_code, "body": resp.text}


def verify_token(channel_access_token: str) -> bool:
    url = "https://api.line.me/v2/bot/info"
    headers = {"Authorization": f"Bearer {channel_access_token}"}
    resp = requests.get(url, headers=headers, timeout=10)
    return resp.status_code == 200
