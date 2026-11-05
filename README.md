# 🎧 Album Discovery — Autonomous Discord Music Bot & AI Radio Hub

A broadcast-grade, standalone Discord music bot and real-time studio control center powered by the **Album Discovery** engine:

- 🎛️ **Triple-Deck Pipeline Preloader:** Zero-gap transitions (<50ms) with Deck 2 Standby Prewarming and Deck 3 harmonic 2-step lookahead.
- 🧠 **Autonomous Vibe Discovery Matrix:** Self-driving intelligent autoplay with 4 exploration modes, anchor locking, artist cooldown shields, era filters, and 8D/Nightcore spam shields.
- 🧬 **Real-Time Music DNA & Acoustic Visualizer:** Live Energy, Danceability, Electronic/Acoustic ratios, and 100% dynamic public taxonomy resolution across 10 genres & 30+ subgenres.
- 🎙️ **Discord Voice Channel Status Synchronization:** Automatically updates Discord's native voice channel status to the currently playing song (`🎵 Artist - Title`) without text chat spam.
- 🌐 **Web Control Hub (`localhost:8905`):** Responsive desktop & split-screen browser studio with live animated soundwave visualizer, low-latency browser audio monitoring, queue reordering, and 1-click Clear History & Clear Logs actions.
- 📻 **Unified 9-Platform Streaming Ecosystem:** High-fidelity Opus 48kHz audio spanning Deezer Studio Masters, YouTube Music, YouTube Live/Concerts, Spotify catalog match, Apple Music / iTunes high-res covers, SoundCloud DJ sets, MusicBrainz taxonomy archives, and live Official UK/US Billboard charts.
- ⏳ **Time Machine (1960–2026):** Explore and queue landmark historical releases across 67 consecutive musical eras.
- 💿 **Complete Discography Classifier:** Browse studio albums, EPs, singles, mixtapes, collabs, and live releases with 1-click album queuing.

---

## 🎛️ Triple-Deck Preloader & Vibe Matrix

Say goodbye to awkward 2-3 second loading pauses and rapid-skip crashes:
- **Deck 1 (Active Playback):** Precision decoded 48kHz 16-bit PCM streaming.
- **Deck 2 (Standby Preloader):** Pre-resolves and buffers the next track's direct stream URL in the background for **<50ms instant zero-gap drop**.
- **Deck 3 (Pipeline Lookahead):** Cues and harmonic-checks two tracks ahead, ensuring continuous non-stop progression.
- **Vibe Modes:**
  - 🎯 **Artist Deep Dive:** Locks 100% onto the current artist's full catalog (albums, singles, B-sides).
  - 🤝 **Collabs & Circle:** Explores immediate collaborators, producers, and affiliated crews.
  - 🧠 **Smart Vibe:** Harmonic balance of related artists, genre branches, and similar sonic profiles.
  - 🚀 **Wild Discovery:** Expands outward to discover fresh, unexpected gems within the same energy tier.
- **Radio Guardrails:** 
  - **Anchor Lock:** Lock onto a favorite artist so exploration always loops back home.
  - **Artist Cooldown Shield:** Enforces authentic radio rules (e.g. 10 songs before an artist can repeat).
  - **Decade & Era Filters:** Restrict exploration to `2020s`, `2010s`, `2000s`, or `Classics`.
  - **Anti-Junk Shield:** Eliminates 8D Audio, Nightcore, sped-up/slowed channels, karaoke, type beats, and skits (<65s).

---

## 🌐 Web Control Hub (`http://localhost:8905`)

The bot embeds a real-time reactive control center running inside the bot process:
- **🎧 Listen Live in Browser:** Monitor the music stream and AI DJ live in your browser with low-latency Web Opus audio streaming and volume controls.
- **Interactive Seeker:** Second-by-second progress display with accurate pause-offset accounting.
- **Visual Deck Previews:** Live high-res album covers, Deck 2 standby badges, and Deck 3 pipeline indicators.
- **Live Queue Manager:** Drag, reorder, delete, or skip directly to any song with **Play Now**.
- **Multi-Source Catalog Search:** Search across all 9 engines with universal Enter-key trigger.
- **Trending Charts & Radio:** Stream official live UK Top 40, Billboard US charts, or 94 curated Cloud DJ stations.
- **Discography Browser:** Inspect any artist's catalog classified by Studio Albums, EPs, Singles, Mixtapes, and Remixes.
- **🗑️ History & Diagnostics Management:** 1-click **Clear History** and **Clear Logs** buttons with confirmation dialogs.
- **📱 Split-Screen & Responsive Design:** Optimized multi-column layout with zero header overlap on split-screen or tablet/mobile viewports.

