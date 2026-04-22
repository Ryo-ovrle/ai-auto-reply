import os
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
