let currentGuildId = ""; window.currentGuildId = "";
let serverStatus = null;
let localElapsed = 0;
let localTotal = 0;
let isPlaying = false;
let isPaused = false;
let lastPollTimestamp = performance.now();
let isSeeking = false;
let currentAutoplay = true;
let currentQuality = "auto";
let preMuteVolume = 100;
let isMonitoring = localStorage.getItem("albumDiscoveryAudioMonitor") !== "false";
let lastMonitoredTrack = "";
window._lastDeck2Track = null;
window._isSkipping = false;
window._skippedTrackTitle = "";
let currentBrainConfig = {
  vibe_mode: "balanced",
  vibe_drift_freq: 1,
  hit_depth: "balanced",
  deck2_enabled: true,
  deck3_enabled: true,
  explicit_filter: "allow",
  artist_cooldown: 10,
  era_filter: "all",
  vibe_energy: "auto",
  vibe_engine_source: "auto"
};
const ALBUM_PLACEHOLDER_SVG = "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='48' height='48' viewBox='0 0 48 48'%3E%3Crect width='48' height='48' rx='6' fill='%231b1c26'/%3E%3Ccircle cx='24' cy='24' r='14' fill='%23282a3a'/%3E%3Ccircle cx='24' cy='24' r='4' fill='%239d4edd'/%3E%3C/svg%3E";
function showToast(msg, icon = "✨") {
  const t = document.getElementById("toastBox");
  document.getElementById("toastMsg").innerText = msg;
  document.getElementById("toastIcon").innerText = icon;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 2800);
}

function switchTab(tabId, btn) {
  document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
  document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
  if (btn) {
    btn.classList.add("active");
  } else {
    const b = document.querySelector(`.tab-btn[onclick*="'${tabId}'"]`);
    if (b) b.classList.add("active");
  }
  const target = document.getElementById("tab" + tabId.charAt(0).toUpperCase() + tabId.slice(1));
  if (target) target.classList.add("active");
  if (tabId === "charts") loadCharts();
  if (tabId === "logs") loadLogs(true);
  if (tabId === "radio" && typeof loadCloudRadio === "function") loadCloudRadio();
  if (tabId === "timemachine" && typeof loadTimeMachine === "function") {
    const select = document.getElementById("tmYearSelect");
    loadTimeMachine(select ? select.value : 1999);
  }
  if (tabId === "discography") {
    const input = document.getElementById("discoArtistInput");
    if (input && !input.value.trim()) {
      const header = document.getElementById("discoArtistHeader");
      const container = document.getElementById("discoAlbumList");
      if (header) header.innerHTML = "";
      if (container) {
        container.innerHTML = `<div class="empty-state"><div class="empty-icon">💿</div><div>Explore complete artist discographies classified with MusicBrainz & Apple Music.</div></div>`;
      }
    }
  }
}
function formatTime(secs) { if (!secs || isNaN(secs) || secs <= 0) return "0:00"; const m = Math.floor(secs / 60), s = Math.floor(secs % 60); return m + ":" + (s < 10 ? "0" : "") + s; }

async function init() {
  await pollStatus();
  setInterval(pollStatus, 1000);
  setInterval(() => {
    const tabLogs = document.getElementById("tabLogs");
    if (tabLogs && tabLogs.classList.contains("active")) {
      loadLogs(false);
    }
  }, 1500);
  startSmoothSeekerLoop();
}
function startSmoothSeekerLoop() {
  function tick() {
    if (isPlaying && !isPaused && localTotal > 0 && !isSeeking) {
      const elapsedDelta = (performance.now() - lastPollTimestamp) / 1000;
      const smoothElapsed = Math.min(localTotal, localElapsed + elapsedDelta);
      document.getElementById("timeElapsed").innerText = formatTime(smoothElapsed);
      document.getElementById("timeTotal").innerText = formatTime(localTotal);
      const pct = (smoothElapsed / localTotal) * 100;
      document.getElementById("progressFill").style.width = pct + "%";
    }
    requestAnimationFrame(tick);
  }
  requestAnimationFrame(tick);
}

function renderSeeker() {
  document.getElementById("timeElapsed").innerText = formatTime(localElapsed);
  document.getElementById("timeTotal").innerText = formatTime(localTotal);
  const pct = localTotal > 0 ? (localElapsed / localTotal) * 100 : 0;
  document.getElementById("progressFill").style.width = pct + "%";
}
function onSeekerClick(e) {
  if (!currentGuildId || !isPlaying || localTotal <= 0) return;
  const bar = document.getElementById("progressBar");
  if (!bar) return;
  const rect = bar.getBoundingClientRect();
  const clickX = e.clientX - rect.left;
  const frac = Math.max(0, Math.min(1, clickX / rect.width));
  const targetSec = Math.round(frac * localTotal);
  localElapsed = targetSec;
  lastPollTimestamp = performance.now();
  renderSeeker();
  sendControl("seek", targetSec);
  showToast("Seeked to " + formatTime(targetSec), "⏩");
}

async function pollStatus() {
  try {
    const res = await fetch("/api/status");
    if (!res.ok) return;
    const data = await res.json();
    serverStatus = data;
    document.getElementById("botUserLabel").innerText = data.bot_user || "Online";
    document.getElementById("pingBadge").innerText = "⚡ " + data.bot_ping_ms + "ms";
    const up = data.uptime_seconds || 0;
    const h = Math.floor(up / 3600);
    const m = Math.floor((up % 3600) / 60);
    document.getElementById("uptimeBadge").innerText = "⏱ " + (h > 0 ? h + "h " : "") + m + "m";
    const select = document.getElementById("serverSelect");
    if (data.guilds && data.guilds.length > 0) {
      if (document.activeElement !== select) {
        const currentKeys = Array.from(select.options).map(o => o.value + ":" + o.innerText).join("|");
        const newKeys = data.guilds.map(g => g.id + ":" + ((g.is_connected ? "🟢 " : "⚪ ") + g.name + " (" + g.member_count + " members)")).join("|");
        if (currentKeys !== newKeys) {
          select.innerHTML = "";
          data.guilds.forEach(g => {
            const opt = document.createElement("option");
            opt.value = g.id;
            opt.innerText = (g.is_connected ? "🟢 " : "⚪ ") + g.name + " (" + g.member_count + " members)";
            select.appendChild(opt);
          });
          if (!currentGuildId || !data.guilds.find(g => g.id === currentGuildId)) {
            currentGuildId = data.guilds[0].id;
          }
          window.currentGuildId = currentGuildId;
          select.value = currentGuildId;
        }
      }
    } else {
      select.innerHTML = '<option value="">No Servers Detected</option>';
    }
    if (currentGuildId) {
      await pollGuildState(currentGuildId);
    }
  } catch (e) {
    console.warn("Poll status notice:", e);
  }
}

