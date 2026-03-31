import sys
from datetime import datetime, timedelta, timezone

import spotipy
from flask import Flask, render_template
from requests.exceptions import RequestException, Timeout
from spotipy import SpotifyException
from spotipy.oauth2 import SpotifyOAuth

app = Flask(__name__)
app.json.ensure_ascii = False

SPOTIFY_SCOPE = "user-read-currently-playing user-read-recently-played playlist-modify-public"
SPOTIFY_CACHE_PATH = ".spotifycache"
SPOTIFY_TIMEOUT_SECONDS = 10
SPOTIFY_API_RETRIES = 2

auth_manager = None


def create_auth_manager():
    return SpotifyOAuth(
        scope=SPOTIFY_SCOPE,
        open_browser=False,
        cache_path=SPOTIFY_CACHE_PATH,
        requests_timeout=SPOTIFY_TIMEOUT_SECONDS,
    )


def ensure_auth_manager(interactive=False, force_recreate=False):
    global auth_manager

    if auth_manager is None or force_recreate:
        auth_manager = create_auth_manager()

    token_info = auth_manager.validate_token(auth_manager.get_cached_token())
    if token_info:
        return auth_manager

    if not interactive:
        raise RuntimeError(
            "Spotify authentication is missing or expired. Run the initial authentication flow again."
        )

    auth_url = auth_manager.get_authorize_url()
    print("\n" + "=" * 70)
    print("[Authentication Mode] Please open the following URL in your browser:")
    print(f"\n{auth_url}\n")
    print("After authorizing, paste the FULL redirect URL below:")
    print("=" * 70 + "\n")

    try:
        response_url = input("Enter the URL: ")
        code = auth_manager.parse_response_code(response_url)
        auth_manager.get_access_token(code, as_dict=False)
        print("\n" + "*" * 60)
        print(" Authentication Success. '.spotifycache' has been created.")
        print(" Setup complete. The program will now exit.")
        print(" Next time, it will start automatically without this step.")
        print("*" * 60 + "\n")
        sys.exit(0)
    except Exception as error:
        print(f"\nError: {error}")
        sys.exit(1)


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
            current_track_raw = client.current_user_playing_track()
            history = client.current_user_recently_played(limit=50)
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
    ensure_auth_manager(interactive=True)


def get_history():
    try:
        current_track_raw, history = fetch_spotify_data()
    except RuntimeError as error:
        return f"Authentication Error: {error}", 401
    except Exception as error:
        status_code = 503 if should_retry_spotify_error(error) else 500
        return f"Spotify API Error: {error}", status_code

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

@app.route("/", methods=["GET"])
def hist():
    return get_history()

if __name__ == "__main__":
    init()
    app.run(debug=False, host="0.0.0.0", port=5000)
