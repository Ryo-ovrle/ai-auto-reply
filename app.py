import streamlit as st
import os
import re
import time
from datetime import datetime
from dotenv import load_dotenv

import groq_client
import gmail_client
import line_client
import chatwork_client
import outlook_client
import request_box

load_dotenv()

st.set_page_config(
    page_title="REPLAI",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;700;800&display=swap');

.brand-title {
    font-family: 'Space Grotesk', -apple-system, 'Helvetica Neue', sans-serif;
    font-size: 5.5rem !important;
    font-weight: 900 !important;
    font-style: normal;
    letter-spacing: -0.04em;
    line-height: 1;
    margin-bottom: 0;
    display: inline-block;
    transform: skewX(-10deg);
}
.brand-repl {
    background: linear-gradient(135deg, #6366f1 0%, #a855f7 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.brand-ai {
    background: linear-gradient(135deg, #a855f7 0%, #ec4899 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
}
.brand-sub {
    color: #94a3b8;
    font-size: 0.85rem;
    margin-top: 2px;
    letter-spacing: 0.05em;
    text-transform: uppercase;
}
.success-badge {
    background: #dcfce7; color: #16a34a;
    padding: 3px 10px; border-radius: 20px; font-size: 0.82rem;
}
.auto-badge {
    background: #fef3c7; color: #d97706;
    padding: 3px 10px; border-radius: 20px; font-size: 0.82rem; font-weight: 600;
}
</style>
""", unsafe_allow_html=True)


# ── Session defaults ──────────────────────────────────────────────────────────
def _init():
    defaults = {
        "groq_api_key": os.getenv("GROQ_API_KEY", ""),
        "line_token": os.getenv("LINE_CHANNEL_ACCESS_TOKEN", ""),
        "line_user_id": os.getenv("LINE_USER_ID", ""),
        "gmail_service": None,
        "selected_msg": None,
        "generated_reply": "",
        "reply_history": [],
        "gmail_messages": [],
        "sender_tones": {},
        "scroll_to_reply": False,
        "page": "gmail",
        "gmail_email": "",
        "cw_token": os.getenv("CHATWORK_API_TOKEN", ""),
        "cw_rooms": [],
        "cw_selected_room": None,
        "cw_messages": [],
        "cw_selected_msg": None,
        "cw_reply": "",
        "ol_email": "",
        "ol_password": "",
        "ol_messages": [],
        "ol_selected_msg": None,
        "ol_generated_reply": "",
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init()

# Gmailサービスがあるのにemailが空なら取得
if st.session_state.gmail_service and not st.session_state.gmail_email:
    st.session_state.gmail_email = gmail_client.get_user_email(st.session_state.gmail_service)


# ── Helpers ───────────────────────────────────────────────────────────────────
def extract_email(sender: str) -> str:
    m = re.search(r"<(.+?)>", sender)
    return m.group(1).lower() if m else sender.lower().strip()

def get_tone_for_sender(sender: str) -> str:
    email = extract_email(sender)
    return st.session_state.sender_tones.get(email, list(groq_client.TONES.keys())[0])

def _user_key() -> str:
    """履歴の保存・取得に使うユーザー識別キー。Gmail優先、なければOutlookメール。"""
    return st.session_state.gmail_email or st.session_state.ol_email

def do_generate(original_text: str, extra: str = "", tone: str = "", length: str = "普通") -> str:
    if not tone:
        tone = list(groq_client.TONES.keys())[0]
    if not st.session_state.groq_api_key or not original_text.strip():
        return ""
    with st.spinner("⚡ AIが返信文を生成中..."):
        try:
            return groq_client.generate_reply(
                original_message=original_text,
                tone=tone,
                instruction=extra,
                language="日本語",
                api_key=st.session_state.groq_api_key,
                model="llama-3.3-70b-versatile",
                length=length,
            )
        except Exception as e:
            st.error(f"生成エラー: {e}")
            return ""

def do_send(msg: dict, reply_text: str):
    gmail_client.send_reply(st.session_state.gmail_service, msg, reply_text)
    gmail_client.mark_as_read(st.session_state.gmail_service, msg["id"])
    st.session_state.reply_history.append({
        "time": datetime.now().strftime("%H:%M"),
        "channel": "Gmail",
        "to": msg["from"],
        "subject": msg["subject"],
    })
    request_box.save_history("Gmail", msg["from"], msg["subject"], reply_text, _user_key())
    st.session_state.selected_msg = None
    st.session_state.generated_reply = ""
    st.session_state.gmail_messages = []


# ── OAuth callback ────────────────────────────────────────────────────────────
params = st.query_params
if "code" in params:
    try:
        creds = gmail_client.exchange_code(None, params["code"])
        svc = gmail_client.build_service(creds)
        st.session_state.gmail_service = svc
        st.session_state.gmail_email = gmail_client.get_user_email(svc)
        st.query_params.clear()
        st.rerun()
    except Exception as e:
        st.error(f"Gmail認証エラー: {e}")
        st.query_params.clear()


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown(
        '<p class="brand-title"><span class="brand-repl">repl</span><span class="brand-ai">AI</span></p>',
        unsafe_allow_html=True
    )
    st.divider()

    # ナビゲーション
    st.markdown("### メニュー")
    pages = {
        "gmail":     "📧 Gmail",
        "outlook":   "📮 Outlook",
        "chatwork":  "💼 Chatwork",
        "request":   "💡 リクエストボックス",
        "history":   "🕘 返信履歴",
        "guide":     "📖 できること",
        "settings":  "⚙️ 設定",
    }
    for key, label in pages.items():
        is_active = st.session_state.page == key
        if st.button(label, use_container_width=True, type="primary" if is_active else "secondary", key=f"nav_{key}"):
            st.session_state.page = key
            st.rerun()

    st.divider()

    # Gmail連携
    if st.session_state.gmail_service:
        st.markdown('<span class="success-badge">✅ Gmail連携済み</span>', unsafe_allow_html=True)
        if st.button("🔓 連携解除", use_container_width=True):
            st.session_state.gmail_service = None
            st.session_state.gmail_messages = []
            st.session_state.selected_msg = None
            st.rerun()
    else:
        pass

    # Outlook連携
    if st.session_state.ol_email and st.session_state.ol_password:
        st.markdown('<span class="success-badge">✅ Outlook連携済み</span>', unsafe_allow_html=True)
        if st.button("🔓 Outlook解除", use_container_width=True):
            st.session_state.ol_email = ""
            st.session_state.ol_password = ""
            st.session_state.ol_messages = []
            st.session_state.ol_selected_msg = None
            st.rerun()


# ── Header ────────────────────────────────────────────────────────────────────
st.markdown('<p class="brand-sub">AI-Powered Instant Reply</p>', unsafe_allow_html=True)
st.divider()

page = st.session_state.page


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: Gmail
# ═══════════════════════════════════════════════════════════════════════════════
if page == "gmail":
    if not st.session_state.gmail_service:
        if gmail_client.credentials_exist():
            auth_url, _ = gmail_client.get_auth_url()
            st.markdown(f"### [🔗 Gmailを連携する]({auth_url})")
            st.caption("認証後、自動でこのページに戻ります。")
        else:
            st.info("Google認証情報が設定されていません。管理者にお問い合わせください。")
    else:
        col_list, col_detail = st.columns([1, 1.6], gap="large")

        # ── メール一覧 ──────────────────────────────────────────────────────
        with col_list:
            st.markdown("#### 📥 受信トレイ")
            col_r1, col_r2 = st.columns([2, 1])
            with col_r1:
                label_filter = st.selectbox("フィルター", ["INBOX", "UNREAD"],
                                             label_visibility="collapsed", key="gmail_filter")
            with col_r2:
                if st.button("🔄", use_container_width=True):
                    st.session_state.gmail_messages = []

            if st.session_state.get("_gmail_filter_prev") != label_filter:
                st.session_state.gmail_messages = []
                st.session_state["_gmail_filter_prev"] = label_filter

            if not st.session_state.gmail_messages:
                with st.spinner("読み込み中..."):
                    try:
                        st.session_state.gmail_messages = gmail_client.list_messages(
                            st.session_state.gmail_service, max_results=20, label=label_filter)
                    except Exception as e:
                        st.error(f"取得エラー: {e}")

            for msg in st.session_state.gmail_messages:
                is_unread = "UNREAD" in msg.get("labelIds", [])
                is_selected = (st.session_state.selected_msg is not None
                               and st.session_state.selected_msg.get("id") == msg["id"])
                left_border = "3px solid #6366f1" if is_selected else ("3px solid #3b82f6" if is_unread else "3px solid transparent")
                bg = "#1e1b4b10" if is_selected else ""
                st.markdown(
                    f"""<div style="border-left:{left_border};background:{bg};border-radius:6px;
                    padding:0.55rem 0.8rem;margin-bottom:0.35rem;">
                    <b style="font-size:0.88rem">{'🔵 ' if is_unread else ''}{msg['subject'][:38]}</b><br>
                    <small style="color:#64748b">{msg['from'][:35]}</small><br>
                    <small style="color:#94a3b8">{msg['snippet'][:55]}...</small>
                    </div>""",
                    unsafe_allow_html=True,
                )
                if st.button("選択 →", key=f"sel_{msg['id']}", use_container_width=True):
                    with st.spinner("取得中..."):
                        try:
                            full = gmail_client.get_message_body(
                                st.session_state.gmail_service, msg["id"])
                            st.session_state.selected_msg = full
                            st.session_state.generated_reply = ""
                            st.session_state.scroll_to_reply = True  # 選択直後にスクロール
                        except Exception as e:
                            st.error(f"取得エラー: {e}")
                    st.rerun()  # この rerun 後にスクロールが発火する

        # ── メール詳細 + 返信 ───────────────────────────────────────────────
        with col_detail:
            # 「選択→」を押した直後のrerunでスクロール発火
            if st.session_state.get("scroll_to_reply"):
                st.components.v1.html("""
                <script>
                setTimeout(function(){
                    window.parent.document.querySelector('section.main').scrollTo({
                        top: window.parent.document.querySelector('section.main').scrollHeight,
                        behavior: 'smooth'
                    });
                }, 150);
                </script>
                """, height=0)
                st.session_state.scroll_to_reply = False

            if st.session_state.selected_msg is None:
                st.info("← メールを選択してください")
            else:
                msg = st.session_state.selected_msg

                st.markdown(f"#### 📨 {msg['subject']}")
                st.caption(f"From: {msg['from']}　|　{msg['date']}")

                with st.expander("📄 メール本文", expanded=False):
                    st.text_area("本文", value=msg["body"][:3000], height=160,
                                 disabled=True, label_visibility="collapsed")

                # 送信者のトーンを自動適用
                default_tone = get_tone_for_sender(msg["from"])
                tone_idx = list(groq_client.TONES.keys()).index(default_tone) \
                    if default_tone in groq_client.TONES else 0
                tone_gmail = st.radio("相手は？", list(groq_client.TONES.keys()),
                                      index=tone_idx, key="tone_gmail", horizontal=True)
                length_gmail = st.radio("返信の長さ", list(groq_client.LENGTHS.keys()),
                                        index=1, key="length_gmail", horizontal=True)
                extra = st.text_input("追加指示（任意）",
                                      placeholder="例：来週水曜に打ち合わせを提案する",
                                      key="extra_gmail")

                # ── 自動生成 ────────────────────────────────────────────────
                if not st.session_state.generated_reply:
                    reply = do_generate(msg["body"], extra, tone_gmail, length_gmail)
                    if reply:
                        st.session_state.generated_reply = reply
                        st.rerun()

                # ── 返信文エリア ─────────────────────────────────────────────
                if st.session_state.generated_reply:
                    st.markdown("---")
                    st.markdown("#### ✏️ 返信文（編集できます）")

                    edited = st.text_area(
                        "返信文", value=st.session_state.generated_reply,
                        height=260, label_visibility="collapsed",
                        key=f"reply_{msg['id']}")

                    col_s1, col_s2, col_s3 = st.columns([2, 1, 1])
                    with col_s1:
                        if st.button("📤 送信する", type="primary", use_container_width=True):
                            with st.spinner("送信中..."):
                                try:
                                    do_send(msg, edited)
                                    st.success("✅ 送信しました！")
                                    time.sleep(1)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"送信エラー: {e}")
                    with col_s2:
                        if st.button("🔁 再生成", use_container_width=True):
                            st.session_state.generated_reply = ""
                            st.session_state.pop(f"reply_{msg['id']}", None)
                            st.rerun()
                    with col_s3:
                        if st.button("✕ キャンセル", use_container_width=True):
                            st.session_state.selected_msg = None
                            st.session_state.generated_reply = ""
                            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: Outlook
# ═══════════════════════════════════════════════════════════════════════════════
if page == "outlook":
    st.markdown("#### 📮 Outlook")

    # ── ログイン入力 ──────────────────────────────────────────────────────────
    ol_email_in = st.text_input("メールアドレス", value=st.session_state.ol_email,
                                 placeholder="you@outlook.com", key="ol_email_input")
    ol_pass_in = st.text_input("パスワード", value=st.session_state.ol_password,
                                type="password",
                                placeholder="パスワード（MFA有効の場合はアプリパスワード）",
                                key="ol_pass_input")
    if ol_email_in:
        st.session_state.ol_email = ol_email_in
    if ol_pass_in:
        st.session_state.ol_password = ol_pass_in

    ol_ready = bool(st.session_state.ol_email and st.session_state.ol_password)

    if not ol_ready:
        st.info("👆 メールアドレスとパスワードを入力してください。")
    else:
        col_ol1, col_ol2 = st.columns([1, 1.6], gap="large")

        with col_ol1:
            st.markdown("#### 📥 受信トレイ")
            col_or1, col_or2 = st.columns([2, 1])
            with col_or1:
                filter_ol = st.selectbox("フィルター", ["すべて", "未読のみ"],
                                          label_visibility="collapsed", key="ol_filter")
            with col_or2:
                if st.button("🔄", use_container_width=True, key="ol_refresh"):
                    st.session_state.ol_messages = []

            if st.session_state.get("_ol_filter_prev") != filter_ol:
                st.session_state.ol_messages = []
                st.session_state["_ol_filter_prev"] = filter_ol

            if not st.session_state.ol_messages:
                with st.spinner("読み込み中..."):
                    try:
                        st.session_state.ol_messages = outlook_client.list_messages(
                            st.session_state.ol_email,
                            st.session_state.ol_password,
                            max_results=20,
                            unread_only=(filter_ol == "未読のみ"),
                        )
                    except Exception as e:
                        st.error(f"取得エラー: {e}")

            for msg in st.session_state.ol_messages:
                is_unread = not msg.get("is_read", True)
                is_selected = (st.session_state.ol_selected_msg is not None and
                               st.session_state.ol_selected_msg.get("id") == msg["id"])
                left_border = "3px solid #6366f1" if is_selected else ("3px solid #0078d4" if is_unread else "3px solid transparent")
                bg = "#1e1b4b10" if is_selected else ""
                st.markdown(
                    f"""<div style="border-left:{left_border};background:{bg};border-radius:6px;
                    padding:0.55rem 0.8rem;margin-bottom:0.35rem;">
                    <b style="font-size:0.88rem">{'🔵 ' if is_unread else ''}{msg['subject'][:38]}</b><br>
                    <small style="color:#64748b">{msg['from'][:40]}</small><br>
                    <small style="color:#94a3b8">{msg['date']}</small>
                    </div>""",
                    unsafe_allow_html=True,
                )
                if st.button("選択 →", key=f"ol_sel_{msg['id']}", use_container_width=True):
                    with st.spinner("取得中..."):
                        try:
                            full = outlook_client.get_message_body(
                                st.session_state.ol_email,
                                st.session_state.ol_password,
                                msg["id"])
                            st.session_state.ol_selected_msg = full
                            st.session_state.ol_generated_reply = ""
                        except Exception as e:
                            st.error(f"取得エラー: {e}")
                    st.rerun()

        with col_ol2:
            if st.session_state.ol_selected_msg is None:
                st.info("← メールを選択してください")
            else:
                msg = st.session_state.ol_selected_msg

                st.markdown(f"#### 📨 {msg['subject']}")
                st.caption(f"From: {msg['from']}　|　{msg['date']}")

                with st.expander("📄 メール本文", expanded=False):
                    st.text_area("本文", value=msg["body"][:3000], height=160,
                                 disabled=True, label_visibility="collapsed")

                tone_ol = st.radio("相手は？", list(groq_client.TONES.keys()),
                                   index=0, key="tone_ol", horizontal=True)
                length_ol = st.radio("返信の長さ", list(groq_client.LENGTHS.keys()),
                                     index=1, key="length_ol", horizontal=True)
                extra_ol = st.text_input("追加指示（任意）",
                                         placeholder="例：来週水曜に打ち合わせを提案する",
                                         key="extra_ol")

                if not st.session_state.ol_generated_reply:
                    reply = do_generate(msg["body"], extra_ol, tone_ol, length_ol)
                    if reply:
                        st.session_state.ol_generated_reply = reply
                        st.rerun()

                if st.session_state.ol_generated_reply:
                    st.markdown("---")
                    st.markdown("#### ✏️ 返信文（編集できます）")
                    edited_ol = st.text_area(
                        "返信文", value=st.session_state.ol_generated_reply,
                        height=260, label_visibility="collapsed",
                        key=f"ol_reply_{msg['id']}")

                    col_o1, col_o2, col_o3 = st.columns([2, 1, 1])
                    with col_o1:
                        if st.button("📤 送信する", type="primary", use_container_width=True, key="ol_send"):
                            with st.spinner("送信中..."):
                                try:
                                    outlook_client.send_reply(
                                        st.session_state.ol_email,
                                        st.session_state.ol_password,
                                        msg, edited_ol)
                                    outlook_client.mark_as_read(
                                        st.session_state.ol_email,
                                        st.session_state.ol_password,
                                        msg["id"])
                                    request_box.save_history(
                                        "Outlook", msg["from"], msg["subject"],
                                        edited_ol, _user_key())
                                    st.success("✅ 送信しました！")
                                    st.session_state.ol_selected_msg = None
                                    st.session_state.ol_generated_reply = ""
                                    st.session_state.ol_messages = []
                                    time.sleep(1)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"送信エラー: {e}")
                    with col_o2:
                        if st.button("🔁 再生成", use_container_width=True, key="ol_regen"):
                            st.session_state.ol_generated_reply = ""
                            st.session_state.pop(f"ol_reply_{msg['id']}", None)
                            st.rerun()
                    with col_o3:
                        if st.button("✕ キャンセル", use_container_width=True, key="ol_cancel"):
                            st.session_state.ol_selected_msg = None
                            st.session_state.ol_generated_reply = ""
                            st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: Chatwork
# ═══════════════════════════════════════════════════════════════════════════════
if page == "chatwork":
    st.markdown("#### 💼 Chatwork")

    cw_input = st.text_input("APIトークン", value=st.session_state.cw_token,
                              type="password", placeholder="Chatwork APIトークン",
                              key="cw_token_input")
    if cw_input:
        st.session_state.cw_token = cw_input

    cw_token = st.session_state.cw_token
    if not cw_token:
        st.info("👆 Chatwork APIトークンを入力してください。")
    else:
        col_cw1, col_cw2 = st.columns([1, 1.6], gap="large")

        with col_cw1:
            st.markdown("#### 💬 ルーム一覧")
            if st.button("🔄 更新", use_container_width=True, key="cw_refresh"):
                st.session_state.cw_rooms = []
                st.session_state.cw_messages = []

            if not st.session_state.cw_rooms:
                with st.spinner("ルームを読み込み中..."):
                    try:
                        st.session_state.cw_rooms = chatwork_client.get_rooms(cw_token)
                    except Exception as e:
                        st.error(str(e))

            for room in st.session_state.cw_rooms:
                is_sel = (st.session_state.cw_selected_room is not None and
                          st.session_state.cw_selected_room.get("room_id") == room["room_id"])
                unread = room.get("unread_num", 0)
                border = "3px solid #6366f1" if is_sel else ("3px solid #f59e0b" if unread else "3px solid transparent")
                st.markdown(
                    f"""<div style="border-left:{border};border-radius:6px;padding:0.5rem 0.8rem;margin-bottom:0.3rem;">
                    <b>{'🟡 ' if unread else ''}{room.get('name','')[:35]}</b>
                    {'<br><small style="color:#f59e0b">未読 '+str(unread)+'件</small>' if unread else ''}
                    </div>""", unsafe_allow_html=True)
                if st.button("選択 →", key=f"cw_room_{room['room_id']}", use_container_width=True):
                    st.session_state.cw_selected_room = room
                    st.session_state.cw_messages = []
                    st.session_state.cw_selected_msg = None
                    st.session_state.cw_reply = ""
                    st.rerun()

        with col_cw2:
            if not st.session_state.cw_selected_room:
                st.info("← ルームを選択してください")
            else:
                room = st.session_state.cw_selected_room
                st.markdown(f"#### 💬 {room.get('name','')}")

                if not st.session_state.cw_messages:
                    with st.spinner("メッセージを取得中..."):
                        try:
                            st.session_state.cw_messages = chatwork_client.get_messages(
                                cw_token, str(room["room_id"]))
                        except Exception as e:
                            st.error(str(e))

                msgs = st.session_state.cw_messages[-20:][::-1]
                if not msgs:
                    st.info("メッセージがありません。")
                else:
                    for m in msgs:
                        acct = m.get("account", {})
                        sender = acct.get("name", "")
                        body = m.get("body", "")
                        is_sel = (st.session_state.cw_selected_msg is not None and
                                  st.session_state.cw_selected_msg.get("message_id") == m.get("message_id"))
                        border = "3px solid #6366f1" if is_sel else "3px solid transparent"
                        st.markdown(
                            f"""<div style="border-left:{border};border-radius:6px;padding:0.5rem 0.8rem;margin-bottom:0.3rem;">
                            <b>{sender}</b><br>
                            <small style="color:#94a3b8">{body[:80]}...</small>
                            </div>""", unsafe_allow_html=True)
                        if st.button("返信する →", key=f"cw_msg_{m['message_id']}", use_container_width=True):
                            st.session_state.cw_selected_msg = m
                            st.session_state.cw_reply = ""
                            st.rerun()

                if st.session_state.cw_selected_msg:
                    st.markdown("---")
                    m = st.session_state.cw_selected_msg
                    st.caption(f"返信先: {m.get('account',{}).get('name','')}  |  {m.get('body','')[:60]}")
                    tone_cw = st.radio("相手は？", list(groq_client.TONES.keys()),
                                       index=0, key="tone_cw", horizontal=True)
                    length_cw = st.radio("長さ", list(groq_client.LENGTHS.keys()),
                                         index=1, key="length_cw", horizontal=True)
                    extra_cw = st.text_input("追加指示（任意）", key="extra_cw")

                    if not st.session_state.cw_reply:
                        reply = do_generate(m.get("body", ""), extra_cw, tone_cw, length_cw)
                        if reply:
                            st.session_state.cw_reply = reply
                            st.rerun()

                    if st.session_state.cw_reply:
                        edited_cw = st.text_area("返信文（編集できます）",
                                                  value=st.session_state.cw_reply,
                                                  height=200, key=f"cw_edit_{m['message_id']}")
                        col_c1, col_c2 = st.columns(2)
                        with col_c1:
                            if st.button("📤 送信する", type="primary", use_container_width=True, key="cw_send"):
                                with st.spinner("送信中..."):
                                    try:
                                        chatwork_client.send_message(cw_token, str(room["room_id"]), edited_cw)
                                        request_box.save_history("Chatwork",
                                            m.get("account",{}).get("name",""),
                                            room.get("name",""), edited_cw,
                                            _user_key())
                                        st.success("✅ 送信しました！")
                                        st.session_state.cw_selected_msg = None
                                        st.session_state.cw_reply = ""
                                        st.session_state.cw_messages = []
                                        st.rerun()
                                    except Exception as e:
                                        st.error(str(e))
                        with col_c2:
                            if st.button("🔁 再生成", use_container_width=True, key="cw_regen"):
                                st.session_state.cw_reply = ""
                                st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB: LINE
# ═══════════════════════════════════════════════════════════════════════════════
if page == "line":
    st.markdown("#### 💬 LINE返信ジェネレーター")
    col_ln1, col_ln2 = st.columns([1, 1], gap="large")

    with col_ln1:
        st.markdown("**受信したLINEメッセージ**")
        line_input = st.text_area("LINEメッセージ", height=160,
                                   placeholder="LINEで受け取ったメッセージを貼り付け...",
                                   label_visibility="collapsed")
        tone_line = st.radio("相手は？", list(groq_client.TONES.keys()),
                              index=0, key="tone_line", horizontal=True)
        line_extra = st.text_input("追加指示（任意）",
                                    placeholder="例：了解の旨を短く伝える", key="line_extra")
        if st.button("⚡ 返信を生成", type="primary", use_container_width=True, key="gen_line"):
            reply = do_generate(line_input, line_extra, tone_line)
            if reply:
                st.session_state["line_reply"] = reply

    with col_ln2:
        st.markdown("**生成された返信文**")
        if not st.session_state.get("line_reply"):
            st.info("← メッセージを入力して生成ボタンを押してください")
        else:
            edited_line = st.text_area("LINE返信", value=st.session_state["line_reply"],
                                        height=160, label_visibility="collapsed",
                                        key="line_reply_edit")
            st.caption(f"文字数: {len(edited_line)}")

            if st.session_state.line_token and st.session_state.line_user_id:
                if st.button("📤 LINEで送信", type="primary", use_container_width=True):
                    with st.spinner("送信中..."):
                        result = line_client.send_line_message(
                            to_user_id=st.session_state.line_user_id,
                            message=edited_line,
                            channel_access_token=st.session_state.line_token,
                        )
                    if result["status_code"] == 200:
                        st.success("✅ LINEで送信しました！")
                        st.session_state["line_reply"] = ""
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(f"送信失敗: {result['body']}")
            else:
                st.caption("💡 自動送信にはサイドバーでLINEトークンを設定してください")
                st.download_button("💾 テキスト保存", data=edited_line,
                                    file_name="line_reply.txt", use_container_width=True)

            if st.button("🔁 再生成", use_container_width=True, key="regen_line"):
                st.session_state["line_reply"] = ""
                st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB: リクエストボックス
# ═══════════════════════════════════════════════════════════════════════════════
if page == "request":
    import uuid
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())
    sid = st.session_state.session_id

    st.markdown("#### 💡 リクエストボックス")
    st.caption("不満点・改善案・欲しい機能を投稿してください。いいねが多い順に上位表示されます。")

    supabase_ready = bool(
        (st.secrets.get("SUPABASE_URL") if hasattr(st, "secrets") else None)
        or os.getenv("SUPABASE_URL")
    )

    if not supabase_ready:
        st.warning("⚙️ Supabaseが未設定です。管理者にお問い合わせください。")
    else:
        # 投稿フォーム
        with st.form("req_form", clear_on_submit=True):
            new_req = st.text_area("リクエストを入力", placeholder="例：Outlookにも対応してほしい", height=80,
                                   label_visibility="collapsed")
            submitted = st.form_submit_button("📨 投稿する", use_container_width=True)
            if submitted and new_req.strip():
                if request_box.submit_request(new_req, sid):
                    st.success("投稿しました！")
                    st.rerun()

        st.markdown("---")

        # リクエスト一覧（いいね順）
        requests = request_box.get_requests()
        if not requests:
            st.info("まだリクエストはありません。最初の投稿をどうぞ！")
        else:
            for req in requests:
                liked_by = req.get("liked_by") or []
                already_liked = sid in liked_by
                col_txt, col_btn = st.columns([5, 1])
                with col_txt:
                    st.markdown(f"**{req['text']}**")
                with col_btn:
                    label = f"{'❤️' if already_liked else '🤍'} {req['likes']}"
                    if st.button(label, key=f"like_{req['id']}", use_container_width=True):
                        request_box.toggle_like(req["id"], sid)
                        st.rerun()
                st.divider()


# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: 設定
# ═══════════════════════════════════════════════════════════════════════════════
if page == "settings":
    st.markdown("#### ⚙️ 設定")

    st.markdown("### 🤖 Groq APIキー")
    groq_input = st.text_input("Groq API Key", value=st.session_state.groq_api_key,
                                type="password", placeholder="gsk_...",
                                key="groq_key_input")
    if groq_input:
        st.session_state.groq_api_key = groq_input
    if st.session_state.groq_api_key:
        st.caption("✅ APIキー設定済み")
    else:
        st.warning("Groq APIキーが未設定です。AI返信生成が使えません。")

    if st.session_state.reply_history:
        st.divider()
        st.markdown(f"### 📋 送信履歴（{len(st.session_state.reply_history)}件）")
        for item in reversed(st.session_state.reply_history[-10:]):
            st.markdown(f"- `{item['time']}` **{item['channel']}** → {item.get('to','')[:30]}")
        if st.button("🗑️ 履歴クリア"):
            st.session_state.reply_history = []
            st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: 返信履歴
# ═══════════════════════════════════════════════════════════════════════════════
if page == "history":
    st.markdown("#### 🕘 返信履歴")
    st.caption("このシステムで送信した返信の記録です。72時間で自動削除されます。")
    _ukey = _user_key()
    if not _ukey:
        st.warning("👈 Gmail または Outlook を連携すると履歴が表示されます。")
    else:
        history = request_box.get_history(_ukey)
        if not history:
            st.info("まだ返信履歴がありません。")
        else:
            for item in history:
                ch = item.get("channel", "")
                to = item.get("to_address", "")
                subj = item.get("subject", "")
                body = item.get("body", "")
                ts = item.get("created_at", "")[:16].replace("T", " ")
                with st.expander(f"**{ch}** | {subj[:35]} → {to[:30]}　`{ts}`"):
                    st.text_area("返信内容", value=body, height=120, disabled=True,
                                 label_visibility="collapsed", key=f"hist_{item['id']}")

# ═══════════════════════════════════════════════════════════════════════════════
# PAGE: できること
# ═══════════════════════════════════════════════════════════════════════════════
if page == "guide":
    st.markdown("#### 📖 replAIでできること")
    st.markdown("""
**📧 メールの自動返信**
- Gmailと連携して受信メールを一覧表示
- メールを選ぶだけでAIが返信文を自動生成
- 生成された文章は自分で編集してから送信できる

**🎭 相手に合わせた文体**
- 上司・先輩へ、友達へ、後輩へなどトーンを選択
- メールアドレスごとに口調を登録しておくと自動で切り替わる

**📏 返信の長さを調整**
- 短め・普通・長めの3段階から選択できる

**💬 LINE返信の生成**
- LINEで受け取ったメッセージを貼り付けて返信文を生成
- LINE Messaging APIと連携すれば自動送信も可能

**💡 リクエストボックス**
- 使いながら気になった改善点や追加してほしい機能をリクエスト投稿できる
- ほかのユーザーがいいねを押すことで要望の優先度が可視化される

**🕘 返信履歴の自動保存**
- 送信した返信が自動で記録・保存される
- いつでも過去の返信内容を確認できる

**🔒 セキュリティ**
- APIキーはサーバー側で管理、画面上に表示されない
- Gmail認証はGoogleの公式OAuthを使用
""")

