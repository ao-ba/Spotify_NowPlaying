import os
import sys
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from flask import Flask, render_template
from datetime import datetime, timezone, timedelta

app = Flask(__name__)
app.json.ensure_ascii = False

sp = None

def init():
    global sp
    scope = "user-read-currently-playing user-read-recently-played playlist-modify-public"
    
    auth_manager = SpotifyOAuth(
        scope=scope,
        open_browser=False,
        cache_path=".spotifycache"
    )

    token_info = auth_manager.validate_token(auth_manager.get_cached_token())

    if not token_info:
        auth_url = auth_manager.get_authorize_url()
        print("\n" + "="*70)
        print("[Authentication Mode] Please open the following URL in your browser:")
        print(f"\n{auth_url}\n")
        print("After authorizing, paste the FULL redirect URL below:")
        print("="*70 + "\n")

        try:
            response_url = input("Enter the URL: ")
            code = auth_manager.parse_response_code(response_url)
            auth_manager.get_access_token(code, as_dict=False)
            print("\n" + "*"*60)
            print(" Authentication Success. '.spotifycache' has been created.")
            print(" Setup complete. The program will now exit.")
            print(" Next time, it will start automatically without this step.")
            print("*"*60 + "\n")
            sys.exit(0)

        except Exception as e:
            print(f"\nError: {e}")
            sys.exit(1)

    sp = spotipy.Spotify(auth_manager=auth_manager, language="ja")

def get_history():
    try:
        current_track_raw = sp.current_user_playing_track()
    except Exception as e:
        return f"Authentication Error: {e}", 401

    current_track = None
    if current_track_raw and current_track_raw.get("is_playing"):
        item = current_track_raw["item"]
        current_track = {
            "name": item["name"],
            "artist": ", ".join([artist["name"] for artist in item["artists"]]),
            "album": item["album"]["name"],
            "url": item["external_urls"]["spotify"],
            "image_url": item["album"]["images"][0]["url"] if item["album"]["images"] else None,
        }

    history = sp.current_user_recently_played(limit=50)
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
            "image_url": track["album"]["images"][1]["url"] if track["album"]["images"] else None,
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
