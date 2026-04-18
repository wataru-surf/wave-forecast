#!/usr/bin/env python3
"""
【初回1回だけ実行】Instagramセッションを作成してGitHub Secretsに登録する
実行: python3 setup_instagram_session.py
"""
import instaloader, base64, os, tempfile, subprocess, sys, getpass

INSTAGRAM_USER = "stokeandsea"
REPO = "wataru-surf/wave-forecast"
# GitHub PAT は環境変数 GITHUB_PAT から読み込む
PAT = os.environ.get("GITHUB_PAT", "")

print("=" * 50)
print("📸 Instagram セッション セットアップ")
print("=" * 50)
print(f"\nアカウント: @{INSTAGRAM_USER}")
if not PAT:
    PAT = input("GitHub PAT（ghp_で始まるトークン）を入力: ").strip()
print("Instagramのパスワードを入力してください（画面には表示されません）\n")

password = getpass.getpass(f"@{INSTAGRAM_USER} のパスワード: ")

# instaloader でログイン
L = instaloader.Instaloader(quiet=True)
try:
    L.login(INSTAGRAM_USER, password)
    print("✅ ログイン成功！")
except instaloader.exceptions.TwoFactorAuthRequiredException:
    code = input("📱 2段階認証コードを入力: ").strip()
    L.two_factor_login(code)
    print("✅ 2段階認証完了！")
except Exception as e:
    print(f"❌ ログイン失敗: {e}")
    sys.exit(1)

# セッションファイルを取得してbase64エンコード
session_path = os.path.join(tempfile.gettempdir(), f"session-{INSTAGRAM_USER}")
L.save_session_to_file(session_path)

with open(session_path, "rb") as f:
    session_b64 = base64.b64encode(f.read()).decode()

os.unlink(session_path)
print(f"✅ セッション作成完了（サイズ: {len(session_b64)}文字）")

# GitHub Secretsに登録
print("\nGitHub Secretsに登録中...")

try:
    import requests
    from nacl.public import PublicKey, SealedBox

    headers = {
        "Authorization": f"Bearer {PAT}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"
    }
    r = requests.get(
        f"https://api.github.com/repos/{REPO}/actions/secrets/public-key",
        headers=headers
    )
    key_data = r.json()
    key_id = key_data["key_id"]
    pub_key_b64 = key_data["key"]

    import base64 as b64
    pk = PublicKey(b64.b64decode(pub_key_b64))
    box = SealedBox(pk)
    encrypted = b64.b64encode(box.encrypt(session_b64.encode())).decode()

    r2 = requests.put(
        f"https://api.github.com/repos/{REPO}/actions/secrets/INSTAGRAM_SESSION",
        headers=headers,
        json={"encrypted_value": encrypted, "key_id": key_id}
    )
    if r2.status_code in (201, 204):
        print("✅ INSTAGRAM_SESSION をGitHub Secretsに登録しました！")
    else:
        print(f"❌ 登録失敗: HTTP {r2.status_code} {r2.text}")

except Exception as e:
    print(f"❌ GitHub登録エラー: {e}")
    print(f"\n手動登録用 セッション値（コピーしてGitHub Secretsに貼り付け）:")
    print(f"Secret名: INSTAGRAM_SESSION")
    print(f"値: {session_b64[:50]}...（省略）")

print("\n" + "=" * 50)
print("✅ セットアップ完了！")
print("次回からGitHub Actionsが自動でInstagramデータを収集します。")
print("=" * 50)
