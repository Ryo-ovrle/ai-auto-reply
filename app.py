import streamlit as st
import os
import time
from datetime import datetime
from dotenv import load_dotenv

import groq_client
import gmail_client
import line_client

load_dotenv()

st.set_page_config(
    page_title="AI自動返信メーカー",
    page_icon="✉️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
.main-title { font-size: 2rem; font-weight: 700; }
.sub-title  { color: #888; font-size: 0.9rem; margin-top: -0.5rem; }
.reply-box  { background: #f0f7ff; border-left: 4px solid #2196F3;
              padding: 1rem; border-radius: 0 8px 8px 0; white-space: pre-wrap; }
.success-badge { background: #e8f5e9; color: #2e7d32;
                 padding: 4px 12px; border-radius: 20px; font-size: 0.85rem; }
</style>
""", unsafe_allow_html=True)


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
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init()


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

    if st.session_state.groq_api_key:
        st.markdown("🤖 **Groq AI** ✅ 設定済み")
    else:
        st.error("⚠️ GROQ_API_KEY が設定されていません")

    st.divider()
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
                st.markdown(f"**[👉 ここをクリックしてGoogleで認証]({auth_url})**")
                st.caption("認証後、自動でこのページに戻ります。")
        else:
            st.warning("credentials.json が見つかりません")

    st.divider()
    st.markdown("### 💬 LINE（任意）")
    line_token = st.text_input(
        "Channel Access Token",
        value=st.session_state.line_token,
        type="password",
        placeholder="LINE Messaging API トークン",
    )
    line_uid = st.text_input(
        "送信先 User ID",
        value=st.session_state.line_user_id,
        placeholder="Uxxxxxxxxxx...",
    )
    if line_token:
        st.session_state.line_token = line_token
    if line_uid:
        st.session_state.line_user_id = line_uid

    if st.session_state.reply_history:
        st.divider()
        st.markdown(f"### 📋 送信履歴（{len(st.session_state.reply_history)}件）")
        if st.button("🗑️ 履歴クリア", use_container_width=True):
            st.session_state.reply_history = []
            st.rerun()


# ── Main ──────────────────────────────────────────────────────────────────────
st.markdown('<p class="main-title">✉️ AI自動返信メーカー</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">Gmailの返信をAIが瞬時に生成・送信</p>', unsafe_allow_html=True)
st.divider()

language = "日本語"
model = "llama-3.3-70b-versatile"


def do_generate(original_text: str, extra: str = "", tone: str = "👔 上司・先輩へ") -> str:
    if not st.session_state.groq_api_key:
        st.error("⚠️ GROQ_API_KEY が設定されていません。")
        return ""
    if not original_text.strip():
        st.warning("メッセージを選択してください。")
        return ""
    with st.spinner("🤖 AIが返信文を生成中..."):
        try:
            return groq_client.generate_reply(
                original_message=original_text,
                tone=tone,
                instruction=extra,
                language=language,
                api_key=st.session_state.groq_api_key,
                model=model,
            )
        except Exception as e:
            st.error(f"生成エラー: {e}")
            return ""


tab_gmail, tab_line = st.tabs(["📧 Gmail", "💬 LINE"])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB: Gmail
# ═══════════════════════════════════════════════════════════════════════════════
with tab_gmail:
    if not st.session_state.gmail_service:
        st.info("👈 サイドバーから「Gmailを連携する」を押してください。")
    else:
        col_list, col_detail = st.columns([1, 1.5], gap="large")

        with col_list:
            st.markdown("#### 📥 受信トレイ")
            col_r1, col_r2 = st.columns([2, 1])
            with col_r1:
                label_filter = st.selectbox("フィルター", ["INBOX", "UNREAD"], label_visibility="collapsed")
            with col_r2:
                if st.button("🔄 更新", use_container_width=True):
                    st.session_state.gmail_messages = []

            if not st.session_state.gmail_messages:
                with st.spinner("メールを読み込み中..."):
                    try:
                        st.session_state.gmail_messages = gmail_client.list_messages(
                            st.session_state.gmail_service, max_results=20, label=label_filter
                        )
                    except Exception as e:
                        st.error(f"取得エラー: {e}")

            for msg in st.session_state.gmail_messages:
                is_unread = "UNREAD" in msg.get("labelIds", [])
                is_selected = (
                    st.session_state.selected_msg is not None
                    and st.session_state.selected_msg.get("id") == msg["id"]
                )
                border = "2px solid #2196F3" if is_selected else ("4px solid #2196F3" if is_unread else "1px solid #e0e0e0")
                st.markdown(
                    f"""<div style="border-left:{border};border-radius:8px;padding:0.6rem 1rem;margin-bottom:0.4rem;">
                    <b>{'🔵 ' if is_unread else ''}{msg['subject'][:40]}</b><br>
                    <small style="color:#666">{msg['from'][:35]}</small><br>
                    <small style="color:#999">{msg['snippet'][:60]}...</small>
                    </div>""",
                    unsafe_allow_html=True,
                )
                if st.button("選択", key=f"sel_{msg['id']}", use_container_width=True):
                    with st.spinner("メール本文を取得中..."):
                        try:
                            full = gmail_client.get_message_body(
                                st.session_state.gmail_service, msg["id"]
                            )
                            st.session_state.selected_msg = full
                            st.session_state.generated_reply = ""
                        except Exception as e:
                            st.error(f"取得エラー: {e}")
                    st.rerun()

        with col_detail:
            if st.session_state.selected_msg is None:
                st.info("← 左のメール一覧からメッセージを選択してください")
            else:
                msg = st.session_state.selected_msg
                st.markdown(f"#### 📨 {msg['subject']}")
                st.caption(f"From: {msg['from']}　|　{msg['date']}")

                with st.expander("📄 メール本文", expanded=True):
                    st.text_area("本文", value=msg["body"][:3000], height=180,
                                 disabled=True, label_visibility="collapsed")

                tone_gmail = st.radio("相手は？", list(groq_client.TONES.keys()),
                                      index=0, key="tone_gmail", horizontal=True)
                extra = st.text_input("追加指示（任意）",
                                      placeholder="例：来週水曜に打ち合わせを提案する")

                if st.button("🤖 返信文を生成", type="primary", use_container_width=True, key="gen_gmail"):
                    reply = do_generate(msg["body"], extra, tone_gmail)
                    if reply:
                        st.session_state.generated_reply = reply

                if st.session_state.generated_reply:
                    st.markdown("#### ✏️ 返信文（編集できます）")
                    edited = st.text_area("返信文", value=st.session_state.generated_reply,
                                          height=250, label_visibility="collapsed",
                                          key="gmail_reply_edit")

                    col_s1, col_s2 = st.columns(2)
                    with col_s1:
                        if st.button("📤 送信する", type="primary", use_container_width=True):
                            with st.spinner("送信中..."):
                                try:
                                    gmail_client.send_reply(st.session_state.gmail_service, msg, edited)
                                    gmail_client.mark_as_read(st.session_state.gmail_service, msg["id"])
                                    st.session_state.reply_history.append({
                                        "time": datetime.now().strftime("%H:%M"),
                                        "channel": "Gmail",
                                        "to": msg["from"],
                                        "subject": msg["subject"],
                                    })
                                    st.success("✅ 送信しました！")
                                    st.session_state.selected_msg = None
                                    st.session_state.generated_reply = ""
                                    st.session_state.gmail_messages = []
                                    time.sleep(1)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"送信エラー: {e}")
                    with col_s2:
                        if st.button("🔁 再生成", use_container_width=True):
                            reply = do_generate(msg["body"], extra, tone_gmail)
                            if reply:
                                st.session_state.generated_reply = reply
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
        if st.button("🤖 返信を生成", type="primary", use_container_width=True, key="gen_line"):
            reply = do_generate(line_input, line_extra, tone_line)
            if reply:
                st.session_state["line_reply"] = reply

    with col_ln2:
        st.markdown("**生成された返信文**")
        if not st.session_state.get("line_reply"):
            st.info("← 左のメッセージを入力して生成ボタンを押してください")
        else:
            edited_line = st.text_area("LINE返信", value=st.session_state["line_reply"],
                                        height=160, label_visibility="collapsed",
                                        key="line_reply_edit")
            st.caption(f"文字数: {len(edited_line)}")

            if st.session_state.line_token and st.session_state.line_user_id:
                if st.button("📤 LINEで自動送信", type="primary", use_container_width=True):
                    with st.spinner("LINE送信中..."):
                        result = line_client.send_line_message(
                            to_user_id=st.session_state.line_user_id,
                            message=edited_line,
                            channel_access_token=st.session_state.line_token,
                        )
                    if result["status_code"] == 200:
                        st.success("✅ LINEで送信しました！")
                        st.session_state.reply_history.append({
                            "time": datetime.now().strftime("%H:%M"),
                            "channel": "LINE",
                            "to": st.session_state.line_user_id,
                            "subject": line_input[:30] + "...",
                        })
                        st.session_state["line_reply"] = ""
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(f"送信失敗: {result['body']}")
            else:
                st.caption("💡 自動送信するにはサイドバーでLINEトークンを設定してください")
                st.download_button("💾 テキスト保存", data=edited_line,
                                    file_name="line_reply.txt", use_container_width=True)

            if st.button("🔁 再生成", use_container_width=True, key="regen_line"):
                reply = do_generate(line_input, line_extra, tone_line)
                if reply:
                    st.session_state["line_reply"] = reply
                    st.rerun()


# ── 送信履歴 ──────────────────────────────────────────────────────────────────
if st.session_state.reply_history:
    st.divider()
    st.markdown("#### 📋 今日の送信履歴")
    for item in reversed(st.session_state.reply_history[-10:]):
        st.markdown(
            f"- `{item['time']}` **{item['channel']}** → {item.get('to','')[:30]}　「{item.get('subject','')[:30]}」"
        )
