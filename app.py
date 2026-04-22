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
.msg-card { border: 1px solid #e0e0e0; border-radius: 8px;
            padding: 0.75rem 1rem; margin-bottom: 0.5rem;
            cursor: pointer; transition: background 0.2s; }
.msg-card:hover { background: #f5f5f5; }
.unread { border-left: 4px solid #2196F3; font-weight: 600; }
</style>
""", unsafe_allow_html=True)


# ── Session state defaults ────────────────────────────────────────────────────
def _init():
    defaults = {
        "groq_api_key": os.getenv("GROQ_API_KEY", ""),
        "line_token": os.getenv("LINE_CHANNEL_ACCESS_TOKEN", ""),
        "line_user_id": os.getenv("LINE_USER_ID", ""),
        "gmail_service": None,
        "oauth_flow": None,
        "selected_msg": None,
        "generated_reply": "",
        "reply_history": [],
        "gmail_messages": [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init()


# ── OAuth callback handling ───────────────────────────────────────────────────
params = st.query_params
if "code" in params:
    try:
        _, fresh_flow = gmail_client.get_auth_url()
        creds = gmail_client.exchange_code(fresh_flow, params["code"])
        st.session_state.gmail_service = gmail_client.build_service(creds)
        st.session_state.oauth_flow = None
        st.query_params.clear()
        st.rerun()
    except Exception as e:
        st.error(f"Gmail認証エラー: {e}")
        st.query_params.clear()

# Load saved token on startup
if st.session_state.gmail_service is None and gmail_client.token_exists():
    creds = gmail_client.load_credentials()
    if creds:
        st.session_state.gmail_service = gmail_client.build_service(creds)


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ 設定")

    if st.session_state.groq_api_key:
        st.markdown("🤖 **Groq API** ✅ 設定済み")
    else:
        st.error("⚠️ GROQ_API_KEY が .env にありません")

    st.divider()
    st.markdown("### 📧 Gmail")
    if st.session_state.gmail_service:
        st.markdown('<span class="success-badge">✅ 連携済み</span>', unsafe_allow_html=True)
        if st.button("🔓 連携解除", use_container_width=True):
            st.session_state.gmail_service = None
            if os.path.exists(gmail_client.TOKEN_FILE):
                os.remove(gmail_client.TOKEN_FILE)
            st.rerun()
    else:
        if gmail_client.credentials_exist():
            if st.button("🔗 Gmailを連携する", use_container_width=True, type="primary"):
                auth_url, flow = gmail_client.get_auth_url()
                st.session_state.oauth_flow = flow
                st.markdown(f"""
**以下のURLをブラウザで開いて認証してください：**

[🔗 Google認証ページを開く]({auth_url})

認証後、自動でこのページに戻ります。
""")
        else:
            st.warning("credentials.json が見つかりません")
            with st.expander("📋 設定方法"):
                st.markdown("""
1. [Google Cloud Console](https://console.cloud.google.com) にアクセス
2. プロジェクト作成 → Gmail API を有効化
3. OAuth 2.0 クライアントID を作成
4. リダイレクトURIに `http://localhost:8501/` を追加
5. `credentials.json` をダウンロードしてこのフォルダに配置
""")

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

    language = "日本語"
    model = "llama-3.3-70b-versatile"

    if st.session_state.reply_history:
        st.divider()
        st.markdown(f"### 📋 送信履歴（{len(st.session_state.reply_history)}件）")
        if st.button("🗑️ 履歴をクリア", use_container_width=True):
            st.session_state.reply_history = []
            st.rerun()


# ── Main header ───────────────────────────────────────────────────────────────
st.markdown('<p class="main-title">✉️ AI自動返信メーカー</p>', unsafe_allow_html=True)
st.markdown('<p class="sub-title">メール・LINE・メッセージの返信をAIが瞬時に生成・送信</p>', unsafe_allow_html=True)
st.divider()


# ── Helper: generate reply ────────────────────────────────────────────────────
def do_generate(original_text: str, extra_instruction: str = "", tone: str = "👔 上司・先輩へ") -> str:
    if not st.session_state.groq_api_key:
        st.error("⚠️ .env に GROQ_API_KEY がありません。")
        return ""
    if not original_text.strip():
        st.warning("返信元のメッセージを入力してください。")
        return ""
    with st.spinner("🤖 AIが返信文を生成中..."):
        try:
            reply = groq_client.generate_reply(
                original_message=original_text,
                tone=tone,
                instruction=extra_instruction,
                language=language,
                api_key=st.session_state.groq_api_key,
                model=model,
            )
            return reply
        except Exception as e:
            st.error(f"生成エラー: {e}")
            return ""


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_gmail, tab_manual, tab_line = st.tabs(["📧 Gmail", "✏️ 手動入力", "💬 LINE"])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1: Gmail
# ═══════════════════════════════════════════════════════════════════════════════
with tab_gmail:
    if not st.session_state.gmail_service:
        st.info("👈 サイドバーからGmailを連携してください。")
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
                card_class = "msg-card unread" if is_unread else "msg-card"
                is_selected = (
                    st.session_state.selected_msg is not None
                    and st.session_state.selected_msg.get("id") == msg["id"]
                )
                border = "2px solid #2196F3" if is_selected else "1px solid #e0e0e0"

                st.markdown(
                    f"""<div style="border:{border};border-radius:8px;padding:0.6rem 1rem;
                    margin-bottom:0.4rem;{'border-left:4px solid #2196F3;' if is_unread else ''}">
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
                    st.text_area(
                        "本文",
                        value=msg["body"][:3000],
                        height=200,
                        disabled=True,
                        label_visibility="collapsed",
                    )

                tone_gmail = st.radio("相手は？", list(groq_client.TONES.keys()), index=0, key="tone_gmail", horizontal=True)
                col_tone_g, col_extra_g = st.columns([1, 2])
                with col_extra_g:
                    extra = st.text_input(
                        "追加指示（任意）",
                        placeholder="例：来週水曜に打ち合わせを提案する、承認の旨を伝える",
                    )

                if st.button("🤖 返信文を生成", type="primary", use_container_width=True, key="gen_gmail"):
                    reply = do_generate(msg["body"], extra, tone_gmail)
                    if reply:
                        st.session_state.generated_reply = reply

                if st.session_state.generated_reply:
                    st.markdown("#### ✏️ 生成された返信文")
                    edited = st.text_area(
                        "返信文（編集可）",
                        value=st.session_state.generated_reply,
                        height=250,
                        label_visibility="collapsed",
                        key="gmail_reply_edit",
                    )

                    col_s1, col_s2 = st.columns(2)
                    with col_s1:
                        if st.button("📤 送信する", type="primary", use_container_width=True):
                            with st.spinner("送信中..."):
                                try:
                                    gmail_client.send_reply(
                                        st.session_state.gmail_service, msg, edited
                                    )
                                    gmail_client.mark_as_read(
                                        st.session_state.gmail_service, msg["id"]
                                    )
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
# TAB 2: Manual
# ═══════════════════════════════════════════════════════════════════════════════
with tab_manual:
    st.markdown("#### ✏️ メッセージを貼り付けて返信を生成")
    st.caption("メール・LINE・チャット・何でも対応。受信したメッセージをそのままペーストしてください。")

    manual_input = st.text_area(
        "受信メッセージ",
        height=180,
        placeholder="ここに返信したいメッセージを貼り付けてください...",
        label_visibility="collapsed",
    )
    tone_manual = st.radio("相手は？", list(groq_client.TONES.keys()), index=0, key="tone_manual", horizontal=True)
    manual_extra = st.text_input(
        "追加指示（任意）",
        placeholder="例：タメ語で、断る方向で、感謝を伝える",
        key="manual_extra",
    )

    gen_btn = st.button("🤖 返信を生成", type="primary", use_container_width=True, key="gen_manual")

    if gen_btn:
        reply = do_generate(manual_input, manual_extra, tone_manual)
        if reply:
            st.session_state["manual_reply"] = reply

    if st.session_state.get("manual_reply"):
        st.markdown("#### ✏️ 生成された返信文")
        edited_manual = st.text_area(
            "返信文",
            value=st.session_state["manual_reply"],
            height=250,
            label_visibility="collapsed",
            key="manual_reply_edit",
        )
        char_count = len(edited_manual)
        st.caption(f"文字数: {char_count}")

        col_mc1, col_mc2, col_mc3 = st.columns(3)
        with col_mc1:
            st.download_button(
                "💾 テキスト保存",
                data=edited_manual,
                file_name=f"reply_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
                mime="text/plain",
                use_container_width=True,
            )
        with col_mc2:
            if st.button("🔁 再生成", use_container_width=True, key="regen_manual"):
                reply = do_generate(manual_input, manual_extra)
                if reply:
                    st.session_state["manual_reply"] = reply
                    st.rerun()
        with col_mc3:
            if st.button("🗑️ クリア", use_container_width=True):
                st.session_state["manual_reply"] = ""
                st.rerun()

        st.info("💡 コピーしてLINE・メール・チャットに貼り付けて送信できます。")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3: LINE
# ═══════════════════════════════════════════════════════════════════════════════
with tab_line:
    st.markdown("#### 💬 LINE返信ジェネレーター")

    col_ln1, col_ln2 = st.columns([1, 1], gap="large")

    with col_ln1:
        st.markdown("**受信したLINEメッセージ**")
        line_input = st.text_area(
            "LINEメッセージ",
            height=160,
            placeholder="LINEで受け取ったメッセージを貼り付け...",
            label_visibility="collapsed",
        )
        tone_line = st.radio("相手は？", list(groq_client.TONES.keys()), index=0, key="tone_line", horizontal=True)
        col_tone_l, col_extra_l = st.columns([1, 2])
        with col_extra_l:
            line_extra = st.text_input(
                "追加指示（任意）",
                placeholder="例：了解の旨を短く伝える",
                key="line_extra",
            )
        if st.button("🤖 返信を生成", type="primary", use_container_width=True, key="gen_line"):
            reply = do_generate(line_input, line_extra, tone_line)
            if reply:
                st.session_state["line_reply"] = reply

    with col_ln2:
        st.markdown("**生成された返信文**")
        if not st.session_state.get("line_reply"):
            st.info("← 左のメッセージを入力して生成ボタンを押してください")
        else:
            edited_line = st.text_area(
                "LINE返信",
                value=st.session_state["line_reply"],
                height=160,
                label_visibility="collapsed",
                key="line_reply_edit",
            )
            st.caption(f"文字数: {len(edited_line)}")

            st.markdown("**送信方法を選択**")

            # Auto-send via LINE API
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
                st.download_button(
                    "💾 テキスト保存",
                    data=edited_line,
                    file_name="line_reply.txt",
                    use_container_width=True,
                )

            if st.button("🔁 再生成", use_container_width=True, key="regen_line"):
                reply = do_generate(line_input, line_extra)
                if reply:
                    st.session_state["line_reply"] = reply
                    st.rerun()


# ── Reply history ─────────────────────────────────────────────────────────────
if st.session_state.reply_history:
    st.divider()
    st.markdown("#### 📋 今日の送信履歴")
    for item in reversed(st.session_state.reply_history[-10:]):
        st.markdown(
            f"- `{item['time']}` **{item['channel']}** → {item.get('to','')[:30]}　「{item.get('subject','')[:30]}」"
        )
