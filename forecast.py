#!/usr/bin/env python3
"""
東海村 週間波予測スクリプト
毎晩22時(JST)にGitHub Actionsで実行 → LINEに送信
"""
import os, json, datetime, requests

# ── 設定 ──────────────────────────────────────────────
LAT, LON = 36.46, 140.57        # 東海村クソ下付近
JST = datetime.timezone(datetime.timedelta(hours=9))
ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]
LINE_TOKEN    = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_USER_ID  = os.environ["LINE_USER_ID"]

# ── 気象・波データ取得 (Open-Meteo / 無料・認証不要) ──
def fetch_forecast():
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={LAT}&longitude={LON}"
        "&daily=wind_speed_10m_max,wind_direction_10m_dominant,"
        "wave_height_max,wave_period_max,swell_wave_height_max,"
        "swell_wave_direction_dominant,precipitation_sum,weather_code"
        "&wind_speed_unit=ms"
        "&timezone=Asia%2FTokyo"
        "&forecast_days=8"
    )
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    return r.json()["daily"]

# ── 潮汐フェーズ計算（月齢ベース簡易版） ──
def tide_phase(date: datetime.date) -> str:
    # 2000-01-06 が新月
    ref = datetime.date(2000, 1, 6)
    lunar_cycle = 29.53
    age = ((date - ref).days % lunar_cycle)
    if age < 2 or age > 27.5:   return "大潮"
    if 12 < age < 17:            return "大潮"
    if 5 < age < 10:             return "小潮"
    if age <= 5 or 27 <= age:    return "中潮"
    if 10 <= age <= 12:          return "長潮"
    if age == 12:                return "若潮"
    return "中潮"

# ── 波高 → わたるさん単位変換 ──
def wave_size(m: float) -> str:
    if m < 0.1:  return "フラット"
    if m < 0.3:  return "スネ〜ヒザ"
    if m < 0.5:  return "ヒザ〜モモ"
    if m < 0.7:  return "モモ〜腰"
    if m < 0.9:  return "腰〜腹"
    if m < 1.1:  return "腹〜胸"
    if m < 1.4:  return "胸〜肩"
    if m < 1.8:  return "肩〜頭"
    return "頭オーバー"

# ── 風向度数 → 16方位 ──
def wind_dir_name(deg: float) -> str:
    dirs = ["北","北北東","北東","東北東","東","東南東","南東","南南東",
            "南","南南西","南西","西南西","西","西北西","北西","北北西"]
    return dirs[round(deg / 22.5) % 16]

# ── 天気コード → 絵文字 ──
def weather_emoji(code: int) -> str:
    if code == 0:       return "☀️"
    if code <= 3:       return "🌤"
    if code <= 48:      return "⛅"
    if code <= 67:      return "🌧"
    if code <= 77:      return "❄️"
    if code <= 82:      return "🌦"
    if code <= 99:      return "⛈"
    return "🌤"

# ── Claude API で予測文生成 ──
def generate_forecast_text(days_data: list[dict]) -> str:
    system = (
        "あなたは茨城県東海村のサーフコーチです。"
        "東海村クソ下ポイントの1週間波予測を、地元サーファーのわたるさん向けに"
        "わかりやすく、具体的にまとめてください。"
        "特に朝イチ（5〜8時台）のサーフィン適性に注目してください。"
    )
    user = "以下のデータから東海村クソ下の7日間波予測をまとめてください：\n\n"
    for d in days_data:
        user += (
            f"【{d['date']}（{d['dow']}）】\n"
            f"  波高: {d['wave_size']}  うねり: {d['swell_h']:.1f}m\n"
            f"  風: {d['wind_dir']} {d['wind_speed']:.1f}m/s  {d['weather']}\n"
            f"  潮汐: {d['tide']}\n\n"
        )
    user += (
        "\n出力フォーマット（各日1〜2行）:\n"
        "📅 [日付]（[曜]）[サイズ] [風向/速] [評価マーク] [一言コメント]\n"
        "最後に「今週のベストコンディション」を一行でまとめる。\n"
        "全体300文字以内。ハッシュタグ不要。"
    )

    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": ANTHROPIC_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 500,
            "system": system,
            "messages": [{"role": "user", "content": user}],
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()["content"][0]["text"].strip()

# ── LINE へ送信 ──
def send_line(text: str):
    r = requests.post(
        "https://api.line.me/v2/bot/message/push",
        headers={
            "Authorization": f"Bearer {LINE_TOKEN}",
            "Content-Type": "application/json",
        },
        json={
            "to": LINE_USER_ID,
            "messages": [{"type": "text", "text": text}],
        },
        timeout=15,
    )
    r.raise_for_status()
    print(f"LINE送信完了: {r.status_code}")

# ── メイン ──────────────────────────────────────────────
def main():
    today = datetime.date.today()
    raw = fetch_forecast()
    days_data = []
    dows = ["月","火","水","木","金","土","日"]

    for i in range(1, 8):   # 明日〜7日後
        date_str = raw["time"][i]
        date_obj = datetime.date.fromisoformat(date_str)
        days_data.append({
            "date":       f"{date_obj.month}/{date_obj.day}",
            "dow":        dows[date_obj.weekday()],
            "wave_size":  wave_size(raw["wave_height_max"][i] or 0),
            "swell_h":    raw["swell_wave_height_max"][i] or 0,
            "wind_dir":   wind_dir_name(raw["wind_direction_10m_dominant"][i] or 0),
            "wind_speed": raw["wind_speed_10m_max"][i] or 0,
            "weather":    weather_emoji(raw["weather_code"][i] or 0),
            "tide":       tide_phase(date_obj),
        })

    forecast_text = generate_forecast_text(days_data)

    now_str = datetime.datetime.now(JST).strftime("%Y/%m/%d %H:%M")
    message = f"🏄 東海村クソ下 週間波予測\n（{now_str} 更新）\n\n{forecast_text}"
    print(message)
    send_line(message)

if __name__ == "__main__":
    main()
