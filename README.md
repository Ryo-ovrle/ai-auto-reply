# ✉️ AI自動返信メーカー

**メール・LINE・メッセージへの返信文をAIが瞬時に生成・送信するツール**

田舎の中小企業向けAI業務改善ツール第2弾。完全無料・インストール不要で使えます。

---

## ✨ 機能

| 機能 | 説明 |
|------|------|
| 📧 Gmail連携 | 受信トレイを一覧表示、選択してワンクリック返信 |
| ✏️ 手動入力 | どんなメッセージでも貼り付けて返信生成 |
| 💬 LINE自動送信 | LINEメッセージの返信をAPI経由で直接送信 |
| 🎨 トーン選択 | 丁寧・フレンドリー・簡潔・カジュアルから選択 |
| 🌐 多言語対応 | 日本語・英語・日英併記 |

---

## 🚀 セットアップ

### 1. 依存関係をインストール
```bash
pip install -r requirements.txt
```

### 2. 環境変数を設定
```bash
cp .env.example .env
# .env を編集して GROQ_API_KEY を入力
```

**Groq APIキーの取得（無料）**
1. https://console.groq.com にアクセス
2. サインアップ → API Keys → Create API Key

### 3. Streamlitを起動
```bash
streamlit run app.py
```

---

## 📧 Gmail連携の設定

### Google Cloud Consoleでの設定

1. https://console.cloud.google.com を開く
2. 新しいプロジェクトを作成
3. **APIとサービス** → **ライブラリ** → **Gmail API** を有効化
4. **認証情報** → **OAuth 2.0 クライアントID** を作成
   - アプリの種類：**ウェブアプリケーション**
   - 承認済みのリダイレクト URI に `http://localhost:8501/` を追加
5. JSONをダウンロードして `credentials.json` としてこのフォルダに配置

### 初回認証

アプリを起動してサイドバーの「Gmailを連携する」をクリック →  
表示されたGoogleリンクを開いて認証 → 自動で連携完了

---

## 💬 LINE自動送信の設定（任意）

1. https://developers.line.biz でアカウント作成
2. **Messaging API** チャンネルを作成
3. **Channel access token** を発行
4. .env に設定：
   ```
   LINE_CHANNEL_ACCESS_TOKEN=your_token_here
   LINE_USER_ID=Uxxxxxxxxxxxxxxxxx
   ```

> **LINE User IDの確認方法**：LINE公式アカウントに「自分のUserID」とメッセージすると確認できます（または [LINE Webhook](https://developers.line.biz/ja/docs/messaging-api/receiving-messages/) で受信データから取得）

---

## 🛠️ 技術スタック

- **フロントエンド**: Streamlit
- **AI**: Groq API（llama-3.3-70b-versatile）
- **メール**: Gmail API（Google）
- **LINE**: LINE Messaging API

---

## 📁 ファイル構成

```
ai-auto-reply/
├── app.py              # Streamlitメインアプリ
├── gmail_client.py     # Gmail API操作
├── groq_client.py      # Groq AI返信生成
├── line_client.py      # LINE送信
├── requirements.txt    # 依存ライブラリ
├── .env.example        # 環境変数テンプレート
└── README.md
```

---

## 🔒 セキュリティ

- APIキー・OAuthトークンはローカルにのみ保存
- `credentials.json` / `token.json` / `.env` はGitにコミットされません

---

*AI業務改善ポートフォリオ第2作 | Made with Streamlit + Groq*
