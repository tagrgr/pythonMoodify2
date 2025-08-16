# Minimal Spotify client: auth, token refresh, add track to playlist
# Usage examples (first run requires manual code paste):
#   python spotify_client.py --auth-url
#   python spotify_client.py --exchange-code "<code-from-redirect>"
#   python spotify_client.py --add-track "<playlist_id>" "<track_id>"

import os
import json
import base64
import argparse
import requests
from urllib.parse import quote

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def _session_with_retries(total=5, backoff=1.5):
    retry = Retry(
        total=total,
        connect=total,
        read=total,
        status=total,
        backoff_factor=backoff,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset({"GET","POST","PUT","PATCH","DELETE","HEAD","OPTIONS"})
    )
    s = requests.Session()
    s.mount("https://", HTTPAdapter(max_retries=retry))
    s.mount("http://", HTTPAdapter(max_retries=retry))
    return s
class Spotify:
    def __init__(self, client_id, client_secret, redirect_uri, token_file="spotify_tokens.json"):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.token_file = token_file  # can be None for ephemeral/no-file use
        self.access_token = None
        self.refresh_token = None
        self.session = _session_with_retries()
        b64 = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("utf-8")
        self.basic_auth = f"Basic {b64}"

    # Auth
    def create_auth_url(self, scope: str) -> str:
        """
        Return the URL to visit for user consent.
        Scopes must be space-separated (not commas). Redirect URI must match exactly.
        """
        scope_str = " ".join(s.strip() for s in scope.replace(",", " ").split())
        return (
            "https://accounts.spotify.com/authorize?"
            f"client_id={self.client_id}&"
            f"redirect_uri={quote(self.redirect_uri, safe='')}&"
            "response_type=code&"
            f"scope={quote(scope_str, safe='')}"
        )

    def _save_tokens(self, tokens: dict):
        if not self.token_file:
            return  # skip writing in CI
        with open(self.token_file, "w", encoding="utf-8") as f:
            json.dump(tokens, f, ensure_ascii=False, indent=2)

    def _load_tokens(self):
        # Prefer env var first
        env_rt = os.getenv("SPOTIFY_REFRESH_TOKEN")
        if env_rt:
            self.refresh_token = env_rt
            return {"refresh_token": env_rt}
        # Then file
        if self.token_file and os.path.exists(self.token_file):
            with open(self.token_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.access_token = data.get("access_token")
                self.refresh_token = data.get("refresh_token")
                return data
        return None

    def get_tokens(self, code: str | None = None):
        """
        Ensure we have a fresh access token:
        - if env/file provides refresh_token -> refresh
        - else if authorization code provided -> exchange
        """
        if not self.access_token or not self.refresh_token:
            self._load_tokens()

        # Refresh path (preferred in CI)
        if self.refresh_token and not code:
            # r = requests.post(
            #     "https://accounts.spotify.com/api/token",
            #     headers={
            #         "Authorization": self.basic_auth,
            #         "Content-Type": "application/x-www-form-urlencoded",
            #     },
            #     data={"grant_type": "refresh_token", "refresh_token": self.refresh_token},
            #     timeout=20,
            # )
            # refresh path
            r = self.session.post(
                "https://accounts.spotify.com/api/token",
                headers={"Authorization": self.basic_auth, "Content-Type": "application/x-www-form-urlencoded"},
                data={"grant_type": "refresh_token", "refresh_token": self.refresh_token},
                timeout=20,
            )
            ...
            # code exchange path
            r = self.session.post(
                "https://accounts.spotify.com/api/token",
                headers={"Authorization": self.basic_auth, "Content-Type": "application/x-www-form-urlencoded"},
                data={"grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect_uri},
                timeout=20,
            )

            if r.status_code != 200:
                raise RuntimeError(f"Refresh failed: {r.status_code} {r.text}")
            data = r.json()
            self.access_token = data["access_token"]
            if "refresh_token" in data:
                self.refresh_token = data["refresh_token"]
            self._save_tokens({"access_token": self.access_token, "refresh_token": self.refresh_token})
            return

        # First-time code exchange (local only)
        if code and not self.access_token:
            r = requests.post(
                "https://accounts.spotify.com/api/token",
                headers={"Authorization": self.basic_auth, "Content-Type": "application/x-www-form-urlencoded"},
                data={"grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect_uri},
                timeout=20,
            )
            if r.status_code != 200:
                raise RuntimeError(f"Code exchange failed: {r.status_code} {r.text}")
            data = r.json()
            self.access_token = data["access_token"]
            self.refresh_token = data["refresh_token"]
            self._save_tokens({"access_token": self.access_token, "refresh_token": self.refresh_token})
            return

        if not self.access_token:
            raise RuntimeError("Tokens not found. Run auth flow locally or set SPOTIFY_REFRESH_TOKEN.")

    # Low-level API
    # def api_get(self, endpoint, base="https://api.spotify.com/v1"):
    #     self.get_tokens()
    #     r = requests.get(
    #         base + endpoint,
    #         headers={"Authorization": f"Bearer {self.access_token}"},
    #         timeout=20,
    #     )
    #     if r.status_code >= 400:
    #         raise RuntimeError(f"GET {endpoint} failed: {r.status_code} {r.text}")
    #     return r

    # def api_post(self, endpoint, data, base="https://api.spotify.com/v1"):
    #     self.get_tokens()
    #     r = requests.post(
    #         base + endpoint,
    #         headers={
    #             "Authorization": f"Bearer {self.access_token}",
    #             "Content-Type": "application/json",
    #         },
    #         json=data,
    #         timeout=20,
    #     )
    #     if r.status_code >= 400:
    #         raise RuntimeError(f"POST {endpoint} failed: {r.status_code} {r.text}")
    #     return r
    def api_get(self, endpoint, base="https://api.spotify.com/v1"):
        self.get_tokens()
        r = self.session.get(base + endpoint, headers={"Authorization": f"Bearer {self.access_token}"}, timeout=20)
        if r.status_code >= 400:
            raise RuntimeError(f"GET {endpoint} failed: {r.status_code} {r.text}")
        return r

    def api_post(self, endpoint, data, base="https://api.spotify.com/v1"):
        self.get_tokens()
        r = self.session.post(
            base + endpoint,
            headers={"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"},
            json=data,
            timeout=20,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"POST {endpoint} failed: {r.status_code} {r.text}")
        return r


    # Helpers
    @staticmethod
    def uri(id, type="track"):
        return f"spotify:{type}:{id}"

    def add_song_to_playlist(self, playlist_id, song_id):
        data = {"uris": [self.uri(song_id)]}
        return self.api_post(f"/playlists/{playlist_id}/tracks", data).json()

    def get_current_user_id(self):
        """Return the Spotify user ID for the current authenticated user."""
        self.get_tokens()
        r = self.api_get("/me")
        return r.json()["id"]
    
    def create_playlist(self, name, public=True, description=""):
        """Create a new playlist for the current user and return its JSON."""
        user_id = self.get_current_user_id()
        payload = {"name": name, "public": public, "description": description}
        r = self.api_post(f"/users/{user_id}/playlists", payload)
        return r.json()
    
def parse_args():
    p = argparse.ArgumentParser(description="Minimal Spotify client")
    p.add_argument("--auth-url", action="store_true", help="Print the Spotify authorization URL")
    p.add_argument("--exchange-code", metavar="CODE", help="Exchange authorization code for tokens")
    p.add_argument("--add-track", nargs=2, metavar=("PLAYLIST_ID", "TRACK_ID"), help="Add a track to a playlist")
    p.add_argument("--create-playlist", nargs=1, metavar="NAME", help="Create a new playlist with given name")

    return p.parse_args()

def main():
    import os, json  # ensure json is available here
    # Read config from env or .env
    client_id = os.getenv("SPOTIFY_CLIENT_ID") or ""
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET") or ""
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI")  # require explicit setting

    scope = os.getenv(
        "SPOTIFY_SCOPE",
        "playlist-modify-public playlist-read-collaborative playlist-modify-private",
    )

    if not client_id or not client_secret or not redirect_uri:
        raise SystemExit(
            "Missing config. Set SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, and SPOTIFY_REDIRECT_URI in your environment or .env"
        )

    sp = Spotify(client_id=client_id, client_secret=client_secret, redirect_uri=redirect_uri)
    args = parse_args()

    if args.auth_url:
        print(sp.create_auth_url(scope))
        return

    if args.exchange_code:
        sp.get_tokens(code=args.exchange_code)
        print("Tokens saved.")
        return

    if args.add_track:
        playlist_id, track_id = args.add_track
        res = sp.add_song_to_playlist(playlist_id, track_id)
        print(json.dumps(res, indent=2))
        return

    #create playlist once
    if args.create_playlist:
        playlist_name = args.create_playlist[0]
        res = sp.create_playlist(
            playlist_name,
            public=True,
            description="Weather-based daily mood playlist"
        )
        print("Playlist created!")
        print(f"Name: {res['name']}")
        print(f"ID: {res['id']}")
        return

    #  just ensure tokens are valid (refresh if needed)
    sp.get_tokens()
    print("Access token ready.")

if __name__ == "__main__":
    main()