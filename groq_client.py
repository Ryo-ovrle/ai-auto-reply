from groq import Groq

TONES = {
    "👔 上司・先輩へ": "目上の人への丁寧な敬語。「〜いただけますでしょうか」「〜させていただきます」など謙譲語・尊敬語を正しく使う。失礼のない、かつ自然なビジネス文体。",
    "👫 友達へ": "タメ口でフランクに。堅苦しくなく、親しみやすい話し言葉。「だよ」「じゃん」「ありがとう！」など自然なカジュアル表現を使う。",
    "🧑‍🎓 後輩へ": "フレンドリーだが頼れる先輩・上司としての口調。優しく、わかりやすく、少しリードする感じ。タメ口寄りだが乱暴にならない。",
    "📧 丁寧（一般）": "万能な丁寧なビジネス敬語。相手を問わず使えるフォーマル文体。",
    "⚡ 簡潔": "要点のみを短く伝える。余計な言葉を削り、読みやすさ重視。",
}

LENGTHS = {
    "短め": "返信は3〜4文以内で簡潔にまとめること。",
    "普通": "返信は適切な長さで、必要な情報を過不足なく伝えること。",
    "長め": "返信は丁寧に詳しく、5文以上で丁寧に書くこと。",
}

def generate_reply(
    original_message: str,
    tone: str = "丁寧（ビジネス）",
    instruction: str = "",
    language: str = "日本語",
    api_key: str = "",
    model: str = "llama-3.3-70b-versatile",
    length: str = "普通",
) -> str:
    client = Groq(api_key=api_key)

    tone_desc = TONES.get(tone, tone)
    length_desc = LENGTHS.get(length, LENGTHS["普通"])
    instruction_line = f"\n- 特別な指示: {instruction}" if instruction else ""

    system_prompt = f"""あなたはビジネスメール・メッセージの返信文を作成するプロです。
以下の条件を厳守して返信文のみを出力してください：
- トーン: {tone_desc}
- 長さ: {length_desc}
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
    result = response.choices[0].message.content.strip()
    # Unicode制御文字を除去（  LINE SEPARATOR等）
    result = result.encode("utf-8", errors="ignore").decode("utf-8")
    result = "".join(c for c in result if ord(c) >= 32 or c in "\n\r\t")
    return result
