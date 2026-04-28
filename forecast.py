#!/usr/bin/env python3
"""
東海村 週間波予測スクリプト
毎晩19時(JST)にGitHub Actionsで実行 → LINEに送信
"""
import os, json, datetime, requests

# ── 設定 ──────────────────────────────────────────────
LAT, LON = 36.46, 140.57        # 東海村クソ下付近
JST = datetime.timezone(datetime.timedelta(hours=9))
ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]
LINE_TOKEN    = os.environ["LINE_CHANNEL_ACCESS_TOKEN"]
LINE_USER_ID  = os.environ["LINE_USER_ID"]

# ── Instagram実績データ読み込み ─────────────────────────
def load_surf_history() -> list[dict]:
    path = os.path.join(os.path.dirname(__file__), "surf_history.json")
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

# ── 実績データから直近N日のサマリーを生成 ──
def build_history_context(history: list[dict], days: int = 14) -> str:
    if not history:
        return ""
    cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
    recent = [h for h in history if h.get("date", "") >= cutoff]
    if not recent:
        return ""
    lines = ["【過去の実測データ（stokeandsea Instagram）】"]
    for h in sorted(recent, key=lambda x: x["date"], reverse=True):
        d    = h.get("date", "?")
        size = h.get("wave_size", "?")
        wdir = h.get("wind_dir", "?")
        wspd = h.get("wind_speed_ms", "?")
        rate = h.get("rating", "?")
        note = h.get("conditions_note", "")
        lines.append(f"  {d}: {size} / {wdir}{wspd}m/s / ★{rate} {note}")
    return "\n".join(lines)

# ── 気象・波データ取得 (Open-Meteo / 無料・認証不要) ──
def fetch_forecast():
    # 風・天気データ（通常のforecast API）
    weather_url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={LAT}&longitude={LON}"
        "&daily=wind_speed_10m_max,wind_direction_10m_dominant,"
        "precipitation_sum,weather_code"
        "&wind_speed_unit=ms"
        "&timezone=Asia%2FTokyo"
        "&forecast_days=10"
    )
    wr = requests.get(weather_url, timeout=15)
    wr.raise_for_status()
    weather = wr.json()["daily"]

    # 波・うねりデータ（Marine API）
    marine_url = (
        "https://marine-api.open-meteo.com/v1/marine"
        f"?latitude={LAT}&longitude={LON}"
        "&daily=wave_height_max,wave_period_max,swell_wave_height_max,"
        "swell_wave_direction_dominant"
        "&timezone=Asia%2FTokyo"
        "&forecast_days=10"
    )
    mr = requests.get(marine_url, timeout=15)
    mr.raise_for_status()
    marine = mr.json()["daily"]

    return {**weather, **marine}

# ── JMA週間予報取得（茨城: 080000）──
def fetch_jma_weekly() -> dict:
    """気象庁週間予報 → {date_str: {weatherCode, wind_text, wave_text}}"""
    try:
        r = requests.get(
            "https://www.jma.go.jp/bosai/forecast/data/forecast/080000.json",
            timeout=15
        )
        r.raise_for_status()
        data = r.json()

        weekly = data[1]  # index 1 = 週間予報
        ts = weekly["timeSeries"][0]  # 天気コード・風・波

        # 日付リスト（"2026-04-29T05:00:00+09:00" → "2026-04-29"）
        dates = [d[:10] for d in ts["timeDefines"]]

        # エリア選択（水戸:40201 or 北部:080010 を優先）
        area_data = None
        for area in ts["areas"]:
            if area["area"]["code"] in ("40201", "080010"):
                area_data = area
                break
        if not area_data and ts["areas"]:
            area_data = ts["areas"][0]

        result = {}
        if area_data:
            codes = area_data.get("weatherCodes", [])
            winds = area_data.get("winds", [])
            waves = area_data.get("waves", [])
            for i, date in enumerate(dates):
                result[date] = {
                    "weatherCode": codes[i] if i < len(codes) else None,
                    "wind_text":   winds[i] if i < len(winds) else None,
                    "wave_text":   waves[i] if i < len(waves) else None,
                }
        return result
    except Exception as e:
        print(f"JMA週間予報取得失敗（スキップ）: {e}")
        return {}

# ── JMA天気コード → 絵文字 ──
def jma_weather_emoji(code: str) -> str:
    if not code:
        return "🌤"
    c = int(code)
    if c // 100 == 1:
        return "☀️" if c == 100 else "🌤"
    if c // 100 == 2:
        return "⛅"
    if c // 100 == 3:
        return "🌧"
    if c // 100 == 4:
        return "❄️"
    return "🌤"

