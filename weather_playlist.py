import os
import datetime as dt
from pathlib import Path
import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from urllib.parse import urlencode
from spotify_client import Spotify

# Config
OW_API_KEY = os.getenv("OW_API_KEY")  # set in .env
OW_CITY = os.getenv("OW_CITY") or "Dublin,IE"  # e.g., "Dublin,IE"
PLAYLIST_ID = os.getenv("PLAYLIST_ID")
SUMMARY_DIR = Path("logs")
SUMMARY_DIR.mkdir(exist_ok=True)

# Filename prefix:
# - If SUMMARY_PREFIX is set -> use it
# - Else if MOODIFY_MODE == "scheduler" -> playlist_moodify_scheduler
# - Else -> playlist_moodify
SUMMARY_PREFIX = os.getenv("SUMMARY_PREFIX")
if not SUMMARY_PREFIX:
    SUMMARY_PREFIX = "playlist_moodify_scheduler" if os.getenv("MOODIFY_MODE") == "scheduler" else "playlist_moodify"

DATE_STR = dt.datetime.now().strftime("%Y-%m-%d")  # year-month-day

# Helpers
def geocode_city(city: str, api_key: str):
    """OpenWeather geocoding API -> (lat, lon)."""
    url = "https://api.openweathermap.org/geo/1.0/direct"
    r = requests.get(url, params={"q": city, "limit": 1, "appid": api_key}, timeout=20)
    r.raise_for_status()
    data = r.json()
    if not data:
        raise SystemExit(f"City not found: {city}")
    return data[0]["lat"], data[0]["lon"]

def get_tomorrow_forecast(lat: float, lon: float, api_key: str):
    """
    Use the 5-day/3-hour forecast endpoint (free).
    Pick tomorrow ~12:00 entry; choose closest 3h slot.
    """
    url = "https://api.openweathermap.org/data/2.5/forecast"
    r = requests.get(url, params={
        "lat": lat,
        "lon": lon,
        "appid": api_key,
        "units": "metric",
    }, timeout=20)
    r.raise_for_status()
    data = r.json()
    if "list" not in data or not data["list"]:
        raise SystemExit("No forecast data returned.")

    from datetime import datetime, timedelta, timezone
    tz_offset = data.get("city", {}).get("timezone", 0)  # seconds
    tz = timezone(timedelta(seconds=tz_offset))
    now_local = datetime.now(tz)
    tomorrow_date = (now_local + timedelta(days=1)).date()
    target_time = datetime.combine(tomorrow_date, datetime.min.time()).replace(hour=12, tzinfo=tz)

    candidates = []
    for item in data["list"]:
        item_dt_local = datetime.fromtimestamp(item["dt"], tz)
        if item_dt_local.date() == tomorrow_date:
            candidates.append((abs((item_dt_local - target_time).total_seconds()), item, item_dt_local))

    if not candidates:
        raise SystemExit("Could not find forecast entries for tomorrow.")

    _, chosen, _ = sorted(candidates, key=lambda x: x[0])[0]
    condition = chosen.get("weather", [{}])[0].get("main", "Clear")
    temp_day = chosen.get("main", {}).get("temp", None)

    return {"condition": condition, "temp_c": temp_day, "raw": chosen}

def choose_mood(condition: str, temp_c: float | None):
    """Map weather condition + temperature to seed genres and targets."""
    cond = (condition or "").lower()

    if "thunder" in cond:
        return {"genres": ["dark-pop", "trip-hop", "alt-rock"], "energy": (0.5, 0.7), "valence": (0.2, 0.4), "tempo": (90, 115)}
    if "rain" in cond or "drizzle" in cond:
        return {"genres": ["lo-fi", "acoustic", "indie-folk"], "energy": (0.3, 0.5), "valence": (0.3, 0.5), "tempo": (70, 100)}
    if "snow" in cond:
        return {"genres": ["acoustic", "singer-songwriter", "folk"], "energy": (0.3, 0.5), "valence": (0.4, 0.6), "tempo": (70, 100)}
    if "mist" in cond or "fog" in cond or "haze" in cond:
        return {"genres": ["lo-fi", "chill", "downtempo"], "energy": (0.25, 0.5), "valence": (0.35, 0.55), "tempo": (70, 95)}
    if "cloud" in cond:
        return {"genres": ["alternative", "indie-rock", "electronic"], "energy": (0.5, 0.7), "valence": (0.45, 0.65), "tempo": (95, 115)}
    if temp_c is not None and temp_c >= 25:
        return {"genres": ["pop", "dance", "edm", "tropical-house"], "energy": (0.75, 0.95), "valence": (0.6, 0.9), "tempo": (110, 130)}
    if temp_c is not None and temp_c <= 5:
        return {"genres": ["ambient", "classical", "chill"], "energy": (0.2, 0.45), "valence": (0.3, 0.5), "tempo": (60, 90)}
    return {"genres": ["indie-pop", "rock", "pop"], "energy": (0.55, 0.75), "valence": (0.55, 0.8), "tempo": (100, 120)}