---

## 📋 Prerequisites

Before running the bot, ensure you have:
1. **Python 3.10+** (Python 3.12 64-bit recommended) — [python.org/downloads](https://www.python.org/downloads/) *(Check "Add Python to PATH" during installation)*.
2. **FFmpeg** (Required for Discord audio decoding) — Install via PowerShell:
   ```powershell
   winget install Gyan.FFmpeg
   ```

---

## 🚀 Quick Setup (3 Steps)

### Step 1: Create Your Discord Bot
1. Go to the [Discord Developer Portal](https://discord.com/developers/applications).
2. Click **New Application**, name it (e.g., *Album Discovery*), and click **Create**.
3. Go to the **Bot** tab on the left:
   - Click **Reset Token** (or **Copy**) to get your `DISCORD_BOT_TOKEN`.
   - Under **Privileged Gateway Intents**, enable:
     - ✅ **Message Content Intent**
   - Click **Save Changes**.

### Step 2: Invite the Bot to Your Server
1. In the Developer Portal, go to **OAuth2** -> **OAuth2 URL Generator**.
2. Under **Scopes**, select:
   - ✅ `bot`
   - ✅ `applications.commands`
3. Under **Bot Permissions**, select:
   - ✅ `Send Messages`, `Embed Links`, `Attach Files`, `Connect`, `Speak`, `Use Application Commands`
4. Copy the generated URL at the bottom and open it in your browser to invite the bot.

### Step 3: Launch!
1. Double-click **`start_bot.bat`**.
   - If this is your first time, it will automatically install all requirements from `requirements.txt`.
   - It will open `.env` in Notepad: paste your `DISCORD_BOT_TOKEN=your_token_here` and save.
2. Open **`http://localhost:8905`** in your browser for the Web Control Hub!

---

## 💬 Slash Commands Reference (22 Commands)

### 🎵 Playback & Audio Controls
- `/play <query> [source]` — Stream track/album/URL with choice of all 9 engines.
- `/playnow <query> [source]` — Instantly plays track right now (bypasses queue).
- `/skip` — Instant zero-gap skip to the preloaded Deck 2 track.
- `/pause` & `/resume` — Pauses or resumes playback.
- `/stop` — Stops audio, clears queue, and disconnects.
- `/queue` — Displays paginated queue with runtime stats and upcoming tracks.
- `/nowplaying` — Rich embed with 1400x1400 artwork and interactive playback buttons.
- `/volume <1-100>` — Sets the playback volume dynamically.
- `/shuffle` — Shuffles the server music queue (or re-rolls AI autoplay recommendations).
- `/loop <off | track | queue>` — Changes repeat mode.
- `/quality <auto | 128k | 192k | 320k>` — Switches streaming bitrate dynamically.
- `/history` — Shows the last 10 tracks played in this server.

### 🧠 AI DJ & Vibe Intelligence
- `/dj [engine]` — Toggles Autoplay DJ or locks it to one of the 9 engines.
- `/brain` — Displays live telemetry embed of active engine, anchor, drift frequency, explicit shield, and last decision.

### 💿 Music Discovery & Discography
- `/search <query> [source]` — Searches catalog with an interactive selection dropdown.
- `/album <artist and album>` — Displays canonical album details, cover art, tracklist, and a **"Queue Entire Album"** button.
- `/artist <name>` — Displays artist profile, fan count, studio albums, and top hits.
- `/discography <artist>` — Categorized discography browser (Studio LPs, EPs, Live, Compilations).
- `/newreleases [limit]` — Fresh weekly editorial drops and studio releases.
- `/timemachine <year>` — Select any year (1960–2026) to browse and queue landmark historical releases.
- `/charts [country]` — Streams live UK Top 40 or US Billboard chart tracks.
- `/radio` — Interactive dropdown to tune into 94 curated cloud genre and vibe stations.

---

## ⚙️ Configuration (`config.json`)

You can customize default bot behavior in `config.json`:
- `default_volume`: Default playback volume (`1.0` = 100%).
- `idle_disconnect_seconds`: Seconds of inactivity before disconnecting (`300` = 5 minutes).
- `autoplay_dj`: Whether Autoplay DJ is enabled on startup (`true` or `false`).
- `embed_color`: Hex code for Discord embed cards (default: `"9d4edd"` studio neon purple).
- `web_enabled`: Whether Web Control Hub is started (`true` or `false`).
- `web_port`: Port for the Web Control Hub (`8905`).
