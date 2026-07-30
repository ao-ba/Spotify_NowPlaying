# 🎵 Spotify Now Playing Dashboard

Spotify で現在再生中の曲をリアルタイムで表示し、直近の再生履歴を一覧で確認できる個人用 Web ダッシュボードです。

---

## 🚀 クイックスタート (Docker Compose)

### 1. Spotify Developer アプリの準備
1. [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/) にログインし、新しい App を作成します。
2. アプリの `Settings` で **Redirect URIs** に使用する URL を登録します。
   - 例: `https://127.0.0.1/callback` や `http://localhost:5000/callback`
3. 発行された **Client ID** と **Client Secret** を手元に控えます。

### 2. 環境変数の設定
`.env.example` をコピーして `.env` を作成し、Spotify の認証情報を入力します：

```bash
cp .env.example .env
```

```env
SPOTIPY_CLIENT_ID=your_client_id_here
SPOTIPY_CLIENT_SECRET=your_client_secret_here
SPOTIPY_REDIRECT_URI=https://127.0.0.1/callback
```

### 3. コンテナの起動
コンテナをバックグラウンドで起動します：

```bash
docker compose up -d
```

### 4. Web ブラウザでの初回認証（セットアップ）
1. コンテナの起動ログを確認し、自動生成された **`SETUP_PIN`** を取得します：
   ```bash
   docker compose logs
   ```
   *ログ出力例:*
   ```text
   ======================================================================
   [SECURITY] SETUP_PIN environment variable was not specified.
   [SECURITY] A temporary random SETUP_PIN has been generated for setup:

       SETUP_PIN = s5toD0IO5lQd

   [SECURITY] Use this PIN when accessing the /setup page in your browser.
   ======================================================================
   ```

2. ブラウザで `http://localhost:5000` にアクセスします（未認証時は自動で `/setup` に誘導されます）。
3. 取得した `SETUP_PIN` を入力して「認証して進む」をクリックします。
4. **「1. Spotify で認証する」** ボタンを押し、Spotify の認可画面で「同意する」をクリックします。
5. 認可後にブラウザのアドレスバーに表示された URL（例: `https://127.0.0.1/callback?code=...`）をコピーし、セットアップ画面の **「2. リダイレクト URL の貼り付け」** フォームに貼り付けて送信します。
6. 認証キャッシュ (`.spotifycache`) が保存され、ダッシュボード画面が表示されます！

---

## 🛡️ セキュリティ仕様

- **2段階 PIN 認証ウォール**  
  セットアップ画面 (`/setup`) にアクセスした際、正しく PIN コードを入力するまで Spotify 認可 URL（Client ID や Redirect URI 情報）は一切レンダリング・非公開化されます。
- **自動生成 PIN & ログ出力**  
  環境変数 `SETUP_PIN` が指定されていない場合、サーバー起動時に 12 桁のランダムな PIN コードが自動生成され標準出力ログに出力されます。（※手動で固定の PIN コードを指定したい場合は、`.env` に `SETUP_PIN=your_custom_pin` を追加してください）。
- **認証完了後の自動ロックアウト**  
  初回認証が正常に完了すると、第三者による再セットアップや上書きを防ぐため、以降の `/setup` へのアクセスは `403 Forbidden` で自動的に遮断されます。（再設定したい場合は `.spotifycache` ファイルを削除してください）。

---

## ☸️ k3s / Kubernetes へのデプロイ

k3s 環境向けのマニフェスト [k3s-deployment.yaml](k3s-deployment.yaml) を用意しています。

### デプロイ手順

1. **`k3s-deployment.yaml` の編集**  
   Secret の `SPOTIPY_CLIENT_ID` と `SPOTIPY_CLIENT_SECRET` に自身の認証情報を入力します。

2. **マニフェストの適用**  
   ```bash
   kubectl apply -f k3s-deployment.yaml
   ```

3. **PIN コードの確認と初期設定**  
   Pod のログを確認して自動生成された PIN を取得します：
   ```bash
   kubectl logs -n spotify deployment/spotify-nowplaying
   ```
   Ingress や Service 経由でブラウザからアクセスし、初回認証を完結させます。認証キャッシュ (`.spotifycache`) は PVC (`subPath`) 経由で安全に永続化されるため、Pod の再作成・再起動後も認証が維持されます。

---

## 🌐 (オプション) 外出先・スマホからのアクセス

Tailscale Funnel 等を利用することで、ローカルサーバーを安全にパブリックインターネットに公開できます。

```bash
tailscale funnel --bg http://127.0.0.1:5000/
```