# Seed genre aliasing → approved Spotify seeds
GENRE_ALIASES = {
    "alt-pop": "alternative",
    "electropop": "electronic",
    "lo-fi": "chill",
    "chillhop": "chill",
    "neo-classical": "classical",
    "modern-rock": "rock",
    "indie-folk": "folk",
    "alt-rock": "alt-rock",
    "indie-pop": "indie-pop",
    "indie-rock": "indie-rock",
    "trip-hop": "trip-hop",
    "downtempo": "downtempo",
    "singer-songwriter": "singer-songwriter",
    # others already Spotify-valid in the mapping above: pop, dance, edm, tropical-house, ambient, classical, chill, alternative, electronic, rock, folk
}

# Safe subset of Spotify seed genres we’ll use (no API call needed)
ALLOWED_SEEDS = {
    "alternative","indie","indie-pop","indie-rock",
    "rock","pop","dance","edm","electronic","electropop",
    "tropical-house","chill","ambient","classical",
    "folk","singer-songwriter","downtempo","trip-hop"
}

def sanitize_seed_genres(mood_genres):
    out = []
    for g in mood_genres:
        cand = GENRE_ALIASES.get(g, g)
        if cand in ALLOWED_SEEDS:
            out.append(cand)
    if not out:
        # fallbacks if none matched
        for fb in ("indie-pop","indie-rock","alternative","electronic","rock","pop","chill","dance"):
            if fb in ALLOWED_SEEDS:
                out.append(fb)
            if len(out) >= 3:
                break
    return out[:5]

def get_spotify():
    """Create Spotify client from env and ensure access token is ready."""
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI")
    if not client_id or not client_secret or not redirect_uri:
        raise SystemExit("Missing Spotify config: set SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI in .env")
    sp = Spotify(client_id=client_id, client_secret=client_secret, redirect_uri=redirect_uri)
    sp.get_tokens()  # loads/refreshes token from spotify_tokens.json
    return sp

def find_tracks(sp: Spotify, mood: dict, limit: int = 10):
    """
    Try Spotify recommendations (preferred). If that 404s on your setup,
    fall back to Search API by genre and pick top tracks, deduped by artist.
    Returns (tracks, seeds).

    Now shuffles the final pool so each run yields a fresh set.
    """
    import random
    seeds = sanitize_seed_genres(mood["genres"])

    energy_min, energy_max = mood["energy"]
    val_min, val_max = mood["valence"]
    tempo_min, tempo_max = mood["tempo"]

    # Attempt 1: Recommendations API
    try:
        params = {
            "seed_genres": ",".join(seeds),
            "limit": min(max(limit * 2, 10), 100),
            "market": os.getenv("SPOTIFY_MARKET", "IE"),
            "min_energy": energy_min, "max_energy": energy_max,
            "min_valence": val_min, "max_valence": val_max,
            "min_tempo": tempo_min, "max_tempo": tempo_max,
        }
        qs = urlencode(params)
        r = requests.get(
            f"https://api.spotify.com/v1/recommendations?{qs}",
            headers={"Authorization": f"Bearer {sp.access_token}"},
            timeout=20
        )
        r.raise_for_status()
        rec_tracks = r.json().get("tracks", [])

        if rec_tracks:
            # Deduplicate by primary artist; prefer higher popularity
            seen_artists, pool = set(), []
            for t in sorted(rec_tracks, key=lambda x: x.get("popularity", 0), reverse=True):
                artist_key = tuple(a["id"] for a in t.get("artists", []))
                if artist_key in seen_artists:
                    continue
                seen_artists.add(artist_key)
                pool.append(t)

            if pool:
                random.shuffle(pool)            # <-- shuffle for freshness
                return pool[:limit], seeds
    except requests.HTTPError:
        # We'll fall back below
        pass

    #Attempt 2: Fallback via Search API by genr
    collected = []
    market = os.getenv("SPOTIFY_MARKET", "IE")
    for seed in seeds:
        # small randomness so repeated runs aren’t identical
        offset = random.randint(0, 50)
        q = f'genre:"{seed}"'
        sr = requests.get(
            "https://api.spotify.com/v1/search",
            headers={"Authorization": f"Bearer {sp.access_token}"},
            params={"q": q, "type": "track", "limit": 25, "offset": offset, "market": market},
            timeout=20,
        )
        if sr.status_code == 200:
            items = sr.json().get("tracks", {}).get("items", [])
            collected.extend(items)

        if len(collected) >= limit * 3:
            break

    if not collected:
        return [], seeds

    # Sort by popularity, dedupe by artist, then shuffle and slice
    collected.sort(key=lambda x: x.get("popularity", 0), reverse=True)
    seen_artists, pool = set(), []
    for t in collected:
        artist_key = tuple(a["id"] for a in t.get("artists", []))
        if artist_key in seen_artists:
            continue
        seen_artists.add(artist_key)
        pool.append(t)

    # suhffle for freshness
    random.shuffle(pool)
    return pool[:limit], seeds

