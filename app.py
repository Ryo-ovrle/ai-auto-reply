import streamlit as st
import os
import re
import time
from datetime import datetime
from dotenv import load_dotenv

import groq_client
import gmail_client
import line_client
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
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init()


# ── Helpers ───────────────────────────────────────────────────────────────────
def extract_email(sender: str) -> str:
    m = re.search(r"<(.+?)>", sender)
    return m.group(1).lower() if m else sender.lower().strip()

def get_tone_for_sender(sender: str) -> str:
    email = extract_email(sender)
    return st.session_state.sender_tones.get(email, list(groq_client.TONES.keys())[0])

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
    st.session_state.selected_msg = None
    st.session_state.generated_reply = ""
    st.session_state.gmail_messages = []


# ── OAuth callback ────────────────────────────────────────────────────────────
params = st.query_params
if "code" in params:
    try:
        creds = gmail_client.exchange_code(None, params["code"])
        st.session_state.gmail_service = gmail_client.build_service(creds)
        st.query_params.clear()
        st.rerun()
    except Exception as e:
        st.error(f"Gmail認証エラー: {e}")
        st.query_params.clear()


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ 設定")

    # Gmail
    st.markdown("### 📧 Gmail")
    if st.session_state.gmail_service:
        st.markdown('<span class="success-badge">✅ 連携済み</span>', unsafe_allow_html=True)
        if st.button("🔓 連携解除", use_container_width=True):
            st.session_state.gmail_service = None
            st.session_state.gmail_messages = []
            st.session_state.selected_msg = None
            st.rerun()
    else:
        if gmail_client.credentials_exist():
            if st.button("🔗 Gmailを連携する", use_container_width=True, type="primary"):
                auth_url, _ = gmail_client.get_auth_url()
                st.markdown(f"**[👉 Googleで認証する]({auth_url})**")
                st.caption("認証後、自動でこのページに戻ります。")
        else:
            st.warning("credentials.json が見つかりません")

    st.divider()

    # 送信者別トーン設定
    st.markdown("### 🎭 送信者別トーン設定")
    with st.expander("設定を追加・編集"):
        new_email = st.text_input("メールアドレス", placeholder="example@gmail.com", key="new_tone_email")
        new_tone = st.radio("口調", list(groq_client.TONES.keys()), key="new_tone_sel")
        if new_email.strip():
            st.session_state.sender_tones[new_email.strip().lower()] = new_tone

    if st.session_state.sender_tones:
        for email, tone in list(st.session_state.sender_tones.items()):
            col_e, col_d = st.columns([3, 1])
            col_e.caption(f"📧 {email}\n→ {tone}")
            if col_d.button("🗑", key=f"del_{email}"):
                del st.session_state.sender_tones[email]
                st.rerun()
    else:
        st.caption("設定なし（デフォルト: 上司・先輩へ）")

    st.divider()

    # LINE
    st.markdown("### 💬 LINE（任意）")
    line_token = st.text_input("Channel Access Token",
        value=st.session_state.line_token, type="password",
        placeholder="LINE Messaging API トークン")
    line_uid = st.text_input("送信先 User ID",
        value=st.session_state.line_user_id, placeholder="Uxxxxxxxxxx...")
    if line_token: st.session_state.line_token = line_token
    if line_uid:   st.session_state.line_user_id = line_uid

    if st.session_state.reply_history:
        st.divider()
        st.markdown(f"### 📋 送信履歴（{len(st.session_state.reply_history)}件）")
        if st.button("🗑️ 履歴クリア", use_container_width=True):
            st.session_state.reply_history = []
            st.rerun()

    st.divider()
    st.markdown("### 💡 リクエストボックス")
    st.caption("不満・改善案を投稿。いいねで要望度を示そう。")


# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(
    '<p class="brand-title"><span class="brand-repl">repl</span><span class="brand-ai">AI</span></p>',
    unsafe_allow_html=True
)
st.markdown('<p class="brand-sub">AI-Powered Instant Reply</p>', unsafe_allow_html=True)
st.divider()

tab_gmail, tab_line, tab_req = st.tabs(["📧 Gmail", "💬 LINE", "💡 リクエストボックス"])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB: Gmail
# ═══════════════════════════════════════════════════════════════════════════════
with tab_gmail:
    if not st.session_state.gmail_service:
        st.info("👈 サイドバーから「Gmailを連携する」を押してください。")
    else:
        col_list, col_detail = st.columns([1, 1.6], gap="large")

        # ── メール一覧 ──────────────────────────────────────────────────────
        with col_list:
            st.markdown("#### 📥 受信トレイ")
            col_r1, col_r2 = st.columns([2, 1])
            with col_r1:
                label_filter = st.selectbox("フィルター", ["INBOX", "UNREAD"],
                                             label_visibility="collapsed")
            with col_r2:
                if st.button("🔄", use_container_width=True):
                    st.session_state.gmail_messages = []

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
# TAB: LINE
# ═══════════════════════════════════════════════════════════════════════════════
with tab_line:
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
with tab_req:
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


# ── 送信履歴 ──────────────────────────────────────────────────────────────────
if st.session_state.reply_history:
    st.divider()
    st.markdown("#### 📋 送信履歴")
    for item in reversed(st.session_state.reply_history[-10:]):
        st.markdown(
            f"- `{item['time']}` **{item['channel']}** → {item.get('to','')[:30]}　「{item.get('subject','')[:30]}」"
        )