function onServerChange() {
  const select = document.getElementById("serverSelect");
  currentGuildId = select ? select.value : "";
  window.currentGuildId = currentGuildId;
  pollGuildState(currentGuildId);
}
async function pollGuildState(guildId) {
  if (!guildId) return;
  try {
    const res = await fetch("/api/guild/" + guildId);
    if (!res.ok) return;
    const data = await res.json();
    const vcText = document.getElementById("voiceStatusText");
    const vcWrap = document.getElementById("voiceActionWrap");
    if (data.voice.is_connected) {
      const count = data.voice.members ? data.voice.members.length : 0;
      vcText.innerHTML = "<strong>" + (data.voice.current_channel_name || "Voice") + "</strong> (" + count + " listening)";
      vcWrap.innerHTML = '<button class="btn-small btn-danger" onclick="sendControl(\'leave_voice\')">Disconnect</button>';
    } else {
      vcText.innerHTML = "Not Connected to Voice";
      let optHtml = "";
      if (data.voice.available_channels && data.voice.available_channels.length > 0) {
        optHtml = '<select id="quickVcSelect" class="server-select" style="padding:4px 8px; font-size:0.75rem;">' +
          data.voice.available_channels.map(c => '<option value="' + c.id + '">' + escapeHtml(c.name) + '</option>').join('') +
          '</select> <button class="btn-small" onclick="joinSelectedVoice()">Join</button>';
      } else {
        optHtml = '<span style="font-size:0.75rem; color:var(--text-muted)">No voice channels</span>';
      }
      vcWrap.innerHTML = optHtml;
    }

    const p = data.player;
    window._lastDeck2Track = p.preloaded_track;
    if (window._isSkipping) {
      if (p.current_track && p.current_track.title === window._skippedTrackTitle) return;
      window._isSkipping = false;
    }
    isPlaying = p.is_playing;
    isPaused = p.is_paused;
    currentAutoplay = p.autoplay;
    currentQuality = p.audio_quality || "auto";
    const btnPlay = document.getElementById("btnPlayPause");
    btnPlay.innerText = (isPlaying && !isPaused) ? "⏸" : "▶";
    const coverImg = document.getElementById("trackCover");
    const placeholder = document.getElementById("coverPlaceholder");
    if (p.current_track) {
      document.getElementById("trackTitle").innerText = p.current_track.title || "Unknown";
      document.getElementById("trackArtist").innerText = p.current_track.artist || "Unknown";
      document.getElementById("sourceBadge").innerText = p.current_track.source ? p.current_track.source.toUpperCase() : "DEEZER";
      document.getElementById("requestedByBadge").innerText = p.current_track.requested_by ? p.current_track.requested_by : "Web Hub";
      if (p.current_track.cover) {
        coverImg.src = p.current_track.cover;
        coverImg.style.display = "block";
        placeholder.style.display = "none";
      } else {
        coverImg.style.display = "none";
        placeholder.style.display = "block";
      }
    } else {
      document.getElementById("trackTitle").innerText = "Nothing Playing";
      document.getElementById("trackArtist").innerText = "Queue is idle";
      document.getElementById("sourceBadge").innerText = "IDLE";
      document.getElementById("requestedByBadge").innerText = "Ready";
      coverImg.style.display = "none";
      placeholder.style.display = "block";
    }
    if (typeof updateAnchorBadge === "function") updateAnchorBadge(p);
    localElapsed = p.progress.elapsed || 0;
    localTotal = p.progress.total || 0;
    lastPollTimestamp = performance.now();
    renderSeeker();
    const btnAuto = document.getElementById("btnAutoplay");
    btnAuto.innerHTML = `✨ Autoplay: <span style="color:${p.autoplay ? '#4ade80' : 'var(--text-muted)'}; font-weight:700;">${p.autoplay ? 'ON' : 'OFF'}</span>`;
    if (p.autoplay) btnAuto.classList.add("active"); else btnAuto.classList.remove("active");
    const btnQ = document.getElementById("btnQuality");
    btnQ.innerText = "🎧 " + (p.audio_quality ? p.audio_quality.toUpperCase() : "AUTO");
    const btnLoopText = document.getElementById("btnLoopText");
    btnLoopText.innerText = "Loop: " + (p.loop_mode ? p.loop_mode.charAt(0).toUpperCase() + p.loop_mode.slice(1) : "Off");
    const btnLoopIcon = document.getElementById("btnLoop");
    if (p.loop_mode === "track") btnLoopIcon.innerText = "🔂";
    else if (p.loop_mode === "queue") btnLoopIcon.innerText = "🔁";
    else btnLoopIcon.innerText = "➡️";
    const volSlider = document.getElementById("volSlider");
    if (!isDraggingVol && document.activeElement !== volSlider) {
      volSlider.value = p.volume;
      document.getElementById("volPct").innerText = p.volume + "%";
      const monAudio = document.getElementById("browserMonitorAudio");
      if (monAudio && isMonitoring) monAudio.volume = Math.max(0, Math.min(1, p.volume / 100));
    }

    const banner = document.getElementById("preloadedBanner");
    const pTitle = document.getElementById("preloadedTitle");
    const pLabel = document.getElementById("preloadedLabel");
    const d3Row = document.getElementById("deck3BannerRow");
    const d3Title = document.getElementById("deck3Title");
    if (banner && pTitle && pLabel) {
      if (p.preloaded_track && p.is_playing) {
        banner.style.display = "flex";
        pTitle.innerText = `${p.preloaded_track.artist} - ${p.preloaded_track.title}`;
        pLabel.innerText = p.preloaded_track.is_autoplay ? "Deck 2 Autoplay Ready" : "Deck 2 Queue Ready";
        if (d3Row && d3Title && p.deck3_track) {
          d3Row.style.display = "flex";
          d3Title.innerText = `${p.deck3_track.artist} - ${p.deck3_track.title}`;
        } else if (d3Row) {
          d3Row.style.display = "none";
        }
      } else {
        banner.style.display = "none";
      }
    }
    renderQueue(p.queue, p.queue_count, p.preloaded_track, p.deck3_track);
    renderHistory(p.history);
    // Sync Brain Control Hub
    if (p.brain) {
      const b = p.brain;
      const tAnchor = document.getElementById("telemetryAnchor");
      const tChain = document.getElementById("telemetryChain");
      const tDeck2 = document.getElementById("telemetryDeck2");
      const tDeck3 = document.getElementById("telemetryDeck3");
      const tDecision = document.getElementById("telemetryDecision");
      if (tAnchor) tAnchor.innerText = b.vibe_anchor_artist || "Auto";
      if (tChain) tChain.innerText = (b.consecutive_autoplay_count || 0) + " songs";
      if (tDeck2) tDeck2.innerText = b.deck2_status || "Standby";
      if (tDeck3) tDeck3.innerText = b.deck3_status || "Standby";
      if (tDecision) tDecision.innerText = b.last_brain_decision || "Standby";
      if (b.vibe_mode) {
        currentBrainConfig.vibe_mode = b.vibe_mode;
        document.querySelectorAll(".brain-mode-card").forEach(c => c.classList.remove("active"));
        const activeCard = document.getElementById("mode-" + b.vibe_mode);
        if (activeCard) activeCard.classList.add("active");
      }
      if (b.vibe_drift_freq && document.activeElement !== document.getElementById("driftFreqSlider")) {
        currentBrainConfig.vibe_drift_freq = b.vibe_drift_freq;
        const s = document.getElementById("driftFreqSlider");
        if (s) s.value = b.vibe_drift_freq;
        const badge = document.getElementById("driftFreqVal");
        if (badge) badge.innerText = "Every " + b.vibe_drift_freq + " song" + (b.vibe_drift_freq > 1 ? "s" : "");
      }
      if (b.hit_depth) { currentBrainConfig.hit_depth = b.hit_depth; setPillActive("depth", b.hit_depth); }
      if (b.deck2_enabled !== undefined) {
        currentBrainConfig.deck2_enabled = b.deck2_enabled;
        const d2Btn = document.getElementById("btnDeck2Toggle");
        if (d2Btn) {
          d2Btn.innerHTML = b.deck2_enabled ? "⚡ Deck 2: ON" : "Deck 2: OFF";
          d2Btn.style.color = b.deck2_enabled ? "#4ade80" : "var(--text-muted)";
        }
      }
      if (b.deck3_enabled !== undefined) {
        currentBrainConfig.deck3_enabled = b.deck3_enabled;
        const d3Btn = document.getElementById("btnDeck3Toggle");
        if (d3Btn) {
          d3Btn.innerHTML = b.deck3_enabled ? "🎛️ Deck 3: ON" : "Deck 3: OFF";
          d3Btn.style.color = b.deck3_enabled ? "#38bdf8" : "var(--text-muted)";
        }
      }
      if (b.explicit_filter) { currentBrainConfig.explicit_filter = b.explicit_filter; setPillActive("exp", b.explicit_filter); }
      if (b.artist_cooldown !== undefined) { currentBrainConfig.artist_cooldown = b.artist_cooldown; setPillActive("cooldown", b.artist_cooldown); }
      if (b.era_filter) { currentBrainConfig.era_filter = b.era_filter; setPillActive("era", b.era_filter); }
      if (b.vibe_energy) { currentBrainConfig.vibe_energy = b.vibe_energy; setPillActive("energy", b.vibe_energy); }
      if (b.vibe_engine_source) { currentBrainConfig.vibe_engine_source = b.vibe_engine_source; setPillActive("engine", b.vibe_engine_source); }
    }
    if (isMonitoring) {
      const currentTitle = p.current_track ? p.current_track.title : "";
      const audio = document.getElementById("browserMonitorAudio");
      const btn = document.getElementById("btnAudioMonitor");
      if (!p.is_playing || !p.current_track) {
        if (audio && !audio.paused) audio.pause();
        if (btn) {
          btn.innerText = "🎧 Listen Live in Browser: ON (Standby)";
          btn.classList.add("active");
        }
      } else if (currentTitle && (currentTitle !== lastMonitoredTrack || !audio.src || audio.paused)) {
        if (currentTitle !== lastMonitoredTrack || !audio.src) {
          lastMonitoredTrack = currentTitle;
          audio.src = "/api/guild/" + currentGuildId + "/stream?t=" + Date.now();
        }
        const pPlay = audio.play();
        if (pPlay !== undefined) {
          pPlay.then(() => {
            if (btn) {
              btn.innerText = "🎧 Listen Live in Browser: ON";
              btn.classList.add("active");
            }
          }).catch(e => {
            if (btn) {
              btn.innerText = "🎧 Click Anywhere to Unmute";
              btn.classList.add("active");
            }
            armAutoplayUnlocker();
          });
        }
      }
    }

  } catch (e) {
    console.warn("Poll guild notice:", e);
  }
}
function selectVibeMode(mode) {
  currentBrainConfig.vibe_mode = mode;
  document.querySelectorAll(".brain-mode-card").forEach(c => c.classList.remove("active"));
  const card = document.getElementById("mode-" + mode);
  if (card) card.classList.add("active");
  sendBrainConfig({ vibe_mode: mode });
  showToast("Vibe Mode: " + mode.replace("_", " ").toUpperCase(), "🧠");
}