def replace_playlist(sp: Spotify, playlist_id: str, tracks: list):
    """Replace the playlist items with today's tracks."""
    uris = [t["uri"] for t in tracks]
    r = requests.put(
        f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks",
        headers={
            "Authorization": f"Bearer {sp.access_token}",
            "Content-Type": "application/json",
        },
        json={"uris": uris},
        timeout=20,
    )
    if r.status_code >= 400:
        raise RuntimeError(f"Replace failed: {r.status_code} {r.text}")
    return r.json() if r.text else {}

def main():
    # Required config
    if not OW_API_KEY:
        raise SystemExit("Missing OW_API_KEY. Add it to your .env file.")
    if not PLAYLIST_ID:
        raise SystemExit("Missing PLAYLIST_ID. Put your target playlist ID in .env")

    #Optional knobs
    # TRACK_COUNT = int(os.getenv("TRACK_COUNT", "12"))
    # TRACK_COUNT = int(os.getenv("TRACK_COUNT") or 12)
    def env_int(name, default):
        v = os.getenv(name)
        try:
            return int(v) if v not in (None, "",) else default
        except ValueError:
            return default
    TRACK_COUNT = env_int("TRACK_COUNT", 12)
    DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"
 
    # Weather → mood
    lat, lon = geocode_city(OW_CITY, OW_API_KEY)
    forecast = get_tomorrow_forecast(lat, lon, OW_API_KEY)

    mood = choose_mood(forecast["condition"], forecast["temp_c"])
    genres_str = "|".join(mood["genres"])
    print(f"[{OW_CITY}] Tomorrow: {forecast['condition']} | {forecast['temp_c']}°C | mood genres: {genres_str}")

    sp = get_spotify()
    tracks, used_seeds = find_tracks(sp, mood, limit=TRACK_COUNT)

    print("Using seed genres:", ", ".join(used_seeds))

    if not tracks:
        print("No tracks found for the current mood/settings. Try widening ranges or different seeds.")
        return

    print("\nRecommended tracks:")
    for i, t in enumerate(tracks, 1):
        name = t["name"]
        artists = ", ".join(a["name"] for a in t["artists"])
        print(f"{i:02d}. {name} — {artists}")

    # Save summary to TXT file
    # summary_path = Path("logs") / f"playlist_summary_{DATE_STR}.txt"
    summary_path = SUMMARY_DIR / f"{SUMMARY_PREFIX}_{DATE_STR}.txt"


    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(f"Date: {DATE_STR}\n")
        f.write(f"City: {OW_CITY}\n")
        f.write(f"Condition: {forecast['condition']}\n")
        f.write(f"Temperature: {forecast['temp_c']}°C\n")
        f.write(f"Mood Genres: {', '.join(used_seeds)}\n")
        f.write(f"Tracks Added: {len(tracks)}\n\n")
        f.write("Track List:\n")
        for i, t in enumerate(tracks, 1):
            artists = ", ".join(a["name"] for a in t["artists"])
            f.write(f"{i:02d}. {t['name']} — {artists}\n")
    print(f"\nSummary saved to {summary_path}")

    # Replace playlist with today's tracks
    if DRY_RUN:
        print(f"\n[DRY RUN] Would replace playlist with {len(tracks)} tracks.")
    else:
        replace_playlist(sp, PLAYLIST_ID, tracks)
        print(f"\nPlaylist replaced with {len(tracks)} tracks.")

if __name__ == "__main__":
    main()
