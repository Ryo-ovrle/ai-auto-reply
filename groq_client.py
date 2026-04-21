from groq import Groq

TONES = {
    "丁寧（ビジネス）": "丁寧でプロフェッショナルなビジネス敬語。「〜でございます」「〜いただけますと幸いです」などを適切に使用する。",
    "フレンドリー": "親しみやすく温かみのある口調。硬すぎず、相手に寄り添うような表現。",
    "簡潔": "要点だけを端的に伝える短い返信。箇条書きや短文を活用する。",
    "カジュアル": "気軽でフラットな口調。ビジネス敬語は最小限にする。",
}

def generate_reply(
    original_message: str,
    tone: str = "丁寧（ビジネス）",
    instruction: str = "",
    language: str = "日本語",
    api_key: str = "",
    model: str = "llama-3.3-70b-versatile",
) -> str:
    client = Groq(api_key=api_key)

    tone_desc = TONES.get(tone, tone)
    instruction_line = f"\n- 特別な指示: {instruction}" if instruction else ""

    system_prompt = f"""あなたはビジネスメール・メッセージの返信文を作成するプロです。
以下の条件を厳守して返信文のみを出力してください：
- トーン: {tone_desc}
- 言語: {language}
- 署名・宛名は含めない（本文のみ）
- 余分な説明や前置きは不要{instruction_line}"""

    user_prompt = f"""以下のメッセージへの返信文を作成してください。

【受信メッセージ】
{original_message}

【返信文】"""

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        max_tokens=1024,
    )
    return response.choices[0].message.content.strip()