let driftDebounceTimer = null;
function onDriftSliderChange(val) {
  const num = parseInt(val);
  currentBrainConfig.vibe_drift_freq = num;
  const badge = document.getElementById("driftFreqVal");
  if (badge) badge.innerText = "Every " + num + " song" + (num > 1 ? "s" : "");
  if (driftDebounceTimer) clearTimeout(driftDebounceTimer);
  driftDebounceTimer = setTimeout(() => {
    sendBrainConfig({ vibe_drift_freq: num });
  }, 350);
}
function setPillActive(prefix, val) {
  document.querySelectorAll("#tabBrain .filter-pills-row .pill-btn").forEach(b => {
    if (b.id && b.id.startsWith(prefix + "-")) b.classList.remove("active");
  });
  const btn = document.getElementById(prefix + "-" + val);
  if (btn) btn.classList.add("active");
}

function selectHitDepth(depth) {
  currentBrainConfig.hit_depth = depth;
  setPillActive("depth", depth);
  sendBrainConfig({ hit_depth: depth });
  showToast("Catalog Depth: " + depth.replace("_", " ").toUpperCase(), "📊");
}
function selectExplicit(pref) {
  currentBrainConfig.explicit_filter = pref;
  setPillActive("exp", pref);
  sendBrainConfig({ explicit_filter: pref });
  showToast("Explicit Shield: " + (pref === "allow" ? "ALLOWED" : "CLEAN ONLY"), "🛡️");
}

