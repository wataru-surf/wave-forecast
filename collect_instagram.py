#!/usr/bin/env python3
"""
stokeandsea Instagram投稿からサーフデータを収集（instagrapi版）
毎朝GitHub Actionsで実行 → surf_history.jsonを更新 → リポジトリにコミット
"""
import json, os, re, datetime, requests, sys, base64, tempfile

INSTAGRAM_USER = "stokeandsea"
HISTORY_FILE   = os.path.join(os.path.dirname(__file__), "surf_history.json")
ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
MAX_NEW_POSTS  = 30
KEEP_DAYS      = 365

# ── キャプションからサーフデータをClaudeで抽出 ──
def parse_caption(caption: str, post_date: str) -> dict | None:
    prompt = f"""以下のInstagram投稿キャプションからサーフィン情報を抽出してください。

投稿日: {post_date}
キャプション:
{caption}

以下のJSONのみ返してください（情報がない場合はnull）:
{{
  "date": "YYYY-MM-DD",
  "time": "HH:MM",
  "wind_dir": "北北東",
  "wind_speed_ms": 5.6,
  "wave_size": "肩〜頭",
  "wave_size_m_est": 1.3,
  "conditions_note": "ミドルから厚くワイド気味",
  "rating": 3
}}

wave_size_m_est は以下を目安に数値化:
スネ=0.2 ヒザ=0.3 モモ=0.5 腰=0.6 腹=0.8 胸=1.0 肩=1.2 頭=1.5 頭オーバー=1.8 ダブル=2.5
rating は 1(波なし/最悪) 〜 5(最高) で推定。JSONのみ返すこと。"""

    try:
        r = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5-20251001",
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=20,
        )
        r.raise_for_status()
        text = r.json()["content"][0]["text"].strip()
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception as e:
        print(f"  ⚠️  Claude解析エラー: {e}", flush=True)
    return None

# ── メイン ──
def main():
    # 既存の履歴を読み込む
    history: list[dict] = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, encoding="utf-8") as f:
            history = json.load(f)
    existing_dates = {h["date"] for h in history}
    print(f"既存データ: {len(history)}件", flush=True)

    # セッション設定ファイルを読み込む
    session_b64 = os.environ.get("INSTAGRAM_SESSION", "")
    if not session_b64:
        print("⚠️ INSTAGRAM_SESSION が未設定。スキップします。", flush=True)
        sys.exit(0)

    # base64デコードしてJSONファイルとして保存
    session_json_bytes = base64.b64decode(session_b64)
    with tempfile.NamedTemporaryFile(mode='wb', suffix=".json", delete=False) as f:
        f.write(session_json_bytes)
        session_path = f.name

    try:
        from instagrapi import Client
        from instagrapi.exceptions import LoginRequired

        cl = Client()
        try:
            cl.load_settings(session_path)
            cl.login(INSTAGRAM_USER, "")  # セッション再利用（パスワード不要）
            print("✅ Instagramセッション読み込み完了", flush=True)
        except Exception as e:
            print(f"❌ セッション読み込み失敗: {e}", flush=True)
            sys.exit(0)

        # ユーザーIDを取得
        try:
            user_id = cl.user_id_from_username(INSTAGRAM_USER)
            print(f"✅ ユーザーID取得: {user_id}", flush=True)
        except Exception as e:
            print(f"❌ ユーザーID取得失敗: {e}", flush=True)
            sys.exit(0)

        # 投稿を取得
        try:
            medias = cl.user_medias(user_id, MAX_NEW_POSTS)
            print(f"✅ 投稿取得: {len(medias)}件", flush=True)
        except Exception as e:
            print(f"❌ 投稿取得失敗: {e}", flush=True)
            sys.exit(0)

        new_entries: list[dict] = []
        skipped = 0

        for media in medias:
            caption = media.caption_text or ""
            post_date = media.taken_at.strftime("%Y-%m-%d") if media.taken_at else ""

            if not post_date:
                continue

            days_ago = (datetime.date.today() - datetime.date.fromisoformat(post_date)).days
            if days_ago > KEEP_DAYS:
                break

            if "クソ下" not in caption:
                skipped += 1
                continue

            if post_date in existing_dates and days_ago > 7:
                continue

            parsed = parse_caption(caption, post_date)
            if not parsed:
                continue

            parsed["date"]         = post_date
            parsed["post_id"]      = str(media.pk)
            parsed["caption_head"] = caption[:80].replace("\n", " ")

            history = [h for h in history if h.get("date") != post_date]
            history.append(parsed)
            new_entries.append(parsed)
            print(f"  ✅ {post_date}: {parsed.get('wave_size','?')} / "
                  f"{parsed.get('wind_dir','?')} {parsed.get('wind_speed_ms','?')}m/s "
                  f"/ ★{parsed.get('rating','?')}", flush=True)

        print(f"\n新規取得: {len(new_entries)}件 / クソ下以外スキップ: {skipped}件", flush=True)

        if new_entries:
            cutoff = (datetime.date.today() - datetime.timedelta(days=KEEP_DAYS)).isoformat()
            history = [h for h in history if h.get("date", "") >= cutoff]
            history.sort(key=lambda x: x.get("date", ""), reverse=True)

            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
            print(f"✅ surf_history.json を更新（合計 {len(history)}件）", flush=True)
        else:
            print("更新なし", flush=True)

    finally:
        os.unlink(session_path)

if __name__ == "__main__":
    main()
