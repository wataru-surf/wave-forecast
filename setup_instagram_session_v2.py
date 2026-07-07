#!/usr/bin/env python3
"""
【v2】ブラウザのsessionidからInstagramセッションを作成してGitHub Secretsに登録する
パスワードログイン不要（Instagram側のIPブロックを回避できる）
実行: python3 setup_instagram_session_v2.py
"""
import base64, os, sys, json, tempfile, subprocess

INSTAGRAM_USER = "stokeandsea"
REPO = "wataru-surf/wave-forecast"

print("=" * 50)
print("📸 Instagram セッション セットアップ v2（sessionid版）")
print("=" * 50)
print(f"\nアカウント: @{INSTAGRAM_USER}")
print("\nChromeの instagram.com からコピーした sessionid を貼り付けてください。")

sessionid = input("sessionid: ").strip().strip('"').strip("'")
if not sessionid:
    print("❌ 空です。中断します。")
    sys.exit(1)

try:
    from instagrapi import Client
    cl = Client()
    cl.login_by_sessionid(sessionid)
    info = cl.account_info()
    print(f"✅ ログイン成功！（@{info.username}）", flush=True)
    if info.username != INSTAGRAM_USER:
        print(f"⚠️ 想定アカウント（@{INSTAGRAM_USER}）と異なります。"
              "ブラウザのログインアカウントを確認してください。")
        sys.exit(1)

    # セッション設定をJSONとして保存 → base64化
    session_path = os.path.join(tempfile.gettempdir(), f"instagrapi-{INSTAGRAM_USER}.json")
    cl.dump_settings(session_path)
    with open(session_path, "rb") as f:
        session_b64 = base64.b64encode(f.read()).decode()
    os.unlink(session_path)
    print(f"✅ セッション作成完了（サイズ: {len(session_b64)}文字）", flush=True)

except Exception as e:
    print(f"❌ ログイン失敗: {e}")
    sys.exit(1)

# GitHub Secretsに登録（gh CLI使用・PAT不要）
print("\nGitHub Secretsに登録中...")
r = subprocess.run(
    ["gh", "secret", "set", "INSTAGRAM_SESSION", "-R", REPO],
    input=session_b64.encode(),
    capture_output=True,
)
if r.returncode == 0:
    print("✅ INSTAGRAM_SESSION をGitHub Secretsに登録しました！")
else:
    print(f"❌ 登録失敗: {r.stderr.decode()}")
    sys.exit(1)

print("\n" + "=" * 50)
print("✅ セットアップ完了！")
print("=" * 50)
