#!/usr/bin/env python3
"""
stokeandsea Instagram投稿からサーフデータを収集
毎朝GitHub Actionsで実行 → surf_history.jsonを更新 → リポジトリにコミット
"""
import instaloader, json, os, re, datetime, requests, sys

INSTAGRAM_USER = "stokeandsea"
HISTORY_FILE   = os.path.join(os.path.dirname(__file__), "surf_history.json")
ANTHROPIC_KEY  = os.environ.get("ANTHROPIC_API_KEY", "")
MAX_NEW_POSTS  = 30   # 1回の実行で最大取得数
KEEP_DAYS      = 365  # 何日分保持するか

# ── キャプションからサーフデータをClaudeで抽出 ──────────────────────────
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
        print(f"  ⚠️  Claude解析エラー: {e}", file=sys.stderr)
    return None

# ── メイン ───────────────────────────────────────────────────────────────
def main():
    # 既存の履歴を読み込む
    history: list[dict] = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, encoding="utf-8") as f:
            history = json.load(f)
    existing_dates = {h["date"] for h in history}
    print(f"既存データ: {len(history)}件")

    # Instagram から投稿を取得
    L = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        quiet=True,
    )

    # GitHub Secret の INSTAGRAM_SESSION からセッションを復元
    session_b64 = os.environ.get("INSTAGRAM_SESSION", "")
    if session_b64:
        import tempfile, base64
        session_bytes = base64.b64decode(session_b64)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".session") as f:
            f.write(session_bytes)
            session_path = f.name
        try:
            L.load_session_from_file(INSTAGRAM_USER, session_path)
            print("✅ Instagramセッション読み込み完了")
        except Exception as e:
            print(f"⚠️  セッション読み込み失敗（未ログインで試行）: {e}", file=sys.stderr)
        finally:
            os.unlink(session_path)
    else:
        print("⚠️  INSTAGRAM_SESSION が未設定。未認証でアクセスします（失敗する場合あり）")

    try:
        profile = instaloader.Profile.from_username(L.context, INSTAGRAM_USER)
    except Exception as e:
        print(f"❌ Instagram取得失敗: {e}", file=sys.stderr)
        sys.exit(0)  # 失敗してもワークフロー全体は止めない

    new_entries: list[dict] = []
    skipped = 0

    for post in profile.get_posts():
        if len(new_entries) >= MAX_NEW_POSTS:
            break

        post_date_str = post.date_local.strftime("%Y-%m-%d")

        # 1年以上前はスキップ
        days_ago = (datetime.date.today() - post.date_local.date()).days
        if days_ago > KEEP_DAYS:
            break

        # クソ下の投稿のみ対象
        caption = post.caption or ""
        if "クソ下" not in caption:
            skipped += 1
            continue

        # 既存データはスキップ（ただし直近7日は再取得して更新）
        if post_date_str in existing_dates and days_ago > 7:
            continue

        parsed = parse_caption(caption, post_date_str)
        if not parsed:
            continue

        parsed["date"]         = post_date_str
        parsed["post_id"]      = post.shortcode
        parsed["caption_head"] = caption[:80].replace("\n", " ")

        # 既存エントリを上書き or 新規追加
        history = [h for h in history if h.get("date") != post_date_str]
        history.append(parsed)
        new_entries.append(parsed)
        print(f"  ✅ {post_date_str}: {parsed.get('wave_size','?')} / "
              f"{parsed.get('wind_dir','?')} {parsed.get('wind_speed_ms','?')}m/s "
              f"/ rating={parsed.get('rating','?')}")

    print(f"\n新規取得: {len(new_entries)}件 / クソ下以外スキップ: {skipped}件")

    if new_entries:
        # 日付降順でソート、古いデータを削除
        cutoff = (datetime.date.today() - datetime.timedelta(days=KEEP_DAYS)).isoformat()
        history = [h for h in history if h.get("date", "") >= cutoff]
        history.sort(key=lambda x: x.get("date", ""), reverse=True)

        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
        print(f"✅ surf_history.json を更新（合計 {len(history)}件）")
    else:
        print("更新なし")

if __name__ == "__main__":
    main()
