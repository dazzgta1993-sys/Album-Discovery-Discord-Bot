# 🎧 Album Discovery — Autonomous Discord Music Bot & AI Radio Hub

A broadcast-grade, standalone Discord music bot and real-time studio control center powered by the **Album Discovery** engine:

- 🎙️ **Live AI Radio DJ Host:** Neural broadcast voice segues with automatic studio audio ducking over song intros across Discord Voice & Web Browser!
- 🎛️ **Triple-Deck Pipeline Preloader:** Zero-gap transitions (<50ms) with Deck 2 Standby Prewarming and Deck 3 harmonic 2-step lookahead.
- 🧠 **Autonomous Vibe Discovery Matrix:** Self-driving intelligent autoplay with 4 exploration modes, anchor locking, artist cooldown shields, and era filters.
- 🌐 **Web Control Hub (`localhost:8905`):** Real-time browser studio with live animated seeker, live browser audio monitoring, queue reordering, and auto-streaming server logs.
- 📻 **Multi-Source Streaming & Charts:** High-fidelity Opus 48kHz audio from Deezer, YouTube Music, Apple Music, SoundCloud, Official UK Top 40, and Billboard US.
- ⏳ **Time Machine (1960–2026):** Explore and queue landmark historical releases across 67 consecutive musical eras.
- 💿 **Complete Discography Classifier:** Browse studio albums, EPs, singles, mixtapes, collabs, and live releases with 1-click album queuing.

---

## 🎙️ Live AI Radio DJ Host

Experience authentic radio broadcast talk-over transitions between tracks:
- **Zero-Latency Audio Ducking:** The bot smoothly ducks active music volume down to **15%** while the DJ speaks, restoring it to **100%** when the voiceover concludes.
- **Dual-Channel Broadcast:** DJ drops play seamlessly in **Discord Voice Channels AND the Web Browser Monitor** simultaneously.
- **4 Neural Studio Personalities:**
  - 🎙️ **Classic FM:** Warm, energetic broadcast host (US Neural Christopher).
  - 🔥 **Hype Club:** High-energy festival & club DJ host (US Neural Guy).
  - 🌙 **Late Night:** Smooth, laid-back midnight broadcast (US Neural Eric).
  - 📻 **BBC Radio 1:** Crisp, iconic British host (UK Neural Ryan).
- **Custom Cadence:** Set the DJ to speak `Every Song`, `Every 3 Songs`, `Every 5 Songs`, or trigger on demand with `🎙️ Drop DJ Voice Now`.
- **Failsafe Redundancy:** Automatic dual-engine fallback (`edge-tts` ➔ `gTTS`) resampled to 48,000Hz stereo studio audio with broadcast loudness normalization.

---

## 🎛️ Triple-Deck Preloader & Vibe Matrix

Say goodbye to awkward 2-3 second loading pauses between tracks:
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

---

## 🌐 Web Control Hub (`http://localhost:8905`)

The bot embeds a real-time reactive control center running inside the bot process:
- **🎧 Listen Live in Browser:** Monitor the music stream and AI DJ voiceover live in your browser with smart autoplay unlock and volume controls.
- **Interactive Seeker:** Second-by-second progress display with instant click-to-seek scrubbing.
- **Visual Deck Previews:** Live high-res album covers, Deck 2 standby badges, and Deck 3 pipeline indicators.
- **Live Queue Manager:** Drag, reorder, delete, or skip directly to any song with **Play Now**.
- **Multi-Source Catalog Search:** Search across Deezer, YouTube, YouTube Music, Apple Music, and SoundCloud.
- **Trending Charts & Radio:** Stream official live UK Top 40, Billboard US charts, or curated Cloud DJ stations.
- **Discography Browser:** Inspect any artist's catalog classified by Studio Albums, EPs, Singles, Mixtapes, and Remixes.
- **🟢 Live Auto-Streaming Logs:** Real-time bottom-locked streaming terminal showing AI brain decisions and playback events.

---

## 📋 Prerequisites

Before running the bot, ensure you have:
1. **Python 3.10+** — [python.org/downloads](https://www.python.org/downloads/) *(Make sure to check "Add Python to PATH" during installation)*.
2. **FFmpeg** (Required for Discord audio decoding) — Install in 1 command via Windows Terminal / PowerShell:
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

## 💬 Slash Commands Reference

### 🎵 Playback & Controls
- `/play <query>` — Plays a song, artist, album, Deezer link, or YouTube search.
- `/skip` — Instant zero-gap skip to the preloaded track.
- `/pause` & `/resume` — Pauses or resumes playback.
- `/stop` — Stops audio, clears queue, and leaves voice.
- `/queue` — Displays upcoming tracks in server queue.
- `/nowplaying` — Rich embed with 1400x1400 artwork and interactive playback buttons.
- `/volume <1-100>` — Sets the playback volume.
- `/shuffle` — Shuffles upcoming queue items.
- `/loop <off | track | queue>` — Changes repeat mode.
- `/dj` — Toggles the autonomous Autoplay DJ engine.

### 💿 Music Discovery & Albums
- `/album <artist and album>` — Displays album details, cover art, and an interactive dropdown with a **"Queue Entire Album"** button!
- `/artist <name>` — Displays artist profile, fan count, and top studio tracks.
- `/search <query>` — Searches the Deezer catalog with an interactive selection dropdown.

### ⏳ Time Machine (1960–2026)
- `/timemachine <year>` — Select any year between 1960 and 2026 to browse and queue iconic landmark releases from that year.

### 📻 Countdown Charts & Cloud Radio
- `/charts <uk | billboard | global>` — Streams live countdown charts directly into your voice channel.
- `/radio` — Interactive dropdown to tune into curated DJ and genre radio stations.

---

## ⚙️ Configuration (`config.json`)

You can customize default bot behavior in `config.json`:
- `default_volume`: Default playback volume (e.g. `1.0` for 100%).
- `idle_disconnect_seconds`: Seconds of inactivity before disconnecting (`300` = 5 minutes).
- `autoplay_dj`: Whether Autoplay DJ is enabled on startup (`true` or `false`).
- `embed_color`: Hex code for Discord embed cards (default: `"9d4edd"` studio neon purple).
- `web_enabled`: Whether Web Control Hub is started (`true` or `false`).
- `web_port`: Port for the Web Control Hub (`8905`).