function selectArtistCooldown(n) {
  const num = parseInt(n);
  currentBrainConfig.artist_cooldown = num;
  setPillActive("cooldown", num);
  sendBrainConfig({ artist_cooldown: num });
  showToast("No-Repeat Cooldown: " + num + " SONGS", "📻");
}
function selectEraFilter(era) {
  currentBrainConfig.era_filter = era;
  setPillActive("era", era);
  sendBrainConfig({ era_filter: era });
  showToast("Decade Filter: " + era.toUpperCase(), "⏳");
}

function selectVibeEnergy(energy) {
  currentBrainConfig.vibe_energy = energy;
  setPillActive("energy", energy);
  sendBrainConfig({ vibe_energy: energy });
  showToast("Energy Flow: " + energy.toUpperCase(), "🌊");
}
function selectEngineSource(source) {
  currentBrainConfig.vibe_engine_source = source;
  setPillActive("engine", source);
  sendBrainConfig({ vibe_engine_source: source });
  showToast("Engine: " + source.toUpperCase(), "🎛️");
}
function toggleDeck2Pref() {
  currentBrainConfig.deck2_enabled = !currentBrainConfig.deck2_enabled;
  const btn = document.getElementById("btnDeck2Toggle");
  if (btn) {
    btn.innerHTML = currentBrainConfig.deck2_enabled ? "⚡ Deck 2: ON" : "Deck 2: OFF";
    btn.style.color = currentBrainConfig.deck2_enabled ? "#4ade80" : "var(--text-muted)";
  }
  sendBrainConfig({ deck2_enabled: currentBrainConfig.deck2_enabled });
  showToast("Deck 2 Preload: " + (currentBrainConfig.deck2_enabled ? "ENABLED ⚡" : "DISABLED"), "⚡");
}
function toggleDeck3Pref() {
  currentBrainConfig.deck3_enabled = !currentBrainConfig.deck3_enabled;
  const btn = document.getElementById("btnDeck3Toggle");
  if (btn) {
    btn.innerHTML = currentBrainConfig.deck3_enabled ? "🎛️ Deck 3: ON" : "Deck 3: OFF";
    btn.style.color = currentBrainConfig.deck3_enabled ? "#38bdf8" : "var(--text-muted)";
  }
  sendBrainConfig({ deck3_enabled: currentBrainConfig.deck3_enabled });
  showToast("Deck 3 Pipeline: " + (currentBrainConfig.deck3_enabled ? "ENABLED 🎛️" : "DISABLED"), "🎛️");
}

async function sendBrainConfig(partial) {
  if (!currentGuildId) return;
  try {
    await fetch("/api/guild/" + currentGuildId + "/control", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "set_brain_config", ...partial })
    });
  } catch (e) {
    console.warn("Brain config notice:", e);
  }
}
function saveBrainConfig() {
  sendBrainConfig(currentBrainConfig);
  showToast("Brain settings saved & active!", "💾");
}

function renderQueue(queue, count) {
  document.getElementById("queueBadgeCount").innerText = count || 0;
  document.getElementById("queueSummaryText").innerText = (count || 0) + " track" + (count === 1 ? "" : "s") + " up next";
  const list = document.getElementById("queueList");
  if (!queue || queue.length === 0) {
    list.innerHTML = ` <div class="empty-state"> <div class="empty-icon">📭</div> <div>The queue is currently empty.</div>
<div style="font-size:0.8rem; color:var(--text-muted)">Use Search or Trending Charts to add tracks!</div> </div> `;
    return;
  }
  list.innerHTML = queue.map((t, idx) => ` <div class="track-item">
<span style="font-weight:700; color:var(--text-muted); font-size:0.8rem; width:20px;">#${idx + 1}</span>
<img class="track-thumb" src="${t.cover || ALBUM_PLACEHOLDER_SVG}" onerror="this.onerror=null; this.src='${ALBUM_PLACEHOLDER_SVG}';" />
<div class="track-info-col"> <span class="item-title">${escapeHtml(t.title)}</span>
<span class="item-artist">${escapeHtml(t.artist)} • ${t.duration || '--:--'}</span> </div> <div class="track-action-btns">
${idx > 0 ? `<button class="btn-small" title="Move Up" onclick="moveQueueItem(${idx}, ${idx - 1})">▲</button>` : ''} ${idx < queue.length - 1 ? `<button class="btn-small" title="Move Down" onclick="moveQueueItem(${idx}, ${idx + 1})">▼</button>` : ''} <button class="btn-small" title="Play Now" onclick="queuePlayNow(${idx})">▶</button>
<button class="btn-small btn-danger" title="Remove" onclick="removeQueueItem(${idx})">✕</button> </div> </div> `).join('');
}

