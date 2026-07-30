import os
import secrets
import string
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import spotipy
from flask import Flask, redirect, render_template, request, session, url_for
from requests.exceptions import RequestException, Timeout
from spotipy import SpotifyException
from spotipy.oauth2 import SpotifyOAuth

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(24)
app.json.ensure_ascii = False

SPOTIFY_SCOPE = "user-read-currently-playing user-read-recently-played playlist-modify-public"
SPOTIFY_CACHE_PATH = os.environ.get("SPOTIPY_CACHE_PATH", ".spotifycache")
SPOTIFY_TIMEOUT_SECONDS = 10
SPOTIFY_API_RETRIES = 2
CACHE_TTL_SECONDS = 30
DEFAULT_FAVICON_SVG = "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🎵</text></svg>"

# キャッシュ保存用ディレクトリの確保
cache_dir = os.path.dirname(SPOTIFY_CACHE_PATH)
if cache_dir:
    os.makedirs(cache_dir, exist_ok=True)


def _init_setup_pin() -> str:
    env_pin = os.environ.get("SETUP_PIN")
    if env_pin:
        print("[SECURITY] Using custom SETUP_PIN from environment variable.", flush=True)
        return env_pin

    alphabet = string.ascii_letters + string.digits
    random_pin = "".join(secrets.choice(alphabet) for _ in range(12))

    print("\n" + "=" * 70, flush=True)
    print("[SECURITY] SETUP_PIN environment variable was not specified.", flush=True)
    print("[SECURITY] A temporary random SETUP_PIN has been generated for setup:\n", flush=True)
    print(f"    SETUP_PIN = {random_pin}\n", flush=True)
    print("[SECURITY] Use this PIN when accessing the /setup page in your browser.", flush=True)
    print("=" * 70 + "\n", flush=True)

    return random_pin


SETUP_PIN = _init_setup_pin()


class _TTLCache:
    """インメモリの TTL キャッシュクラス"""

    def __init__(self, ttl: float):
        self._ttl = ttl
        self._lock = threading.Lock()
        self._value = None
        self._expires_at = 0.0

    def get(self) -> Optional[Any]:
        with self._lock:
            if self._value is not None and time.monotonic() < self._expires_at:
                return self._value
        return None

    def set(self, value: Any) -> None:
        with self._lock:
            self._value = value
            self._expires_at = time.monotonic() + self._ttl


_spotify_cache = _TTLCache(CACHE_TTL_SECONDS)


def create_auth_manager() -> SpotifyOAuth:
    return SpotifyOAuth(
        scope=SPOTIFY_SCOPE,
        open_browser=False,
        cache_path=SPOTIFY_CACHE_PATH,
        requests_timeout=SPOTIFY_TIMEOUT_SECONDS,
    )


def ensure_auth_manager(force_recreate: bool = False) -> SpotifyOAuth:
    auth_mgr = create_auth_manager()
    token_info = auth_mgr.validate_token(auth_mgr.get_cached_token())
    if token_info:
        return auth_mgr
    raise RuntimeError("Spotify authentication is missing or expired.")


def create_spotify_client(force_recreate_auth: bool = False) -> spotipy.Spotify:
    return spotipy.Spotify(
        auth_manager=ensure_auth_manager(force_recreate=force_recreate_auth),
        language="ja",
        requests_timeout=SPOTIFY_TIMEOUT_SECONDS,
        retries=2,
        status_retries=2,
        backoff_factor=0.3,
    )


def should_retry_spotify_error(error: Exception) -> bool:
    if isinstance(error, (Timeout, RequestException)):
        return True
    if isinstance(error, SpotifyException):
        return error.http_status in {401, 429, 500, 502, 503, 504}
    return False


def fetch_spotify_data() -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
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


def pick_album_image(images: List[Dict[str, Any]], preferred_index: int = 0) -> Optional[str]:
    if not images:
        return None
    safe_index = preferred_index if preferred_index < len(images) else 0
    return images[safe_index]["url"]


