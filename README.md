- **Moodify - Weather-Based Playlist**

- Purpose: Moodify builds a daily Spotify playlist that matches tomorrow’s weather.
It fetches the forecast, maps it to a “mood” (genres + energy/valence/tempo), pulls 12 tracks from Spotify, shuffles them, and replaces the playlist contents each run. It also writes a readable summary to a dated .txt file.

- What it does: 
    - Gets tomorrow’s forecast for Dublin (OpenWeather).
    - Maps weather → mood (e.g., rain → lo-fi/acoustic; hot & clear → dance/pop/EDM).
    - Fetches ~TRACK_COUNT recommendations from Spotify:
        - Uses Spotify Recommendations when available.
        - Falls back to Spotify Search by genre if needed.
        - Dedupes by primary artist and shuffles for freshness.
    - Replaces your target playlist with the new tracks (no duplicates if you rerun today).
    - Saves a daily summary .txt in logs/ (forecast, mood, and the track list).

- File outputs:
    - Manual or Scheduled run: `logs/playlist_moodify_YYYY-MM-DD.txt`
        - This is controlled by `SUMMARY_PREFIX` / `MOODIFY_MODE` (see below).

- Project layout (key files):
    - `weather_playlist.py` — main runner (weather → mood → tracks → playlist → summary).
    - `spotify_client.py` — minimal Spotify auth/client helper.
    - `schedule_moodify.py` — optional Python-based daily scheduler.
    - `logs/ — summaries` and (optionally) scheduler logs.

- Prereqs:
    - Python 3.9+
    - Packages:
    ```bash
    pip install requests python-dotenv APScheduler tzdata
    ```
    - (APScheduler/tzdata only needed if you use `schedule_moodify.py`.)

- Setup:
    - Create a .env in the project folder:
    - One-time Spotify auth to create `spotify_tokens.json`:
        ```bash
        python spotify_client.py --auth-url
        python spotify_client.py --exchange-code "CODE_HERE"
        ```

- Run it manually:
    ```bash
    python weather_playlist.py
    ```

    - What you’ll see:
        - Weather + mood line
        - Seed genres used
        - ~TRACK_COUNT recommended tracks printed
        - Playlist replaced with the new tracks
        - Summary saved to logs/playlist_moodify_YYYY-MM-DD.txt

- Schedule it daily (cross-platform, no OS scheduler):
    - Use the included Python scheduler:
    ```bash
    python schedule_moodify.py
    ```

    - Configure time and timezone via .env
    ```ini
    TZ=Europe/Dublin
    RUN_TIME=12:00
    ```

- How the mood logic works:
    - choose_mood() maps forecast + temp to:
        - seed genres (sanitized to Spotify’s known seed set)
        - target energy/valence/tempo ranges
        - Examples:
            - Rain → lo-fi, acoustic, indie-folk (lower energy/tempo)
            - Clouds → alternative, indie-rock, electronic (moderate)
            - Hot & clear → pop, dance, edm, tropical-house (high energy/tempo)

- How track selection works:
    - Try Recommendations API with seed genres + feature ranges.
    - If that errors, Search by genre (with a random offset).
    - Sort by popularity, dedupe by artist, shuffle, return top TRACK_COUNT.
    - This makes each run feel fresh even with the same weather.

- Environment flags:
    - TRACK_COUNT — number of songs per run (default 12).
    - DRY_RUN=true — prints everything but does not touch the playlist.
    - SPOTIFY_MARKET — country code for recommendations/search (e.g., IE).
    - SUMMARY_PREFIX — override output filename prefix (e.g., playlist_moodify_scheduler).
    - MOODIFY_MODE=scheduler — if set, filename defaults to playlist_moodify_scheduler_* (used by the scheduler).

- Troubleshooting:
    - 401 / 403: Token expired or wrong scopes → redo --auth-url / --exchange-code flow.
    - Wrong playlist: Ensure PLAYLIST_ID is the ID (from URL), not the name.
    - No tracks: Loosen energy/valence/tempo ranges or widen genres.
    - Terminal “stuck” after starting scheduler: open a new terminal tab, or kill the scheduler tab (trash-icon), or stop the Python process (Task Manager).

- Command lines used in the terminal during development:
    - pip install python-dotenv request

    - python spotify_client.py --auth-url

    - python spotify_client.py --exchange-code "AQA_vqzbyLbJKMBSKagyccYx0zCuyiwEoRHpfTX7oMWuWm5GpDFFmNsjxr19z1lk-mue0k7fNLjOq9Idq7pDX1qk2R7vC9jM73nA90yudw9wV9UDb_xo67N-25wKBtifjrGwCBBFAOpklwIHr2VmSIq-hxkAQfQGQKw4Lt5Wc5CEfaYvrMXcrv8SHVt87KHkKPlteTtzDmCNaEmtsHyaRxjPlfYqoN--vb_irkV_Ja6PNxOf9swLkmcQGi3ji7x12QnfC15VeTa61nSth6m8IQHQ6Wi2piYJhSCQCWS0Wg"

    - python spotify_client.py --add-track
    "5F2B7FXhOtQYGrAL6ldic2" "5hM5arv9KDbCHS0k9uqwjr"

    - python weather_playlist.py

    - python spotify_client.py

    - python weather_playlist.py

    - pip install APScheduler tzdata

    - python schedule_moodify.py

    - python weather_playlist.py