import requests
import os
from urllib.parse import urlencode

GRAPH = "https://graph.microsoft.com/v1.0"
AUTH  = "https://login.microsoftonline.com/common/oauth2/v2.0"
SCOPES = "https://graph.microsoft.com/Mail.Read https://graph.microsoft.com/Mail.Send https://graph.microsoft.com/Mail.ReadWrite offline_access"


def _client_id() -> str:
    try:
        import streamlit as st
        return st.secrets.get("MICROSOFT_CLIENT_ID") or os.getenv("MICROSOFT_CLIENT_ID", "")
    except Exception:
        return os.getenv("MICROSOFT_CLIENT_ID", "")


def _client_secret() -> str:
    try:
        import streamlit as st
        return st.secrets.get("MICROSOFT_CLIENT_SECRET") or os.getenv("MICROSOFT_CLIENT_SECRET", "")
    except Exception:
        return os.getenv("MICROSOFT_CLIENT_SECRET", "")


def _redirect_uri() -> str:
    try:
        import streamlit as st
        url = st.secrets.get("STREAMLIT_APP_URL", "")
        if url:
            return url.rstrip("/") + "/"
    except Exception:
        pass
    return os.getenv("STREAMLIT_APP_URL", "http://localhost:8501/")


def credentials_exist() -> bool:
    return bool(_client_id() and _client_secret())


def get_auth_url() -> str:
    params = {
        "client_id":     _client_id(),
        "response_type": "code",
        "redirect_uri":  _redirect_uri(),
        "scope":         SCOPES,
        "response_mode": "query",
        "state":         "outlook_auth",
    }
    return f"{AUTH}/authorize?" + urlencode(params)


def exchange_code(code: str) -> dict:
    resp = requests.post(
        f"{AUTH}/token",
        data={
            "client_id":     _client_id(),
            "client_secret": _client_secret(),
            "code":          code,
            "redirect_uri":  _redirect_uri(),
            "grant_type":    "authorization_code",
        },
        timeout=15,
    )
    token = resp.json()
    if "error" in token:
        raise Exception(f"{token['error']}: {token.get('error_description', '')}")
    return token


def refresh_access_token(refresh_tok: str) -> dict:
    resp = requests.post(
        f"{AUTH}/token",
        data={
            "client_id":     _client_id(),
            "client_secret": _client_secret(),
            "refresh_token": refresh_tok,
            "grant_type":    "refresh_token",
        },
        timeout=15,
    )
    token = resp.json()
    if "error" in token:
        raise Exception(f"{token['error']}: {token.get('error_description', '')}")
    return token


def _h(access_token: str) -> dict:
    return {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}


def get_user_email(access_token: str) -> str:
    try:
        r = requests.get(f"{GRAPH}/me", headers=_h(access_token), timeout=10)
        r.raise_for_status()
        d = r.json()
        return d.get("mail") or d.get("userPrincipalName", "")
    except Exception:
        return ""


def list_messages(access_token: str, max_results: int = 20,
                  unread_only: bool = False) -> list[dict]:
    params = {
        "$top":     max_results,
        "$select":  "id,subject,from,receivedDateTime,bodyPreview,isRead",
        "$orderby": "receivedDateTime desc",
    }
    if unread_only:
        params["$filter"] = "isRead eq false"
    r = requests.get(
        f"{GRAPH}/me/mailFolders/inbox/messages",
        headers=_h(access_token),
        params=params,
        timeout=15,
    )
    r.raise_for_status()
    items = []
    for msg in r.json().get("value", []):
        fa = msg.get("from", {}).get("emailAddress", {})
        items.append({
            "id":       msg["id"],
            "subject":  msg.get("subject") or "（件名なし）",
            "from":     f"{fa.get('name','')} <{fa.get('address','')}>",
            "date":     msg.get("receivedDateTime", "")[:16].replace("T", " "),
            "snippet":  msg.get("bodyPreview", ""),
            "is_read":  msg.get("isRead", True),
        })
    return items


def get_message_body(access_token: str, message_id: str) -> dict:
    r = requests.get(
        f"{GRAPH}/me/messages/{message_id}",
        headers={**_h(access_token), "Prefer": "outlook.body-content-type='text'"},
        params={"$select": "id,subject,from,toRecipients,receivedDateTime,body,conversationId"},
        timeout=15,
    )
    r.raise_for_status()
    msg = r.json()
    fa = msg.get("from", {}).get("emailAddress", {})
    to = ", ".join(
        rec.get("emailAddress", {}).get("address", "")
        for rec in msg.get("toRecipients", [])
    )
    return {
        "id":      message_id,
        "subject": msg.get("subject", ""),
        "from":    f"{fa.get('name','')} <{fa.get('address','')}>",
        "to":      to,
        "date":    msg.get("receivedDateTime", "")[:16].replace("T", " "),
        "conversation_id": msg.get("conversationId", ""),
        "body":    msg.get("body", {}).get("content", ""),
    }


def send_reply(access_token: str, original: dict, reply_body: str) -> None:
    requests.post(
        f"{GRAPH}/me/messages/{original['id']}/reply",
        headers=_h(access_token),
        json={"comment": reply_body},
        timeout=15,
    ).raise_for_status()


def mark_as_read(access_token: str, message_id: str) -> None:
    try:
        requests.patch(
            f"{GRAPH}/me/messages/{message_id}",
            headers=_h(access_token),
            json={"isRead": True},
            timeout=10,
        ).raise_for_status()
    except Exception:
        pass
