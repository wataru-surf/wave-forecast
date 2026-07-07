# 週間波予測 セットアップガイド

> ✅ **このセットアップは完了済みです（2026-07-07 時点で毎晩稼働中）**。以下は初期構築時の記録として残しています。
> - リポジトリ：`wataru-surf/wave-forecast`（Push済・Secrets 4種登録済）
> - Instagramセッションの再登録は **`setup_instagram_session_v2.py`（sessionid方式）** を使うこと（本ガイドのパスワード方式はIPブロックで失敗する）

## わたるさん用 / 所要時間：約20分

---

## 必要なもの（すべて無料）
1. **GitHub** アカウント → コードを動かす場所
2. **LINE Developers** アカウント → LINEに送るための設定
3. Claude APIキー → すでに取得済み ✅

---

## STEP 1: GitHubアカウント作成（5分）

1. https://github.com/signup を開く
2. メールアドレスで登録
3. ユーザー名は `surf-wataru` などで OK

---

## STEP 2: GitHubリポジトリ作成（2分）

1. GitHubにログイン → 右上 「+」→「New repository」
2. Repository name: `wave-forecast`
3. **Private** を選択（非公開）
4. 「Create repository」

---

## STEP 3: ファイルをアップロード（3分）

リポジトリのページで「uploading an existing file」をクリック。
以下のファイルをドラッグ&ドロップ：
- `forecast.py`
- `requirements.txt`
- `.github/workflows/nightly-forecast.yml`

「Commit changes」で保存。

---

## STEP 4: LINE Developers設定（5分）

1. https://developers.line.biz/ → LINEアカウントでログイン
2. 「Create a new provider」→ 名前は「surf-wataru」
3. 「Create a Messaging API channel」
4. チャンネル名: 「波情報」など
5. 作成後、「Messaging API」タブ →「Channel access token」→「Issue」
6. 発行されたトークンをコピー（後で使う）

### あなたのLINE User IDを取得
1. 同じページの「Basic settings」タブ
2. 「Your user ID」に表示されている `Uxxxxxxxx...` をコピー

### LINEの友だち追加
- 「Messaging API」タブのQRコードをLINEで読み取る（自分のBotを友だち追加）

---

## STEP 5: GitHub Secretsに登録（3分）

GitHubのリポジトリ → Settings → Secrets and variables → Actions → New repository secret

| Name | Value |
|---|---|
| `ANTHROPIC_API_KEY` | sk-ant-api03-... （あなたのClaudeキー） |
| `LINE_CHANNEL_ACCESS_TOKEN` | STEP4で取得したLINEトークン |
| `LINE_USER_ID` | STEP4で取得したUser ID（Uで始まる） |

---

## STEP 6: 動作確認（1分）

GitHub → リポジトリ → Actions タブ →
「東海村 週間波予測」→「Run workflow」→「Run workflow」

LINEに予測が届けば完了！🏄

---

## 毎晩22時に自動で届くようになります 🌊

問題があればClaude Codeに「週間予測エラー」と貼り付けてください。