# ── JMA風テキストから方角を抽出 ──
def jma_wind_dir(wind_text: str) -> str:
    """'北東の風　やや強く' → '北東'"""
    if not wind_text:
        return ""
    if "の風" in wind_text:
        return wind_text.split("の風")[0].strip()
    return ""

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
    if m < 0.1:  return "フラット（波なし）"
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
def generate_forecast_text(days_data: list[dict], history: list[dict]) -> str:
    system = (
        "あなたは茨城県東海村のサーフコーチです。"
        "東海村クソ下ポイントの1週間波予測を、地元サーファーのわたるさん向けに"
        "わかりやすく、具体的にまとめてください。"
        "特に朝イチ（5〜8時台）のサーフィン適性に注目してください。"
        "過去の実測データが提供される場合は、それを参考にして予測の精度を高めてください。"
        "数値モデルと実測値の傾向の差異（例：モデルより実際は波が大きい/小さい等）に注目してください。"
    )
    history_context = build_history_context(history, days=14)
    user = "以下のデータから東海村クソ下の7日間波予測をまとめてください：\n\n"
    if history_context:
        user += history_context + "\n\n"
    user += "【予測データ（気象庁JMA + Open-Meteo Marine）】\n"
    for d in days_data:
        user += (
            f"【{d['date']}（{d['dow']}）】\n"
            f"  波高: {d['wave_size']}  うねり: {d['swell_size']}（{d['swell_h']:.1f}m）\n"
            f"  風: {d['wind_dir']} {d['wind_speed']:.1f}m/s  {d['weather']}\n"
        )
        if d.get("jma_wind"):
            user += f"  JMA風: {d['jma_wind']}\n"
        if d.get("jma_wave"):
            user += f"  JMA波: {d['jma_wave']}\n"
        user += f"  潮汐: {d['tide']}\n\n"
    user += (
        "\n出力フォーマット（各日2行）:\n"
        "📅 [月/日]（[曜]）[天気絵文字] 🌊[波サイズ（パーツ表記）]\n"
        "   💨[風向][速度]m/s ／ [コンディション一言（例：オフショアで面ツル、オンショアでジャンク、etc）]\n"
        "\n必須ルール:\n"
        "・🌊の後には必ず波のサイズをパーツ表記（スネ/ヒザ/モモ/腰/腹/胸/肩/頭など）で書く。\n"
        "・波がない日は「🌊フラット（波なし）」と明記する。\n"
        "・風は向きと強さ（m/s）を必ず両方書く。オフショア/オンショア/サイドも一言に含める。\n"
        "・コンディション一言は面の状態（面ツル/ザワつき/ジャンク）や入れるかどうかを具体的に。\n"
        "最後に「今週のベスト」を一行でまとめる。\n"
        "全体400文字以内。ハッシュタグ不要。\n"
        "マークダウン記法（#, ##, **, __ など）は一切使わない。プレーンテキストのみ。"
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
    # JSTで「明日」を計算（GitHub ActionsはUTC動作のため明示的にJSTを使う）
    jst_now     = datetime.datetime.now(JST)
    tomorrow_jst = (jst_now + datetime.timedelta(days=1)).date()

    raw = fetch_forecast()   # Open-Meteo（波高・風速・天気コード）
    jma = fetch_jma_weekly() # JMA週間予報（天気コード・風テキスト・波テキスト）
    days_data = []
    dows = ["月","火","水","木","金","土","日"]

    # raw["time"] の中から JST翌日のインデックスを探す
    start_idx = 1  # フォールバック
    for idx, t in enumerate(raw["time"]):
        if datetime.date.fromisoformat(t) == tomorrow_jst:
            start_idx = idx
            break
    print(f"予報開始インデックス: {start_idx}（{raw['time'][start_idx]}〜）")

    for i in range(start_idx, start_idx + 7):
        if i >= len(raw["time"]):
            break
        date_str = raw["time"][i]
        date_obj = datetime.date.fromisoformat(date_str)
        swell_h_val = raw["swell_wave_height_max"][i] or 0

        # JMAデータ（その日付があれば優先）
        jma_day  = jma.get(date_str, {})
        jma_code = jma_day.get("weatherCode")
        jma_wind = jma_day.get("wind_text", "")
        jma_wave = jma_day.get("wave_text", "")

        # 天気絵文字: JMAコードを優先
        wx_emoji = jma_weather_emoji(jma_code) if jma_code else weather_emoji(raw["weather_code"][i] or 0)

        # 風向き: JMAテキストから方角を取得、なければOpen-Meteoの度数変換
        jma_dir = jma_wind_dir(jma_wind)
        wind_dir_str = jma_dir if jma_dir else wind_dir_name(raw["wind_direction_10m_dominant"][i] or 0)

        days_data.append({
            "date":       f"{date_obj.month}/{date_obj.day}",
            "dow":        dows[date_obj.weekday()],
            "wave_size":  wave_size(raw["wave_height_max"][i] or 0),
            "swell_h":    swell_h_val,
            "swell_size": wave_size(swell_h_val),
            "wind_dir":   wind_dir_str,
            "wind_speed": raw["wind_speed_10m_max"][i] or 0,
            "weather":    wx_emoji,
            "tide":       tide_phase(date_obj),
            "jma_wind":   jma_wind,
            "jma_wave":   jma_wave,
        })

    history = load_surf_history()
    print(f"実績データ読み込み: {len(history)}件")
    forecast_text = generate_forecast_text(days_data, history)

    now_str = datetime.datetime.now(JST).strftime("%Y/%m/%d %H:%M")
    message = f"🏄 東海村クソ下 週間波予測\n（{now_str} 更新）\n\n{forecast_text}"
    print(message)
    send_line(message)

if __name__ == "__main__":
    main()
