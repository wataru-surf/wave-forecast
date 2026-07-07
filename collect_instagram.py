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
JST = datetime.timezone(datetime.timedelta(hours=9))

def today_jst() -> datetime.date:
    """Actions(UTC)上でも日付がズレないようJSTで「今日」を返す"""
    return datetime.datetime.now(JST).date()

# ── セッション失効などをLINEに通知（サイレント劣化の防止）──
def notify_line(text: str):
    token   = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
    user_id = os.environ.get("LINE_USER_ID", "")
    if not token or not user_id:
        return  # ローカル実行時など、未設定なら黙ってスキップ
    try:
        requests.post(
            "https://api.line.me/v2/bot/message/push",
            headers={"Authorization": f"Bearer {token}",
                     "Content-Type": "application/json"},
            json={"to": user_id, "messages": [{"type": "text", "text": text}]},
            timeout=15,
        )
    except Exception as e:
        print(f"LINE通知失敗: {e}", flush=True)

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
    if not session_json_bytes.lstrip().startswith(b"{"):
        # instagrapi の dump_settings はJSON形式（先頭が "{"）。
        # 先頭 0x80 等ならpickle形式（instaloader等の別ツール）が誤登録されている
        print("❌ INSTAGRAM_SESSION がJSON形式ではありません"
              f"（先頭バイト: {session_json_bytes[:2]!r}）。", flush=True)
        print("   → instaloader等の別形式の可能性。setup_instagram_session.py で"
              "再生成・再登録してください。", flush=True)
        sys.exit(0)
    with tempfile.NamedTemporaryFile(mode='wb', suffix=".json", delete=False) as f:
        f.write(session_json_bytes)
        session_path = f.name

    try:
        from instagrapi import Client
        from instagrapi.exceptions import LoginRequired

        cl = Client()
        try:
            cl.load_settings(session_path)
            # login()は呼ばない（空パスワードは新instagrapiが拒否する）。
            # セッションが有効かはAPI呼び出しで検証する
            account = cl.account_info()
            print(f"✅ Instagramセッション読み込み完了（@{account.username}）", flush=True)
        except Exception as e:
            print(f"❌ セッション読み込み失敗: {e}", flush=True)
            notify_line(
                "⚠️ Instagram実測データの収集が止まっています\n"
                "（セッション失効の可能性）\n\n"
                "波予測の配信は続きますが実測補正が効きません。\n"
                "復旧: ターミナルで\n"
                "cd \"/Users/wataru/Desktop/波情報（Code）ファイル/wave-forecast\"\n"
                "python3 setup_instagram_session_v2.py\n"
                "（Chromeのsessionidを貼り付け）"
            )
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
        processed_dates: set[str] = set()  # 同日複数投稿は最新（先に返る）を採用
        skipped = 0

        for media in medias:
            caption = media.caption_text or ""
            post_date = media.taken_at.strftime("%Y-%m-%d") if media.taken_at else ""

            if not post_date:
                continue

            days_ago = (today_jst() - datetime.date.fromisoformat(post_date)).days
            if days_ago > KEEP_DAYS:
                # break禁止: ピン留め投稿は日付順を崩して先頭に返るため、
                # 古いピン留め1件で全件スキップされる事故を防ぐ
                continue

            if "クソ下" not in caption:
                skipped += 1
                continue

            if post_date in processed_dates:
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
            processed_dates.add(post_date)
            print(f"  ✅ {post_date}: {parsed.get('wave_size','?')} / "
                  f"{parsed.get('wind_dir','?')} {parsed.get('wind_speed_ms','?')}m/s "
                  f"/ ★{parsed.get('rating','?')}", flush=True)

        print(f"\n新規取得: {len(new_entries)}件 / クソ下以外スキップ: {skipped}件", flush=True)

        if new_entries:
            cutoff = (today_jst() - datetime.timedelta(days=KEEP_DAYS)).isoformat()
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