function renderHistory(history) {
  const count = (history && Array.isArray(history)) ? history.length : 0;
  const badge = document.getElementById("historyBadgeCount");
  if (badge) badge.innerText = count;
  const summary = document.getElementById("historySummaryText");
  if (summary) summary.innerText = count + " song" + (count === 1 ? "" : "s") + " played recently";
  const list = document.getElementById("historyList");
  if (!list) return;
  if (!history || history.length === 0) {
    list.innerHTML = `<div class="empty-state"><div class="empty-icon">🕒</div><div>No playback history yet.</div><div style="font-size:0.8rem; color:var(--text-muted)">Played tracks will automatically be recorded here!</div></div>`;
    return;
  }
  const rev = [...history].reverse();
  list.innerHTML = rev.map((t, idx) => ` <div class="track-item">
<span style="font-weight:700; color:var(--text-muted); font-size:0.8rem; width:22px;">#${idx + 1}</span>
<img class="track-thumb" src="${t.cover || ALBUM_PLACEHOLDER_SVG}" onerror="this.onerror=null; this.src='${ALBUM_PLACEHOLDER_SVG}';" />
<div class="track-info-col"> <span class="item-title">${escapeHtml(t.title)}</span>
<span class="item-artist">${escapeHtml(t.artist)} • ${t.duration || '--:--'} • <span class="tag-badge">${(t.source || 'PLAYED').toUpperCase()}</span></span>
</div> <div class="track-action-btns">
<button class="btn-small" title="Replay Now" onclick='queueTrackDirect(${JSON.stringify(t).replace(/'/g, "&#39;")}, true)'>▶ Replay</button>
<button class="btn-small" title="Queue Again" onclick='queueTrackDirect(${JSON.stringify(t).replace(/'/g, "&#39;")}, false)'>+ Queue</button>
</div> </div> `).join('');
}
let unlockerArmed = false;
function armAutoplayUnlocker() {
  if (unlockerArmed) return;
  unlockerArmed = true;
  const unlock = () => {
    const audio = document.getElementById("browserMonitorAudio");
    const btn = document.getElementById("btnAudioMonitor");
    if (audio && isMonitoring && audio.src && audio.paused) {
      audio.play().then(() => {
        if (btn) {
          btn.innerText = "🎧 Listen Live in Browser: ON";
          btn.classList.add("active");
        }
      }).catch(e => console.warn("Audio unlock notice:", e));
    }
    window.removeEventListener("click", unlock);
    window.removeEventListener("keydown", unlock);
    window.removeEventListener("pointerdown", unlock);
    unlockerArmed = false;
  };
  window.addEventListener("click", unlock, { once: true });
  window.addEventListener("keydown", unlock, { once: true });
  window.addEventListener("pointerdown", unlock, { once: true });
}

function toggleAudioMonitor() {
  const audio = document.getElementById("browserMonitorAudio");
  const btn = document.getElementById("btnAudioMonitor");
  if (!currentGuildId) {
    showToast("No server selected", "❌");
    return;
  }

  isMonitoring = !isMonitoring;
  localStorage.setItem("albumDiscoveryAudioMonitor", isMonitoring ? "true" : "false");
  if (isMonitoring) {
    lastMonitoredTrack = document.getElementById("trackTitle") ? document.getElementById("trackTitle").innerText : "";
    audio.src = "/api/guild/" + currentGuildId + "/stream?t=" + Date.now();
    audio.play().catch(e => {
      console.warn("Audio autoplay blocked by browser:", e);
      armAutoplayUnlocker();
    });
    btn.innerText = "🎧 Listen Live in Browser: ON";
    btn.classList.add("active");
    showToast("Live browser audio monitor connected 🎧", "🔊");
  } else {
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
    btn.innerText = "🎧 Listen Live in Browser: OFF";
    btn.classList.remove("active");
    showToast("Audio monitor disconnected", "🔇");
  }
}
function togglePlayPause() {
  if (!currentGuildId) return;
  isPlaying = !isPlaying;
  isPaused = !isPlaying;
  const btn = document.getElementById("btnPlayPause");
  if (btn) btn.innerText = (isPlaying && !isPaused) ? "\u23f8" : "\u25b6";
  const monAudio = document.getElementById("browserMonitorAudio");
  if (monAudio && isMonitoring) {
    if (isPlaying && !isPaused) monAudio.play().catch(e => {});
    else monAudio.pause();
  }
  sendControl("toggle_play");
}

function skipTrack() {
  if (!currentGuildId) return;
  if (window._skipDebounce && Date.now() - window._skipDebounce < 800) {
    return;
  }
  window._skipDebounce = Date.now();
  const monAudio = document.getElementById("browserMonitorAudio");
  if (monAudio) { monAudio.pause(); monAudio.removeAttribute("src"); }
  window._isSkipping = true;
  window._skippedTrackTitle = document.getElementById("trackTitle") ? document.getElementById("trackTitle").innerText : "";
  if (window._lastDeck2Track && window._lastDeck2Track.title) {
    document.getElementById("trackTitle").innerText = window._lastDeck2Track.title;
    document.getElementById("trackArtist").innerText = window._lastDeck2Track.artist || "";
    if (window._lastDeck2Track.cover) document.getElementById("trackCover").src = window._lastDeck2Track.cover;
    localElapsed = 0;
    localTotal = window._lastDeck2Track.duration_seconds || 0;
  } else {
    document.getElementById("trackTitle").innerText = "Skipping...";
    document.getElementById("trackArtist").innerText = "Loading next track...";
    localElapsed = 0; localTotal = 0;
  }
  lastPollTimestamp = performance.now();
  renderSeeker();
  sendControl("skip");
  setTimeout(() => pollGuildState(currentGuildId), 400);
}

async function sendControl(action, value = null) {
  if (!currentGuildId) return;
  try {
    await fetch("/api/guild/" + currentGuildId + "/control", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action, value })
    });
    showToast("Sent: " + action.replace('_', ' ').toUpperCase());
    if (action === "skip") {
      localElapsed = 0;
      localTotal = 0;
      lastPollTimestamp = performance.now();
      renderSeeker();
      document.getElementById("trackTitle").innerText = "Skipping...";
      document.getElementById("trackArtist").innerText = "Loading next track...";
    }
    pollGuildState(currentGuildId);
  } catch (e) {
    showToast("Command failed", "❌");
  }
}

function toggleAutoplay() {
  currentAutoplay = !currentAutoplay;
  const btn = document.getElementById("btnAutoplay");
  if (btn) {
    btn.innerText = currentAutoplay ? "✨ Autoplay: ON" : "Autoplay: OFF";
    btn.classList.toggle("active", currentAutoplay);
  }
  sendControl("set_autoplay", currentAutoplay);
}
function cycleQuality() {
  const q = ["auto", "128k", "192k", "320k"];
  const next = q[(q.indexOf(currentQuality) + 1) % q.length];
  sendControl("set_quality", next);
}

