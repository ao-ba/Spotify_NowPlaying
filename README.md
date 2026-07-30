# 🎵 Spotify Now Playing Dashboard

A personal dashboard that displays the track you are currently playing on Spotify in real-time and allows you to check your recent playback history.

## 🚀 Quick Start

### 1. Spotify Developer Setup

1. Create an App on the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/).
2. Register `https://example.com/callback` (or your preferred URL) in the `Redirect URI` section.
3. Obtain your `Client ID`, `Client Secret` and `Redirect URL`.

### 2. Environment Configuration

Enter your credentials in the `environment` section of the `docker-compose.yml` file or Kubernetes Secrets.

```yaml
environment:
  - SPOTIPY_CLIENT_ID=<your_client_id>
  - SPOTIPY_CLIENT_SECRET=<your_client_secret>
  - SPOTIPY_REDIRECT_URI=<your_redirect_url>
```

### 3. Launch

Run the dashboard in the background:

```bash
docker compose up -d
```

Access `http://localhost:5000` in your browser.

If authentication is required, the **Web Setup Page** (`/setup`) will automatically appear:

1. Click **"Spotify で認証する"** to authorize your Spotify account.
2. Copy the redirected URL from your browser address bar.
3. Paste the URL into the setup form and submit.

Once submitted, `.spotifycache` will be created automatically and you'll be redirected to the dashboard!

### 4. (Optional) Public Access

If you want to access your dashboard from outside your local network (e.g., from your phone while on mobile data), you can use **Tailscale Funnel**.

```bash
tailscale funnel --bg http://127.0.0.1:5000/
```
