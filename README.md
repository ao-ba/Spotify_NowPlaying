# 🎵 Spotify Now Playing Dashboard
A personal dashboard that displays the track you are currently playing on Spotify in real-time and allows you to check your recent playback history.
## 🚀 Quick Start
### 1. Spotify Developer Setup
1.  Create an App on the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/).
2.  Register `https://example.com/callback` (or your preferred URL) in the `Redirect URI` section.
3.  Obtain your `Client ID`, `Client Secret` and `Redirect URL`.
### 2. Environment Configuration
Enter your credentials in the `environment` section of the `docker-compose.yml` file.
```YAML
environment:
  - SPOTIPY_CLIENT_ID=<your_client_id>
  - SPOTIPY_CLIENT_SECRET=<your_client_secret>
  - SPOTIPY_REDIRECT_URI=<your_redirect_url>
```

### 3. Launch
To get started, you need to complete the initial Spotify authentication.

Step 1: Initial Authentication Run the following command to start the container in interactive mode and follow the on-screen instructions to authorize your Spotify account:

```Bash
docker compose run -it --rm dashboard
```
Once the message "Success! '.spotifycache' has been created" appears, the setup is complete and the container will exit.

Step 2: Normal Operation After the initial setup, you can run the dashboard in the background:

```Bash
docker compose up -d
```
Access http://localhost:5000 in your browser.

### 4.(Optional)Public Access
If you want to access your dashboard from outside your local network (e.g., from your phone while on mobile data), you can use **Tailscale Funnel**. This allows you to securely expose your local server to the public internet.
1.  Ensure you have [Tailscale](https://tailscale.com/) installed and Funnel enabled on your account.  
2.  Run the following command in your terminal:
```Bash
tailscale funnel --bg http://127.0.0.1:5000/
```
This will run in the background and provide you with a public URL (e.g., `https://your-node-name.tailscale.net`).
