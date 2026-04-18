#!/usr/bin/env python3
"""
【初回1回だけ実行】Instagramセッションを作成してGitHub Secretsに登録する
実行: python3 setup_instagram_session.py
"""
import base64, os, sys, getpass, json, tempfile, requests

INSTAGRAM_USER = "stokeandsea"
REPO = "wataru-surf/wave-forecast"
PAT = os.environ.get("GITHUB_PAT", "")

print("=" * 50)
print("📸 Instagram セッション セットアップ（instagrapi版）")
print("=" * 50)
print(f"\nアカウント: @{INSTAGRAM_USER}")

if not PAT:
    PAT = input("GitHub PAT（ghp_で始まるトークン）を入力: ").strip()

password = getpass.getpass(f"@{INSTAGRAM_USER} のパスワード: ")

try:
    from instagrapi import Client
    cl = Client()
    # ログイン
    cl.login(INSTAGRAM_USER, password)
    print("✅ ログイン成功！", flush=True)

    # セッション設定をJSONとして保存
    session_path = os.path.join(tempfile.gettempdir(), f"instagrapi-{INSTAGRAM_USER}.json")
    cl.dump_settings(session_path)

    with open(session_path, "rb") as f:
        session_b64 = base64.b64encode(f.read()).decode()

    os.unlink(session_path)
    print(f"✅ セッション作成完了（サイズ: {len(session_b64)}文字）", flush=True)

except Exception as e:
    print(f"❌ ログイン失敗: {e}")
    sys.exit(1)

# GitHub Secretsに登録
print("\nGitHub Secretsに登録中...")
try:
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

    pk = PublicKey(base64.b64decode(pub_key_b64))
    box = SealedBox(pk)
    encrypted = base64.b64encode(box.encrypt(session_b64.encode())).decode()

    r2 = requests.put(
        f"https://api.github.com/repos/{REPO}/actions/secrets/INSTAGRAM_SESSION",
        headers=headers,
        json={"encrypted_value": encrypted, "key_id": key_id}
    )
    if r2.status_code in (201, 204):
        print("✅ INSTAGRAM_SESSION をGitHub Secretsに登録しました！")
    else:
        print(f"❌ 登録失敗: HTTP {r2.status_code}")

except Exception as e:
    print(f"❌ GitHub登録エラー: {e}")

print("\n" + "=" * 50)
print("✅ セットアップ完了！")
print("=" * 50)