let volDebounce = null;
let isDraggingVol = false;
function onVolumeInput(val) {
  const num = parseInt(val) || 0;
  document.getElementById("volPct").innerText = num + "%";
  const monAudio = document.getElementById("browserMonitorAudio");
  if (monAudio && isMonitoring) monAudio.volume = Math.max(0, Math.min(1, num / 100));
  if (volDebounce) clearTimeout(volDebounce);
  volDebounce = setTimeout(() => { sendControl("set_volume", num); }, 120);
}
function toggleMute() {
  const slider = document.getElementById("volSlider");
  const monAudio = document.getElementById("browserMonitorAudio");
  const curr = parseInt(slider.value) || 0;
  if (curr > 0) {
    preMuteVolume = curr;
    slider.value = 0;
    document.getElementById("volPct").innerText = "0%";
    if (monAudio) monAudio.volume = 0;
    sendControl("set_volume", 0);
  } else {
    const res = preMuteVolume || 100;
    slider.value = res;
    document.getElementById("volPct").innerText = res + "%";
    if (monAudio) monAudio.volume = res / 100;
    sendControl("set_volume", res);
  }
}

async function joinSelectedVoice() {
  const select = document.getElementById("quickVcSelect");
  if (!select || !select.value) return;
  await fetch("/api/guild/" + currentGuildId + "/control", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action: "join_voice", channel_id: select.value })
  });
  showToast("Joined voice channel 🔊");
  setTimeout(() => pollGuildState(currentGuildId), 600);
}
async function removeQueueItem(index) { await fetch("/api/guild/" + currentGuildId + "/queue/remove", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ index }) }); showToast("Track removed from queue"); pollGuildState(currentGuildId); }
async function clearQueue() { if (!confirm("Are you sure you want to clear the entire queue?")) return; await fetch("/api/guild/" + currentGuildId + "/queue/clear", { method: "POST" }); showToast("Queue cleared"); pollGuildState(currentGuildId); }
async function moveQueueItem(from_index, to_index) { await fetch("/api/guild/" + currentGuildId + "/queue/move", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ from_index, to_index }) }); pollGuildState(currentGuildId); }
async function queuePlayNow(index) {
  const qItem = document.querySelectorAll("#queueList .queue-item")[index];
  if (qItem) {
    const t = qItem.querySelector(".item-title");
    const a = qItem.querySelector(".item-artist");
    if (t) document.getElementById("trackTitle").innerText = t.innerText;
    if (a) document.getElementById("trackArtist").innerText = a.innerText;
    localElapsed = 0;
  }
  await fetch("/api/guild/" + currentGuildId + "/queue/play_now", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ index }) });
  showToast("Playing track now ▶");
  pollGuildState(currentGuildId);
}
async function executeSearch() {
  const query = document.getElementById("searchInput").value.trim();
  const source = document.getElementById("searchSource").value;
  if (!query) return;
  const container = document.getElementById("searchResults");
  container.innerHTML = `<div class="empty-state"><div class="empty-icon">⏳</div><div>Searching for "${escapeHtml(query)}"...</div></div>`;
  try {
    const res = await fetch("/api/search?q=" + encodeURIComponent(query) + "&source=" + source);
    const data = await res.json();
    const results = data.results || [];
    if (results.length === 0) {
      container.innerHTML = `<div class="empty-state"><div class="empty-icon">❌</div><div>No tracks found for "${escapeHtml(query)}". Try another search query!</div></div>`;
      return;
    }

    container.innerHTML = results.map((r, idx) => {
      if (r.is_album) {
        const safeAid = String(r.id || idx).replace(/[^a-zA-Z0-9_-]/g, "_");
        const tracksTxt = r.tracks_count ? `${r.tracks_count} tracks` : "Full Album";
        return ` <div class="album-item-container"> <div class="album-card-item">
<img class="album-card-thumb" src="${r.cover || ALBUM_PLACEHOLDER_SVG}" onerror="this.onerror=null; this.src='${ALBUM_PLACEHOLDER_SVG}';" />
<div class="track-info-col"> <span class="item-title" style="font-size:0.95rem; font-weight:700;">${escapeHtml(r.title)}</span>
<span class="item-artist">${escapeHtml(r.artist)} • <span class="album-badge">💿 ${r.record_type || 'ALBUM'}</span> • <span style="color:#c77dff; font-weight:600;">${tracksTxt}</span></span>
</div> <div class="track-action-btns">
<button class="btn-small btn-view-tracks" id="btnTracks-search-${idx}-${safeAid}" data-album-id="${escapeHtml(String(r.id || ''))}" data-title="${escapeHtml(r.title)}" data-artist="${escapeHtml(r.artist)}" onclick="toggleAlbumTracks(this)">📋 View Tracklist</button>
<button class="btn-small" style="background:var(--accent-purple); color:#fff;" data-album-id="${escapeHtml(String(r.id || ''))}" data-title="${escapeHtml(r.title)}" data-artist="${escapeHtml(r.artist)}" onclick="queueAlbumDirect(this, true)">▶ Play Full LP</button>
<button class="btn-small" data-album-id="${escapeHtml(String(r.id || ''))}" data-title="${escapeHtml(r.title)}" data-artist="${escapeHtml(r.artist)}" onclick="queueAlbumDirect(this, false)">+ Add LP</button>
</div> </div> <div class="album-tracks-tray" id="tray-search-${idx}-${safeAid}" style="display:none;"></div> </div> `;
      }
      return ` <div class="track-item">
<img class="track-thumb" src="${r.cover || ALBUM_PLACEHOLDER_SVG}" onerror="this.onerror=null; this.src='${ALBUM_PLACEHOLDER_SVG}';" />
<div class="track-info-col"> <span class="item-title">${escapeHtml(r.title)}</span>
<span class="item-artist">${escapeHtml(r.artist)} • ${r.duration} • <span class="tag-badge">${r.source.toUpperCase()}</span></span>
</div> <div class="track-action-btns">
<button class="btn-small" onclick='queueTrackDirect(${JSON.stringify(r).replace(/\'/g, "&#39;")}, true)'>▶ Play Now</button>
<button class="btn-small" onclick='queueTrackDirect(${JSON.stringify(r).replace(/\'/g, "&#39;")}, false)'>+ Queue</button> </div>
</div> `;
    }).join('');
  } catch (e) {
    container.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><div>Search failed. Please try again.</div></div>`;
  }
}
async function queueTrackDirect(track, playNow = false) {
  if (!currentGuildId) currentGuildId = (document.getElementById("serverSelect") || {}).value || "";
  window.currentGuildId = currentGuildId;
  if (!currentGuildId) { showToast("No server selected", "❌"); return; }
  try {
    const body = {
      title: track.title,
      artist: track.artist,
      album: track.album || "",
      cover: track.cover || "",
      duration_seconds: track.duration_seconds || 0,
      video_id: track.video_id || null,
      source: track.source || "deezer",
      play_now: playNow
    };
    const res = await fetch("/api/guild/" + currentGuildId + "/play", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });
    const d = await res.json();
    if (res.ok) {
      showToast(playNow ? "Playing now ▶" : "Added to queue (#" + d.position + ")", "🎵");
      pollGuildState(currentGuildId);
    } else {
      showToast(d.error || "Failed to play", "⚠️");
    }
  } catch (e) {
    showToast("Playback request error", "❌");
  }
}

async function loadCharts(forceRefresh = false) {
  const container = document.getElementById("chartsList");
  const select = document.getElementById("chartCountrySelect");
  const country = select ? select.value : "gb";
  const titleEl = document.getElementById("chartsHeaderTitle");
  const badgeEl = document.getElementById("chartsBadge");
  container.innerHTML = `<div class="empty-state"><div class="empty-icon">⏳</div><div>Loading live official charts...</div></div>`;
  try {
    const res = await fetch(`/api/charts?country=${encodeURIComponent(country)}&refresh=${forceRefresh ? 1 : 0}`);
    const data = await res.json();
    const charts = data.charts || [];
    if (titleEl && data.title) titleEl.innerText = data.title;
    if (badgeEl && data.badge) badgeEl.innerText = data.badge;
    if (charts.length === 0) {
      container.innerHTML = `<div class="empty-state"><div class="empty-icon">❌</div><div>Could not load charts.</div></div>`;
      return;
    }
    container.innerHTML = charts.map((c, i) => {
      const durText = c.duration ? ` • ${c.duration}` : (c.release_date ? ` • ${c.release_date}` : "");
      let actions = "";
      if (c.is_album) {
        actions = `
<button class="btn-small" data-album-id="${escapeHtml(String(c.id || ''))}" data-title="${escapeHtml(c.title)}" data-artist="${escapeHtml(c.artist)}" onclick="queueAlbumDirect(this, true)">▶ Play</button>
<button class="btn-small" data-album-id="${escapeHtml(String(c.id || ''))}" data-title="${escapeHtml(c.title)}" data-artist="${escapeHtml(c.artist)}" onclick="queueAlbumDirect(this, false)">➕ Add</button>
`;
      } else {
        actions = ` <button class="btn-small" onclick='queueTrackDirect(${JSON.stringify(c).replace(/'/g, "&#39;")}, true)'>▶ Play</button>