def format_time_ms(ms: int) -> str:
    """ミリ秒を mm:ss 形式の文字列に変換"""
    seconds = max(0, int(ms) // 1000)
    minutes = seconds // 60
    rem_seconds = seconds % 60
    return f"{minutes:02d}:{rem_seconds:02d}"


def format_track_item(item: Dict[str, Any], progress_ms: Optional[int] = 0) -> Dict[str, Any]:
    """現在再生中のトラックデータ（進捗状況含む）を画面表示用にフォーマット"""
    duration_ms = item.get("duration_ms", 0)
    prog_ms = progress_ms or 0
    percent = round((prog_ms / duration_ms) * 100, 1) if duration_ms > 0 else 0.0

    return {
        "name": item["name"],
        "artist": ", ".join([artist["name"] for artist in item["artists"]]),
        "album": item["album"]["name"],
        "url": item["external_urls"]["spotify"],
        "image_url": pick_album_image(item["album"]["images"]),
        "progress_ms": prog_ms,
        "duration_ms": duration_ms,
        "progress_percent": min(100.0, max(0.0, percent)),
        "progress_str": format_time_ms(prog_ms),
        "duration_str": format_time_ms(duration_ms),
    }


def format_history_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """再生履歴データを JST 時刻変換および画面表示用にフォーマット"""
    history_arr = []
    jst = timezone(timedelta(hours=+9))

    for value in items:
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
    return history_arr


def init() -> bool:
    try:
        sp_oauth = create_auth_manager()
        token = sp_oauth.validate_token(sp_oauth.get_cached_token())
        return token is not None
    except Exception:
        return False


@app.route("/favicon.ico")
def favicon():
    return redirect(DEFAULT_FAVICON_SVG)


@app.route("/setup", methods=["GET", "POST"])
def setup():
    sp_oauth = None
    try:
        sp_oauth = create_auth_manager()
        # すでに認証が完了している場合は 403 Forbidden
        if sp_oauth.validate_token(sp_oauth.get_cached_token()):
            return (
                "<h3>🔒 セットアップはすでに完了しています。再設定するには `.spotifycache` ファイルを削除してください。</h3>",
                403,
            )
    except Exception:
        pass

    error = None
    input_pin = request.form.get("pin") or session.get("setup_pin")
    is_pin_authenticated = (input_pin == SETUP_PIN) or session.get("setup_authenticated", False)

    if request.method == "POST":
        action = request.form.get("action")

        # 段階1: PIN コードの検証
        if action == "verify_pin" or not is_pin_authenticated:
            if input_pin == SETUP_PIN:
                session["setup_pin"] = input_pin
                session["setup_authenticated"] = True
                is_pin_authenticated = True
            else:
                error = "PIN コードが一致しません。"
                return (
                    render_template(
                        "setup.html",
                        is_authenticated=False,
                        error=error,
                    ),
                    401,
                )

        # 段階2: URL の送信とトークン引き換え
        if action == "submit_url" and is_pin_authenticated:
            response_url = request.form.get("response_url")
            if response_url and sp_oauth:
                try:
                    code = sp_oauth.parse_response_code(response_url.strip())
                    token_info = sp_oauth.get_access_token(code, as_dict=False)
                    if token_info:
                        session.pop("setup_authenticated", None)
                        session.pop("setup_pin", None)
                        return redirect(url_for("hist"))
                    else:
                        error = "トークンの取得に失敗しました。URLを再度確認してください。"
                except Exception as e:
                    error = f"認証エラー: {e}"
            else:
                error = "URLを入力するか環境変数を設定してください。"

    # PIN 未認証時: 認証リンク (auth_url) は生成せず PIN 入力画面のみ表示
    if not is_pin_authenticated:
        return render_template(
            "setup.html",
            is_authenticated=False,
            error=error,
        )

    # PIN 認証成功済みの場合のみ: Spotify 認可 URL を生成して表示
    try:
        auth_url = sp_oauth.get_authorize_url() if sp_oauth else "#"
    except Exception as e:
        auth_url = "#"
        error = error or f"Spotify 設定エラー (CLIENT_ID未設定等): {e}"

    return render_template(
        "setup.html",
        is_authenticated=True,
        auth_url=auth_url,
        error=error,
        pin=input_pin or SETUP_PIN,
    )


@app.route("/callback", methods=["GET"])
def callback():
    try:
        sp_oauth = create_auth_manager()
        code = request.args.get("code")
        if code:
            sp_oauth.get_access_token(code, as_dict=False)
            return redirect(url_for("hist"))
    except Exception as e:
        return redirect(url_for("setup", error=str(e)))
    return redirect(url_for("setup"))


@app.route("/", methods=["GET"])
def hist():
    try:
        sp_oauth = create_auth_manager()
        token_info = sp_oauth.validate_token(sp_oauth.get_cached_token())
        if not token_info:
            return redirect(url_for("setup"))
    except Exception:
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
        progress_ms = current_track_raw.get("progress_ms", 0)
        current_track = format_track_item(current_track_raw["item"], progress_ms=progress_ms)

    history_arr = format_history_items(history.get("items", []))

    return render_template(
        "index.html", current_track=current_track, tracks=history_arr
    )


if __name__ == "__main__":
    app.run(debug=False, host="0.0.0.0", port=5000)
