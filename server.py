import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import spotipy
from flask import Flask, redirect, render_template, request, url_for
from requests.exceptions import RequestException, Timeout
from spotipy import SpotifyException
from spotipy.oauth2 import SpotifyOAuth

app = Flask(__name__)
app.json.ensure_ascii = False

SPOTIFY_SCOPE = "user-read-currently-playing user-read-recently-played playlist-modify-public"
SPOTIFY_CACHE_PATH = ".spotifycache"
SPOTIFY_TIMEOUT_SECONDS = 10
SPOTIFY_API_RETRIES = 2
CACHE_TTL_SECONDS = 30
SETUP_PIN = os.environ.get("SETUP_PIN")


class _TTLCache:
    def __init__(self, ttl: float):
        self._ttl = ttl
        self._lock = threading.Lock()
        self._value = None
        self._expires_at = 0.0

    def get(self):
        with self._lock:
            if self._value is not None and time.monotonic() < self._expires_at:
                return self._value
        return None

    def set(self, value):
        with self._lock:
            self._value = value
            self._expires_at = time.monotonic() + self._ttl


_spotify_cache = _TTLCache(CACHE_TTL_SECONDS)
auth_manager = None


def create_auth_manager():
    return SpotifyOAuth(
        scope=SPOTIFY_SCOPE,
        open_browser=False,
        cache_path=SPOTIFY_CACHE_PATH,
        requests_timeout=SPOTIFY_TIMEOUT_SECONDS,
    )


def ensure_auth_manager(force_recreate=False):
    global auth_manager

    if auth_manager is None or force_recreate:
        auth_manager = create_auth_manager()

    token_info = auth_manager.validate_token(auth_manager.get_cached_token())
    if token_info:
        return auth_manager

    raise RuntimeError("Spotify authentication is missing or expired.")


def create_spotify_client(force_recreate_auth=False):
    return spotipy.Spotify(
        auth_manager=ensure_auth_manager(force_recreate=force_recreate_auth),
        language="ja",
        requests_timeout=SPOTIFY_TIMEOUT_SECONDS,
        retries=2,
        status_retries=2,
        backoff_factor=0.3,
    )


def should_retry_spotify_error(error):
    if isinstance(error, (Timeout, RequestException)):
        return True

    if isinstance(error, SpotifyException):
        return error.http_status in {401, 429, 500, 502, 503, 504}

    return False


def fetch_spotify_data():
    last_error = None

    for attempt in range(SPOTIFY_API_RETRIES):
        try:
            client = create_spotify_client(force_recreate_auth=attempt > 0)
            with ThreadPoolExecutor(max_workers=2) as executor:
                future_track = executor.submit(client.current_user_playing_track)
                future_history = executor.submit(
                    client.current_user_recently_played, limit=50
                )
                current_track_raw = future_track.result()
                history = future_history.result()
            return current_track_raw, history
        except Exception as error:
            last_error = error
            if attempt < SPOTIFY_API_RETRIES - 1 and should_retry_spotify_error(error):
                continue
            raise last_error


def pick_album_image(images, preferred_index=0):
    if not images:
        return None

    safe_index = preferred_index if preferred_index < len(images) else 0
    return images[safe_index]["url"]


def init():
    # 後方互換用: 初期化チェック
    sp_oauth = create_auth_manager()
    token = sp_oauth.validate_token(sp_oauth.get_cached_token())
    return token is not None


@app.route("/setup", methods=["GET", "POST"])
def setup():
    sp_oauth = create_auth_manager()

    # 1. すでに認証が完了している場合は 403 Forbidden でガード
    if sp_oauth.validate_token(sp_oauth.get_cached_token()):
        return (
            "<h3>🔒 セットアップはすでに完了しています。再設定するには `.spotifycache` ファイルを削除してください。</h3>",
            403,
        )

    error = None

    if request.method == "POST":
        # 2. SETUP_PIN が設定されている場合は PIN コードを検証
        if SETUP_PIN:
            input_pin = request.form.get("pin")
            if input_pin != SETUP_PIN:
                error = "PIN コードが一致しません。"
                auth_url = sp_oauth.get_authorize_url()
                return (
                    render_template(
                        "setup.html",
                        auth_url=auth_url,
                        error=error,
                        requires_pin=bool(SETUP_PIN),
                    ),
                    401,
                )

        response_url = request.form.get("response_url")
        if response_url:
            try:
                code = sp_oauth.parse_response_code(response_url.strip())
                sp_oauth.get_access_token(code, as_dict=False)
                return redirect(url_for("hist"))
            except Exception as e:
                error = str(e)
        else:
            error = "URLを入力してください。"

    auth_url = sp_oauth.get_authorize_url()
    return render_template(
        "setup.html",
        auth_url=auth_url,
        error=error,
        requires_pin=bool(SETUP_PIN),
    )


@app.route("/callback", methods=["GET"])
def callback():
    sp_oauth = create_auth_manager()
    code = request.args.get("code")
    if code:
        try:
            sp_oauth.get_access_token(code, as_dict=False)
            return redirect(url_for("hist"))
        except Exception as e:
            return redirect(url_for("setup", error=str(e)))
    return redirect(url_for("setup"))


@app.route("/", methods=["GET"])
def hist():
    # キャッシュチェック。未認証なら /setup へリダイレクト
    sp_oauth = create_auth_manager()
    token_info = sp_oauth.validate_token(sp_oauth.get_cached_token())
    if not token_info:
        return redirect(url_for("setup"))

    cached = _spotify_cache.get()
    if cached is not None:
        current_track_raw, history = cached
    else:
        try:
            current_track_raw, history = fetch_spotify_data()
        except RuntimeError:
            return redirect(url_for("setup"))
        except Exception as error:
            status_code = 503 if should_retry_spotify_error(error) else 500
            return f"Spotify API Error: {error}", status_code
        _spotify_cache.set((current_track_raw, history))

    current_track = None
    if current_track_raw and current_track_raw.get("is_playing"):
        item = current_track_raw["item"]
        current_track = {
            "name": item["name"],
            "artist": ", ".join([artist["name"] for artist in item["artists"]]),
            "album": item["album"]["name"],
            "url": item["external_urls"]["spotify"],
            "image_url": pick_album_image(item["album"]["images"]),
        }

    history_arr = []
    jst = timezone(timedelta(hours=+9))

    for value in history["items"]:
        played_at_str = value["played_at"].replace("Z", "+00:00")
        dt_utc = datetime.fromisoformat(played_at_str)
        dt_jst = dt_utc.astimezone(jst)

        track = value["track"]
        history_arr.append({
            "played_at": dt_jst.strftime("%Y-%m-%d %H:%M:%S"),
            "name": track["name"],
            "artist": ", ".join([artist["name"] for artist in track["artists"]]),
            "album": track["album"]["name"],
            "url": track["external_urls"]["spotify"],
            "image_url": pick_album_image(track["album"]["images"], preferred_index=1),
        })

    history_arr.sort(key=lambda x: x["played_at"], reverse=True)

    return render_template(
        "index.html", current_track=current_track, tracks=history_arr
    )


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