<button class="btn-small" onclick='queueTrackDirect(${JSON.stringify(c).replace(/'/g, "&#39;")}, false)'>➕ Add</button> `;
      }
      return ` <div class="track-item">
<span style="font-weight:800; color:#c77dff; font-size:0.9rem; width:28px;">#${c.position || i + 1}</span>
<img class="track-thumb" src="${c.cover || ALBUM_PLACEHOLDER_SVG}" onerror="this.onerror=null; this.src='${ALBUM_PLACEHOLDER_SVG}';" />
<div class="track-info-col"> <span class="item-title">${escapeHtml(c.title)}</span>
<span class="item-artist">${escapeHtml(c.artist)}${durText}</span> </div> <div class="track-action-btns"> ${actions} </div> </div>
`;
    }).join('');
  } catch (e) {
    container.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><div>Failed to load charts.</div></div>`;
  }
}

let currentLogFilter = "all";
function setLogFilter(type, btn) {
  currentLogFilter = type;
  document.querySelectorAll(".log-filter-btn").forEach(b => b.classList.remove("active"));
  if (btn) btn.classList.add("active");
  loadLogs(true);
}
async function loadLogs(forceScroll = false) {
  const pre = document.getElementById("logsContainer");
  if (!pre) return;
  try {
    const res = await fetch("/api/logs?type=" + encodeURIComponent(currentLogFilter));
    const data = await res.json();
    const newText = (data.logs || []).join("\n") || `No ${currentLogFilter} log entries recorded yet.`;
    if (pre.innerText !== newText) {
      const isNearBottom = (pre.scrollHeight - pre.scrollTop - pre.clientHeight) < 50;
      pre.innerText = newText;
      if (forceScroll || isNearBottom) {
        pre.scrollTop = pre.scrollHeight;
      }
    }
  } catch (e) {
    // Keep existing view on transient network error
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}
let currentDiscographyData = null;
async function executeDiscographySearch() {
  const input = document.getElementById("discoArtistInput");
  const artist = (input ? input.value : "").trim();
  if (!artist) {
    showToast("Please enter an artist name", "⚠️");
    return;
  }

  const container = document.getElementById("discoAlbumList");
  const header = document.getElementById("discoArtistHeader");
  container.innerHTML = `<div class="empty-state"><div class="empty-icon">⏳</div><div>Querying MusicBrainz & Apple Music discography for "${escapeHtml(artist)}"...</div></div>`;
  if (header) header.innerHTML = "";
  try {
    const res = await fetch("/api/discography?artist=" + encodeURIComponent(artist));
    const data = await res.json();
    currentDiscographyData = data;
    if (!data.albums || data.albums.length === 0) {
      container.innerHTML = `<div class="empty-state"><div class="empty-icon">❌</div><div>No discography found for "${escapeHtml(artist)}".</div></div>`;
      return;
    }
    if (header) {
      const stats = Object.entries(data.counts || {}).map(([k, v]) => `<strong>${k}:</strong> ${v}`).join(" • ");
      header.innerHTML = `
<div style="display:flex; align-items:center; gap:12px; background:rgba(255,255,255,0.03); padding:10px 14px; border-radius:var(--radius-md); border:1px solid var(--border-color);">
${data.picture ? `<img src="${data.picture}" style="width:44px; height:44px; border-radius:50%; object-fit:cover;" onerror="this.style.display='none';" />` : ''} <div> <div style="font-weight:700; font-size:1rem; color:var(--text-bright);">${escapeHtml(data.artist)}</div>
<div style="font-size:0.75rem; color:var(--text-muted);">${stats || 'Classified Catalog'}</div> </div> </div> `;
    }

    const filterEl = document.getElementById("discoCategoryFilter");
    if (filterEl && data.categories) {
      let optHtml = `<option value="All">All Categories (${data.albums.length})</option>`;
      data.categories.forEach(c => {
        const count = data.counts ? (data.counts[c] || 0) : 0;
        let icon = "💿";
        if (c.includes("EP") || c.includes("Single")) icon = "📀";
        else if (c.includes("Collab")) icon = "🤝";
        else if (c.includes("Mixtape")) icon = "🔥";
        else if (c.includes("Compil")) icon = "📦";
        else if (c.includes("Live")) icon = "🎸";
        else if (c.includes("Remix")) icon = "🎛️";
        else if (c.includes("Soundtrack")) icon = "🎬";
        optHtml += `<option value="${escapeHtml(c)}">${icon} ${escapeHtml(c)} (${count})</option>`;
      });
      filterEl.innerHTML = optHtml;
      filterEl.value = "All";
    }
    renderDiscographyAlbums();
  } catch (e) {
    container.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><div>Failed to load discography.</div></div>`;
  }
}

