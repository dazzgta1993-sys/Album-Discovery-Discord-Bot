# Album Discovery — Discord Music Bot 🎵

A dedicated, standalone Discord Music Bot powered by the **Album Discovery** engine:
- **Zero hardcoded data:** 100% live metadata from **Deezer**, **MusicBrainz**, and **Apple Music RSS**.
- **Web Control Hub:** Built-in real-time browser dashboard (`http://localhost:8905`) with live deck, moving seeker, queue manager, search, and charts.
- **High-Fidelity Audio:** Streamed directly through YouTube Opus with automatic reconnect guardrails and dynamic volume control.
- **Time Machine (1960–2026):** Explore and queue landmark historical releases across 67 consecutive years.
- **Official Countdown Charts:** Live UK Top 40, Billboard US, and Cloud DJ radio stations.
- **Smart Autoplay DJ:** Automatically plays vibe-matched tracks when the server queue ends.
- **Interactive Discord UI:** Rich embeds with 1400x1400 artwork, interactive playback control buttons, and tracklist dropdown menus.

---

## 🌐 Web Control Hub

The bot embeds a modern, real-time web dashboard running directly inside the bot process:
- **URL:** [`http://localhost:8905`](http://localhost:8905)
- **Live Deck:** High-res album art, live animated seeker bar with second-by-second progress, Play/Pause/Skip/Stop/Shuffle controls.
- **Live Queue Manager:** Reorder tracks up/down, remove tracks, clear queue, or jump immediately to any track with "Play Now".
- **Instant Search & Queue:** Search Deezer studio tracks or YouTube live versions and click to play or queue with 1 click.
- **Trending Charts:** Live official top trending singles with 1-click queue buttons.
- **Voice Channel Join/Leave:** Connect the bot to any server voice channel directly from your browser!

---

## 📋 Prerequisites
Before running the bot, ensure you have:
1. **Python 3.10+** — [python.org](https://www.python.org/downloads/) *(Make sure to check "Add Python to PATH")*
2. **FFmpeg** (Required for Discord audio streaming) — Install in 1 command:
   ```powershell
   winget install Gyan.FFmpeg
   ```

---

## 🚀 Quick Setup (3 Steps)

### Step 1: Create Your Discord Bot
1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Click **New Application**, give it a name (e.g., *Album Discovery*), and click **Create**.
3. Go to the **Bot** tab on the left:
   - Click **Reset Token** (or **Copy**) to get your `DISCORD_BOT_TOKEN`.
   - Scroll down to **Privileged Gateway Intents** and enable:
     - ✅ **Message Content Intent**
   - Click **Save Changes**.

### Step 2: Invite the Bot to Your Server
1. In the Developer Portal, go to **OAuth2** -> **OAuth2 URL Generator**.
2. Under **Scopes**, select:
   - ✅ `bot`
   - ✅ `applications.commands`
3. Under **Bot Permissions**, select:
   - ✅ `Send Messages`
   - ✅ `Embed Links`
   - ✅ `Attach Files`
   - ✅ `Connect`
   - ✅ `Speak`
   - ✅ `Use Application Commands`
4. Copy the generated URL at the bottom and open it in your browser to invite the bot to your server.

### Step 3: Configure Token & Start
1. Open `.env` in this directory and paste your token:
   ```env
   DISCORD_BOT_TOKEN=your_token_here
   ```
2. Double-click **`start_bot.bat`** to launch!
3. Open **`http://localhost:8905`** in your browser for the Web Control Hub.

---

## 🎧 Slash Commands

### 🎵 Playback & Controls
- `/play <query>` — Plays a song, artist, album, Deezer URL, or YouTube search.
- `/skip` — Skips the current track.
- `/pause` — Pauses current playback.
- `/resume` — Resumes audio playback.
- `/stop` — Stops playback, clears the queue, and disconnects the bot.
- `/queue` — Displays the upcoming tracks in the server queue.
- `/nowplaying` — Shows a rich embed with cover art, track details, and interactive control buttons.
- `/volume <1-100>` — Sets the playback volume.
- `/shuffle` — Shuffles the current queue.
- `/loop <off | track | queue>` — Sets the repeat mode.
- `/dj` — Toggles the Autoplay DJ vibe stream on or off.

### 💿 Music Discovery & Albums
- `/album <artist and album>` — Displays album details, 1400x1400 cover art, and an interactive dropdown list of tracks with a **"Queue Entire Album"** button!
- `/artist <name>` — Displays artist profile, fan count, and their top studio tracks.
- `/search <query>` — Searches the Deezer catalog and presents an interactive dropdown menu to choose a track.

### ⏳ Time Machine (1960–2026)
- `/timemachine <year>` — Select any year between 1960 and 2026 to browse and queue iconic landmark releases from that exact year.

### 🏆 Countdown Charts & Cloud Radio
- `/charts <uk | billboard | global>` — Streams live countdown charts directly into your voice channel.
- `/radio` — Interactive dropdown to tune into curated DJ and genre radio stations.

---

## ⚙️ Configuration (`config.json`)

You can customize bot behavior in `config.json`:
- `default_volume`: Default playback volume (e.g. `1.0` for 100%).
- `idle_disconnect_seconds`: Seconds of inactivity before the bot leaves the voice channel (`300` = 5 minutes).
- `autoplay_dj`: Whether Autoplay DJ is enabled by default (`true` or `false`).
- `embed_color`: Hex code for Discord embed cards (default: `"9d4edd"` studio neon purple).
- `web_enabled`: Whether the Web Control Hub is started (`true` or `false`).
- `web_port`: Port for the Web Control Hub (`8905`).
