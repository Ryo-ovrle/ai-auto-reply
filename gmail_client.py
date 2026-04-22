import base64
import re
import os
import json
import tempfile
from typing import Optional, Tuple
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
TOKEN_FILE = "token.json"
CREDENTIALS_FILE = "credentials.json"
REDIRECT_URI = "http://localhost:8501/"


def _get_credentials_file() -> Optional[str]:
    """credentials.jsonがなければStreamlit SecretsのGOOGLE_CREDENTIALSから一時ファイルを作成"""
    if os.path.exists(CREDENTIALS_FILE):
        return CREDENTIALS_FILE
    creds_json = os.getenv("GOOGLE_CREDENTIALS")
    if creds_json:
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        tmp.write(creds_json)
        tmp.flush()
        return tmp.name
    return None


def credentials_exist() -> bool:
    return _get_credentials_file() is not None


def token_exists() -> bool:
    return os.path.exists(TOKEN_FILE)


def get_auth_url() -> Tuple[str, object]:
    flow = Flow.from_client_secrets_file(
        _get_credentials_file(),
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI,
    )
    auth_url, _ = flow.authorization_url(
        prompt="consent",
        access_type="offline",
        include_granted_scopes="true",
    )
    return auth_url, flow


def exchange_code(flow, code: str) -> Credentials:
    flow.fetch_token(code=code)
    creds = flow.credentials
    with open(TOKEN_FILE, "w") as f:
        f.write(creds.to_json())
    return creds


def load_credentials() -> Optional[Credentials]:
    if not token_exists():
        return None
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return creds if creds and creds.valid else None


def build_service(creds: Credentials):
    return build("gmail", "v1", credentials=creds)


def list_messages(service, max_results: int = 20, label: str = "INBOX") -> list[dict]:
    result = (
        service.users()
        .messages()
        .list(userId="me", labelIds=[label], maxResults=max_results)
        .execute()
    )
    messages = result.get("messages", [])
    items = []
    for msg in messages:
        detail = (
            service.users()
            .messages()
            .get(userId="me", id=msg["id"], format="metadata",
                 metadataHeaders=["Subject", "From", "Date"])
            .execute()
        )
        headers = {h["name"]: h["value"] for h in detail["payload"]["headers"]}
        items.append({
            "id": msg["id"],
            "threadId": detail["threadId"],
            "subject": headers.get("Subject", "（件名なし）"),
            "from": headers.get("From", ""),
            "date": headers.get("Date", ""),
            "snippet": detail.get("snippet", ""),
            "labelIds": detail.get("labelIds", []),
        })
    return items


def get_message_body(service, message_id: str) -> dict:
    msg = (
        service.users()
        .messages()
        .get(userId="me", id=message_id, format="full")
        .execute()
    )
    headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}
    body = _extract_text(msg["payload"])
    return {
        "id": message_id,
        "threadId": msg["threadId"],
        "subject": headers.get("Subject", ""),
        "from": headers.get("From", ""),
        "to": headers.get("To", ""),
        "date": headers.get("Date", ""),
        "message_id_header": headers.get("Message-ID", ""),
        "references": headers.get("References", ""),
        "body": body,
    }


def _extract_text(payload: dict) -> str:
    mime = payload.get("mimeType", "")
    if mime == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            return base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    if mime == "text/html":
        data = payload.get("body", {}).get("data", "")
        if data:
            html = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
            return re.sub(r"<[^>]+>", "", html).strip()
    text = ""
    for part in payload.get("parts", []):
        extracted = _extract_text(part)
        if extracted:
            if "text/plain" in part.get("mimeType", ""):
                return extracted
            text = text or extracted
    return text


def send_reply(service, original: dict, reply_body: str) -> dict:
    msg = MIMEMultipart()
    subject = original["subject"]
    if not subject.lower().startswith("re:"):
        subject = "Re: " + subject

    # Reply-to sender
    sender_email = re.search(r"<(.+?)>", original["from"])
    to_addr = sender_email.group(1) if sender_email else original["from"]

    msg["To"] = to_addr
    msg["Subject"] = subject
    if original.get("message_id_header"):
        msg["In-Reply-To"] = original["message_id_header"]
        refs = original.get("references", "")
        msg["References"] = (refs + " " + original["message_id_header"]).strip()

    msg.attach(MIMEText(reply_body, "plain", "utf-8"))
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

    sent = (
        service.users()
        .messages()
        .send(userId="me", body={"raw": raw, "threadId": original["threadId"]})
        .execute()
    )
    return sent


def mark_as_read(service, message_id: str):
    service.users().messages().modify(
        userId="me",
        id=message_id,
        body={"removeLabelIds": ["UNREAD"]},
    ).execute()
