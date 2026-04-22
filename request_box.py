import os
import hashlib
import base64
import streamlit as st

def _client():
    try:
        from supabase import create_client
        url = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL", "")
        key = st.secrets.get("SUPABASE_KEY") or os.getenv("SUPABASE_KEY", "")
        if url and key:
            return create_client(url, key)
    except Exception:
        pass
    return None


def get_requests() -> list[dict]:
    client = _client()
    if not client:
        return []
    try:
        res = client.table("requests").select("*").order("likes", desc=True).execute()
        return res.data or []
    except Exception:
        return []


def submit_request(text: str, session_id: str) -> bool:
    client = _client()
    if not client or not text.strip():
        return False
    try:
        client.table("requests").insert({
            "text": text.strip(),
            "likes": 0,
            "liked_by": [],
        }).execute()
        return True
    except Exception:
        return False


def _user_id(email: str) -> str:
    return hashlib.sha256(email.lower().encode()).hexdigest()


def _encrypt(text: str, key: str) -> str:
    k = hashlib.sha256(key.encode()).digest()
    tb = text.encode("utf-8")
    enc = bytes(tb[i] ^ k[i % 32] for i in range(len(tb)))
    return base64.b64encode(enc).decode()


def _decrypt(enc_text: str, key: str) -> str:
    try:
        k = hashlib.sha256(key.encode()).digest()
        enc = base64.b64decode(enc_text.encode())
        dec = bytes(enc[i] ^ k[i % 32] for i in range(len(enc)))
        return dec.decode("utf-8")
    except Exception:
        return "（復号できませんでした）"


def save_history(channel: str, to: str, subject: str, body: str, user_email: str) -> bool:
    client = _client()
    if not client or not user_email:
        return False
    try:
        client.table("reply_history").insert({
            "user_id": _user_id(user_email),
            "channel": channel,
            "to_address": to,
            "subject": subject,
            "body_enc": _encrypt(body, user_email),
        }).execute()
        return True
    except Exception:
        return False


def get_history(user_email: str) -> list[dict]:
    client = _client()
    if not client or not user_email:
        return []
    try:
        res = (
            client.table("reply_history")
            .select("*")
            .eq("user_id", _user_id(user_email))
            .gte("created_at", "now() - interval '72 hours'")
            .order("created_at", desc=True)
            .limit(100)
            .execute()
        )
        rows = res.data or []
        for row in rows:
            row["body"] = _decrypt(row.get("body_enc", ""), user_email)
        return rows
    except Exception:
        return []


def toggle_like(request_id: int, session_id: str) -> bool:
    client = _client()
    if not client:
        return False
    try:
        res = client.table("requests").select("likes,liked_by").eq("id", request_id).execute()
        if not res.data:
            return False
        row = res.data[0]
        liked_by = row.get("liked_by") or []
        if session_id in liked_by:
            liked_by.remove(session_id)
            new_likes = max(0, row["likes"] - 1)
        else:
            liked_by.append(session_id)
            new_likes = row["likes"] + 1
        client.table("requests").update({
            "likes": new_likes,
            "liked_by": liked_by,
        }).eq("id", request_id).execute()
        return True
    except Exception:
        return False
