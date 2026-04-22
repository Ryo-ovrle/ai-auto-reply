import imaplib
import smtplib
import email as _email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import decode_header as _decode_header
import re

IMAP_SERVER = "outlook.office365.com"
SMTP_SERVER = "smtp.office365.com"
IMAP_PORT = 993
SMTP_PORT = 587


def _decode_str(s: str) -> str:
    if not s:
        return ""
    parts = _decode_header(s)
    result = ""
    for part, charset in parts:
        if isinstance(part, bytes):
            result += part.decode(charset or "utf-8", errors="replace")
        else:
            result += str(part)
    return result


def _imap(email_addr: str, password: str):
    mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
    mail.login(email_addr, password)
    return mail


def test_login(email_addr: str, password: str) -> bool:
    try:
        mail = _imap(email_addr, password)
        mail.logout()
        return True
    except Exception:
        return False


def list_messages(email_addr: str, password: str,
                  max_results: int = 20, unread_only: bool = False) -> list[dict]:
    mail = _imap(email_addr, password)
    mail.select("INBOX")
    criteria = "UNSEEN" if unread_only else "ALL"
    _, data = mail.uid("SEARCH", None, criteria)
    uids = data[0].split()
    uids = uids[-max_results:][::-1]

    items = []
    for uid in uids:
        _, raw = mail.uid("FETCH", uid,
                          "(FLAGS BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])")
        if not raw or not raw[0] or not isinstance(raw[0], tuple):
            continue
        msg = _email.message_from_bytes(raw[0][1])
        flags_str = raw[0][0].decode(errors="replace") if raw[0][0] else ""
        is_read = "\\Seen" in flags_str
        items.append({
            "id": uid.decode(),
            "subject": _decode_str(msg.get("Subject")) or "（件名なし）",
            "from": _decode_str(msg.get("From", "")),
            "date": msg.get("Date", "")[:25],
            "message_id_header": msg.get("Message-ID", ""),
            "is_read": is_read,
            "snippet": "",
        })
    mail.logout()
    return items


def get_message_body(email_addr: str, password: str, uid: str) -> dict:
    mail = _imap(email_addr, password)
    mail.select("INBOX")
    _, raw = mail.uid("FETCH", uid.encode(), "(RFC822)")
    mail.logout()

    if not raw or not raw[0] or not isinstance(raw[0], tuple):
        return {}

    msg = _email.message_from_bytes(raw[0][1])
    body = _extract_text(msg)
    return {
        "id": uid,
        "subject": _decode_str(msg.get("Subject", "")),
        "from": _decode_str(msg.get("From", "")),
        "to": _decode_str(msg.get("To", "")),
        "date": msg.get("Date", "")[:25],
        "message_id_header": msg.get("Message-ID", ""),
        "references": msg.get("References", ""),
        "body": body,
    }


def _extract_text(msg) -> str:
    plain = ""
    html = ""
    for part in msg.walk():
        ct = part.get_content_type()
        if ct == "text/plain" and not plain:
            payload = part.get_payload(decode=True)
            charset = part.get_content_charset() or "utf-8"
            plain = payload.decode(charset, errors="replace") if payload else ""
        elif ct == "text/html" and not html:
            payload = part.get_payload(decode=True)
            charset = part.get_content_charset() or "utf-8"
            raw_html = payload.decode(charset, errors="replace") if payload else ""
            html = re.sub(r"<[^>]+>", "", raw_html).strip()
    return plain or html


def send_reply(email_addr: str, password: str, original: dict, reply_body: str) -> None:
    msg = MIMEMultipart()
    subject = original.get("subject", "")
    if not subject.lower().startswith("re:"):
        subject = "Re: " + subject

    m = re.search(r"<(.+?)>", original.get("from", ""))
    to_addr = m.group(1) if m else original.get("from", "")

    msg["From"] = email_addr
    msg["To"] = to_addr
    msg["Subject"] = subject
    mid = original.get("message_id_header", "")
    if mid:
        msg["In-Reply-To"] = mid
        refs = original.get("references", "")
        msg["References"] = (refs + " " + mid).strip()

    msg.attach(MIMEText(reply_body, "plain", "utf-8"))

    with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
        server.ehlo()
        server.starttls()
        server.login(email_addr, password)
        server.send_message(msg)


def mark_as_read(email_addr: str, password: str, uid: str) -> None:
    try:
        mail = _imap(email_addr, password)
        mail.select("INBOX")
        mail.uid("STORE", uid.encode(), "+FLAGS", "\\Seen")
        mail.logout()
    except Exception:
        pass