function filterDiscographyCategory() {
  renderDiscographyAlbums();
}
function renderDiscographyAlbums() {
  if (!currentDiscographyData || !currentDiscographyData.albums) return;
  const container = document.getElementById("discoAlbumList");
  const filterEl = document.getElementById("discoCategoryFilter");
  const catFilter = filterEl ? filterEl.value : "All";
  let albums = currentDiscographyData.albums;
  if (catFilter !== "All") {
    albums = albums.filter(a => a.category === catFilter);
  }

  if (albums.length === 0) {
    container.innerHTML = `<div class="empty-state"><div class="empty-icon">📭</div><div>No releases found in category "${escapeHtml(catFilter)}".</div></div>`;
    return;
  }
  container.innerHTML = albums.map((a, idx) => {
    const yr = String(a.year || a.release_date || "").slice(0, 4);
    const cat = a.category || "Studio Album";
    const tracks = a.tracks_count || a.nb_tracks || 0;
    const coverSrc = (a.cover && a.cover.trim() && !a.cover.includes("coverartarchive.org")) ? a.cover : ALBUM_PLACEHOLDER_SVG;
    const safeAid = String(a.id || idx).replace(/[^a-zA-Z0-9_-]/g, "_");
    const isLP = cat === "Studio Albums";
    return ` <div class="album-item-container"> <div class="album-card-item">
<img class="album-card-thumb" src="${coverSrc}" onerror="this.onerror=null; this.src='${ALBUM_PLACEHOLDER_SVG}';" alt="" />
<div class="track-info-col"> <span class="item-title" style="font-size:0.95rem; font-weight:700;">${escapeHtml(a.title)} ${yr ? `<span style="color:var(--text-muted); font-size:0.8rem; font-weight:500;">(${yr})</span>` : ''}</span>
<span class="item-artist">${escapeHtml(a.artist || currentDiscographyData.artist)} • <span class="album-badge">${isLP ? '💿 ' : ''}${cat}</span> • <span style="color:#c77dff; font-weight:600;">${tracks ? tracks + ' tracks' : 'Full Release'}</span></span>
</div> <div class="track-action-btns">
<button class="btn-small btn-view-tracks" id="btnTracks-${idx}-${safeAid}" data-album-id="${escapeHtml(String(a.id || ''))}" data-title="${escapeHtml(a.title)}" data-artist="${escapeHtml(a.artist || currentDiscographyData.artist)}" onclick="toggleAlbumTracks(this)">📋 View Tracklist</button>
<button class="btn-small" style="background:var(--accent-purple); color:#fff;" data-album-id="${escapeHtml(String(a.id || ''))}" data-title="${escapeHtml(a.title)}" data-artist="${escapeHtml(a.artist || currentDiscographyData.artist)}" onclick="queueAlbumDirect(this, true)">▶ Play Release</button>
<button class="btn-small" data-album-id="${escapeHtml(String(a.id || ''))}" data-title="${escapeHtml(a.title)}" data-artist="${escapeHtml(a.artist || currentDiscographyData.artist)}" onclick="queueAlbumDirect(this, false)">+ Add Release</button>
</div> </div> <div class="album-tracks-tray" id="tray-disco-${idx}-${safeAid}" style="display:none;"></div> </div> `;
  }).join('');
}

function queueTrackFromData(btn, playNow = false) {
  if (!btn || !btn.dataset || !btn.dataset.track) return;
  try {
    const track = JSON.parse(decodeURIComponent(btn.dataset.track));
    queueTrackDirect(track, playNow);
  } catch (e) {
    console.error("Failed to parse track data:", e);
  }
}
async function queueAlbumDirect(btnOrId, playNow = false, title = '', artist = '') {
  if (!currentGuildId) currentGuildId = (document.getElementById("serverSelect") || {}).value || "";
  window.currentGuildId = currentGuildId;
  if (!currentGuildId) { showToast("No server selected", "❌"); return; }
  let albumId = '';
  if (btnOrId instanceof HTMLElement || (btnOrId && btnOrId.dataset)) {
    albumId = btnOrId.dataset.albumId || '';
    title = btnOrId.dataset.title || '';
    artist = btnOrId.dataset.artist || '';
  } else {
    albumId = String(btnOrId || '');
  }

  showToast(playNow ? "Loading album to play..." : "Adding album to queue...", "⏳");
  try {
    const res = await fetch("/api/guild/" + currentGuildId + "/play", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ album_id: albumId, play_now: playNow, title: title, artist: artist })
    });
    const d = await res.json();
    if (res.ok) {
      showToast(playNow ? `Playing album now! (${d.enqueued_count} tracks)` : `Added ${d.enqueued_count} tracks to queue!`, "💿");
      pollGuildState(currentGuildId);
    } else {
      showToast(d.error || "Failed to queue album", "⚠️");
    }
  } catch (e) {
    showToast("Error queuing album", "❌");
  }
}

window.onload = init;
