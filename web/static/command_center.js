// Command Center Extensions: Fast-Play, Time Machine & Cloud Radio
let allLoadedRadioStations = [];
let allLoadedTimeMachineAlbums = [];
let currentTimeMachineYear = 1999;
let currentRadioCategory = "all";
let currentTimeMachineGenre = "all";

// Unified Guild ID Resolver: checks local scope, window scope, and DOM dropdown
function getActiveGuildId() {
  if (typeof currentGuildId !== "undefined" && currentGuildId) {
    window.currentGuildId = currentGuildId;
    return currentGuildId;
  }
  if (window.currentGuildId) return window.currentGuildId;
  const select = document.getElementById("serverSelect");
  if (select && select.value) {
    window.currentGuildId = select.value;
    if (typeof currentGuildId !== "undefined") currentGuildId = select.value;
    return select.value;
  }
  return "";
}

// Fast-Play Quick Action
async function executeFastPlay(playNow = true) {
  const input = document.getElementById("fastPlayInput");
  const query = (input ? input.value : "").trim();
  if (!query) {
    if (typeof showToast === "function") showToast("Enter a track, album, or URL to play", "⚠️");
    return;
  }
  const guildId = getActiveGuildId();
  if (!guildId) {
    if (typeof showToast === "function") showToast("Select a server first", "❌");
    return;
  }
  input.value = "";
  if (typeof showToast === "function") showToast(playNow ? "Resolving track to play..." : "Adding to queue...", "⏳");
  try {
    const res = await fetch("/api/search?q=" + encodeURIComponent(query) + "&source=auto");
    const data = await res.json();
    const results = data.results || [];
    if (results.length > 0) {
      const topPick = results[0];
      if (typeof queueTrackDirect === "function") {
        await queueTrackDirect(topPick, playNow);
      }
    } else {
      if (typeof showToast === "function") showToast("No matches found for: " + query, "❌");
    }
  } catch (e) {
    if (typeof showToast === "function") showToast("Fast-Play failed", "❌");
  }
}

// Time Machine Tab Logic
async function loadTimeMachine(year = null) {
  const container = document.getElementById("timemachineGrid");
  const yearSelect = document.getElementById("tmYearSelect");
  if (year) currentTimeMachineYear = parseInt(year);
  if (!container) return;

  const yearBadge = document.getElementById("tmYearBadge");
  if (yearBadge) yearBadge.innerText = `YEAR ${currentTimeMachineYear}`;
  const summaryText = document.getElementById("tmSummaryText");
  if (summaryText) summaryText.innerText = `⏳ Landmark Releases & Masterpieces (${currentTimeMachineYear})`;

  container.innerHTML = `<div class="empty-state"><div class="empty-icon">⏳</div><div>Traveling through musical history to ${currentTimeMachineYear}...</div></div>`;
  try {
    const res = await fetch("/api/timemachine?year=" + currentTimeMachineYear);
    const data = await res.json();
    allLoadedTimeMachineAlbums = data.albums || [];
    const years = data.years || [];

    if (yearSelect && yearSelect.options.length <= 1 && years.length > 0) {
      yearSelect.innerHTML = years.map(y => `<option value="${y}" ${y === currentTimeMachineYear ? 'selected' : ''}>Year ${y}</option>`).join('');
    } else if (yearSelect) {
      yearSelect.value = currentTimeMachineYear;
    }

    renderTimeMachineAlbums();
  } catch (e) {
    container.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><div>Failed to load Time Machine albums.</div></div>`;
  }
}

function renderTimeMachineAlbums() {
  const container = document.getElementById("timemachineGrid");
  if (!container) return;

  let albums = allLoadedTimeMachineAlbums;
  if (currentTimeMachineGenre && currentTimeMachineGenre !== "all") {
    const gKey = currentTimeMachineGenre.toLowerCase();
    albums = albums.filter(a => {
      const g = ((a.genre || "") + " " + (a.desc || "") + " " + (a.title || "")).toLowerCase();
      if (gKey === "rock") return g.includes("rock") || g.includes("metal") || g.includes("grunge") || g.includes("punk") || g.includes("alternative");
      if (gKey === "hip-hop") return g.includes("hip-hop") || g.includes("rap") || g.includes("r&b");
      if (gKey === "electronic") return g.includes("electronic") || g.includes("dance") || g.includes("techno") || g.includes("house") || g.includes("trip-hop");
      if (gKey === "pop") return g.includes("pop") || g.includes("soul") || g.includes("r&b");
      return true;
    });
  }

  if (!albums || albums.length === 0) {
    container.innerHTML = `<div class="empty-state"><div class="empty-icon">❌</div><div>No landmark albums found for ${currentTimeMachineYear} in this genre.</div></div>`;
    return;
  }

  const placeholder = typeof ALBUM_PLACEHOLDER_SVG !== "undefined" ? ALBUM_PLACEHOLDER_SVG : "";
  container.innerHTML = albums.map(a => `
    <div class="tm-album-card">
      <img class="tm-card-thumb" src="${a.cover || placeholder}" onerror="this.onerror=null; this.src='${placeholder}';" />
      <div style="flex:1; display:flex; flex-direction:column; justify-content:space-between; min-width:0;">
        <div>
          <div style="font-weight:700; font-size:0.88rem; color:#fff; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;" title="${typeof escapeHtml === "function" ? escapeHtml(a.title) : a.title}">${typeof escapeHtml === "function" ? escapeHtml(a.title) : a.title}</div>
          <div style="font-size:0.75rem; color:var(--text-muted); margin-top:2px;">${typeof escapeHtml === "function" ? escapeHtml(a.artist) : a.artist} • <span style="color:#c77dff; font-weight:600;">${a.year || currentTimeMachineYear}</span></div>
          <div style="font-size:0.7rem; color:#94a3b8; margin-top:4px; line-height:1.2; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;">${typeof escapeHtml === "function" ? escapeHtml(a.desc || a.genre || 'Landmark Release') : (a.desc || a.genre || 'Landmark Release')}</div>
        </div>
        <div style="display:flex; gap:6px; margin-top:8px;">
          <button class="btn-small" style="padding:3px 8px; font-size:0.7rem;" data-album-id="${typeof escapeHtml === "function" ? escapeHtml(String(a.id || '')) : a.id}" data-title="${typeof escapeHtml === "function" ? escapeHtml(a.title) : a.title}" data-artist="${typeof escapeHtml === "function" ? escapeHtml(a.artist) : a.artist}" onclick="queueAlbumDirect(this, true)">▶ Play</button>
          <button class="btn-small" style="padding:3px 8px; font-size:0.7rem;" data-album-id="${typeof escapeHtml === "function" ? escapeHtml(String(a.id || '')) : a.id}" data-title="${typeof escapeHtml === "function" ? escapeHtml(a.title) : a.title}" data-artist="${typeof escapeHtml === "function" ? escapeHtml(a.artist) : a.artist}" onclick="queueAlbumDirect(this, false)">+ Add</button>
        </div>
      </div>
    </div>
  `).join('');
}

function selectDecade(startYear, btn) {
  document.querySelectorAll(".timemachine-nav-menu .sub-nav-pill").forEach(p => p.classList.remove("active"));
  if (btn) btn.classList.add("active");
  const yearSelect = document.getElementById("tmYearSelect");
  if (yearSelect) yearSelect.value = startYear;
  loadTimeMachine(startYear);
}

function selectTimeMachineGenre(genre, btn) {
  currentTimeMachineGenre = genre;
  document.querySelectorAll(".timemachine-genre-nav .sub-nav-pill").forEach(p => p.classList.remove("active"));
  if (btn) btn.classList.add("active");
  renderTimeMachineAlbums();
}

// Cloud Radio Tab Logic
async function loadCloudRadio() {
  const container = document.getElementById("radioStationsGrid");
  if (!container) return;
  container.innerHTML = `<div class="empty-state"><div class="empty-icon">⏳</div><div>Loading curated high-definition cloud radio stations...</div></div>`;
  try {
    const res = await fetch("/api/radio");
    const data = await res.json();
    allLoadedRadioStations = data.stations || [];
    
    // Update count badges
    const badge = document.getElementById("radioCountBadge");
    if (badge) badge.innerText = `${allLoadedRadioStations.length} STATIONS`;
    const pillAll = document.getElementById("pillCountAll");
    if (pillAll) pillAll.innerText = allLoadedRadioStations.length;
    const summary = document.getElementById("radioSummaryText");
    if (summary) summary.innerText = `📻 ${allLoadedRadioStations.length} Curated High-Definition Cloud Radio Stations`;
    
    applyRadioFilters("", currentRadioCategory);
  } catch (e) {
    container.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><div>Failed to load cloud stations.</div></div>`;
  }
}

function renderRadioStations(stations) {
  const container = document.getElementById("radioStationsGrid");
  if (!container) return;
  if (!stations || stations.length === 0) {
    container.innerHTML = `<div class="empty-state"><div class="empty-icon">❌</div><div>No stations match your filter in this category.</div></div>`;
    return;
  }
  container.innerHTML = stations.map(s => {
    const title = s.title || s.name || s.category || "Live Radio";
    const desc = s.desc || s.sub_title || "Curated 24/7 stream and seamless radio playlist.";
    const icon = s.icon || "📻";
    const genre = s.genre || s.category || "Curated";
    const safeTitle = typeof escapeHtml === "function" ? escapeHtml(title) : title;
    const safeDesc = typeof escapeHtml === "function" ? escapeHtml(desc) : desc;
    const safeGenre = typeof escapeHtml === "function" ? escapeHtml(genre) : genre;
    const stationId = s.id || s.radio_id || "";

    return `
      <div class="radio-station-card" onclick="tuneInRadio('${stationId}', '${safeTitle.replace(/'/g, "\\'")}')">
        <div class="radio-card-top">
          <div class="radio-station-icon">${icon}</div>
          <div style="flex:1; min-width:0;">
            <div class="radio-station-name" title="${safeTitle}">${safeTitle}</div>
            <div style="font-size:0.68rem; color:#38bdf8; font-weight:600; text-transform:uppercase;">${safeGenre}</div>
          </div>
          <span class="radio-live-tag">LIVE 📻</span>
        </div>
        <div class="radio-station-desc">${safeDesc}</div>
        <div class="radio-card-bottom">
          <span class="radio-genre-tag">${safeGenre}</span>
          <button class="btn-tune-in" onclick="event.stopPropagation(); tuneInRadio('${stationId}', '${safeTitle.replace(/'/g, "\\'")}')">▶ Tune In</button>
        </div>
      </div>
    `;
  }).join('');
}

function selectRadioCategory(category, btn) {
  currentRadioCategory = category;
  document.querySelectorAll(".radio-nav-menu .sub-nav-pill").forEach(p => p.classList.remove("active"));
  if (btn) btn.classList.add("active");

  const filterInput = document.getElementById("radioFilterInput");
  const query = filterInput ? filterInput.value.toLowerCase().trim() : "";
  applyRadioFilters(query, category);
}

function applyRadioFilters(query, category) {
  let filtered = allLoadedRadioStations;

  if (category && category !== "all") {
    filtered = filtered.filter(s => {
      const g = ((s.genre || "") + " " + (s.category || "") + " " + (s.title || "") + " " + (s.desc || "")).toLowerCase();
      if (category === "electronic") return g.includes("electronic") || g.includes("cyberpunk") || g.includes("synthwave") || g.includes("dance") || g.includes("house") || g.includes("dubstep") || g.includes("edm") || g.includes("bass") || g.includes("hardstyle");
      if (category === "rock") return g.includes("rock") || g.includes("metal") || g.includes("grunge") || g.includes("punk") || g.includes("alternative") || g.includes("indie");
      if (category === "hiphop") return g.includes("hip-hop") || g.includes("rap") || g.includes("trap") || g.includes("drill") || g.includes("phonk") || g.includes("r&b");
      if (category === "lofi") return g.includes("lofi") || g.includes("lo-fi") || g.includes("chillhop") || g.includes("acoustic chill") || g.includes("relaxing");
      if (category === "decades") return g.includes("80s") || g.includes("90s") || g.includes("70s") || g.includes("60s") || g.includes("50s") || g.includes("2000s") || g.includes("classic") || g.includes("retrowave") || g.includes("disco");
      if (category === "charts") return g.includes("hot 100") || g.includes("top 40") || g.includes("chart") || g.includes("viral");
      if (category === "ambient") return g.includes("ambient") || g.includes("jazz") || g.includes("blues") || g.includes("classical") || g.includes("soul");
      if (category === "pop") return g.includes("pop") || g.includes("k-pop") || g.includes("latin") || g.includes("city pop") || g.includes("afrobeats");
      return true;
    });
  }

  if (query) {
    filtered = filtered.filter(s => {
      const title = (s.title || s.name || "").toLowerCase();
      const desc = (s.desc || s.sub_title || "").toLowerCase();
      const cat = (s.category || s.genre || "").toLowerCase();
      return title.includes(query) || desc.includes(query) || cat.includes(query);
    });
  }

  renderRadioStations(filtered);
}

function filterRadioStations(query) {
  const q = (query || "").toLowerCase().trim();
  applyRadioFilters(q, currentRadioCategory);
}

async function tuneInRadio(stationId, stationName) {
  const guildId = getActiveGuildId();
  if (!guildId) {
    if (typeof showToast === "function") showToast("Select a server first", "❌");
    return;
  }
  if (typeof showToast === "function") showToast(`Tuning into station: ${stationName}...`, "📻");
  try {
    const res = await fetch(`/api/radio?station=${encodeURIComponent(stationId)}`);
    const data = await res.json();
    const tracks = data.tracks || [];
    if (tracks.length > 0) {
      if (typeof queueTrackDirect === "function") {
        await queueTrackDirect(tracks[0], true);
        for (let i = 1; i < Math.min(tracks.length, 6); i++) {
          await queueTrackDirect(tracks[i], false);
        }
      }
      if (typeof showToast === "function") showToast(`Now Streaming: ${stationName} 📻`, "🎶");
    } else {
      if (typeof showToast === "function") showToast("No active stream for this station", "⚠️");
    }
  } catch (e) {
    if (typeof showToast === "function") showToast("Failed to tune in", "❌");
  }
}

// Loop mode cycle handler
function cycleLoopMode() {
  const modes = ["off", "track", "queue"];
  const current = (window._currentLoopMode || "off");
  const next = modes[(modes.indexOf(current) + 1) % modes.length];
  window._currentLoopMode = next;
  if (typeof sendControl === "function") sendControl("set_loop", next);
  const badge = document.getElementById("cmdLoopStatus");
  if (badge) {
    badge.innerText = next === "off" ? "🔁 Loop: Off" : (next === "track" ? "🔂 Loop: Track" : "🔁 Loop: Queue");
    badge.style.color = next === "off" ? "var(--text-main)" : "#c77dff";
  }
  if (typeof showToast === "function") showToast("Loop: " + next.toUpperCase(), "🔁");
}

// Intercept tab switching to load dynamic tabs
(function setupTabHooks() {
  const originalSwitch = window.switchTab;
  window.switchTab = function(tabId, btn) {
    if (typeof originalSwitch === "function") {
      originalSwitch(tabId, btn);
    } else {
      document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
      if (btn) btn.classList.add("active");
      const target = document.getElementById("tab" + tabId.charAt(0).toUpperCase() + tabId.slice(1));
      if (target) target.classList.add("active");
    }
    if (tabId === "timemachine") loadTimeMachine();
    if (tabId === "radio") loadCloudRadio();
  };

  // Sync soundwave visualizer & badges periodically
  setInterval(() => {
    const btnPlay = document.getElementById("btnPlayPause");
    const viz = document.getElementById("soundwaveVisualizer");
    if (btnPlay && viz) {
      if (btnPlay.innerText.includes("⏸")) {
        viz.classList.add("playing-anim");
      } else {
        viz.classList.remove("playing-anim");
      }
    }
  }, 500);
})();


// Enhanced Queue Renderer: Synchronizes queue list & counters with Deck 2 & Deck 3 Autoplay preloads
window.renderQueue = function(queue, count, preloaded, deck3) {
  const badge = document.getElementById("queueBadgeCount");
  const summary = document.getElementById("queueSummaryText");
  const list = document.getElementById("queueList");
  if (!list) return;

  const hasUserQueue = queue && queue.length > 0;
  const autoplayItems = [];
  if (preloaded) {
    autoplayItems.push({ ...preloaded, deckLabel: "DECK 2 NEXT UP", badgeColor: "#22c55e" });
  }
  if (deck3) {
    autoplayItems.push({ ...deck3, deckLabel: "DECK 3 CUED", badgeColor: "#38bdf8" });
  }

  if (hasUserQueue) {
    if (badge) badge.innerText = count || queue.length;
    if (summary) summary.innerText = (count || queue.length) + " track" + (count === 1 ? "" : "s") + " up next";
    list.innerHTML = queue.map((t, idx) => `
      <div class="track-item">
        <span style="font-weight:700; color:var(--text-muted); font-size:0.8rem; width:20px;">#${idx + 1}</span>
        <img class="track-thumb" src="${t.cover || (typeof ALBUM_PLACEHOLDER_SVG !== 'undefined' ? ALBUM_PLACEHOLDER_SVG : '')}" onerror="this.onerror=null;" />
        <div class="track-info-col">
          <span class="item-title">${typeof escapeHtml === 'function' ? escapeHtml(t.title) : t.title}</span>
          <span class="item-artist">${typeof escapeHtml === 'function' ? escapeHtml(t.artist) : t.artist} • ${t.duration || '--:--'}</span>
        </div>
        <div class="track-action-btns">
          ${idx > 0 ? `<button class="btn-small" title="Move Up" onclick="moveQueueItem(${idx}, ${idx - 1})">▲</button>` : ''}
          ${idx < queue.length - 1 ? `<button class="btn-small" title="Move Down" onclick="moveQueueItem(${idx}, ${idx + 1})">▼</button>` : ''}
          <button class="btn-small" title="Play Now" onclick="queuePlayNow(${idx})">▶</button>
          <button class="btn-small btn-danger" title="Remove" onclick="removeQueueItem(${idx})">✕</button>
        </div>
      </div>
    `).join('');
    return;
  }

  if (autoplayItems.length > 0) {
    if (badge) badge.innerText = `${autoplayItems.length} (AI)`;
    if (summary) summary.innerHTML = `<span style="color:#c77dff; font-weight:700;">✨ ${autoplayItems.length} Tracks Up Next (Autonomous AI Autoplay DJ)</span>`;
    list.innerHTML = `
      <div style="display:flex; flex-direction:column; gap:8px;">
        ${autoplayItems.map((t, idx) => `
          <div class="track-item" style="border:1px solid rgba(157, 78, 221, 0.25); background:rgba(22, 24, 38, 0.65);">
            <span style="font-weight:700; color:${t.badgeColor}; font-size:0.75rem; width:22px;">#${idx + 1}</span>
            <img class="track-thumb" src="${t.cover || (typeof ALBUM_PLACEHOLDER_SVG !== 'undefined' ? ALBUM_PLACEHOLDER_SVG : '')}" onerror="this.onerror=null;" />
            <div class="track-info-col">
              <span class="item-title">${typeof escapeHtml === 'function' ? escapeHtml(t.title) : t.title}</span>
              <span class="item-artist">${typeof escapeHtml === 'function' ? escapeHtml(t.artist) : t.artist} • ${t.duration || '--:--'} • <span class="tag-badge" style="background:rgba(157,78,221,0.15); color:#c77dff; border:1px solid rgba(157,78,221,0.3);">${t.deckLabel}</span></span>
            </div>
            <div class="track-action-btns">
              <button class="btn-small" style="background:var(--accent-purple); color:#fff;" title="Play Now" onclick='queueTrackDirect(${JSON.stringify(t).replace(/'/g, "&#39;")}, true)'>▶ Play Now</button>
            </div>
          </div>
        `).join('')}
        <div style="font-size:0.74rem; color:var(--text-muted); text-align:center; padding:10px 0;">
          💡 Autonomous AI Autoplay will keep music flowing continuously. Add your own tracks anytime via Search, Charts, or Fast-Play to take over the queue!
        </div>
      </div>
    `;
    return;
  }

  if (badge) badge.innerText = "0";
  if (summary) summary.innerText = "0 tracks up next";
  list.innerHTML = `
    <div class="empty-state">
      <div class="empty-icon">📭</div>
      <div>The queue is currently empty.</div>
      <div style="font-size:0.8rem; color:var(--text-muted)">Use Search, Trending Charts, or Fast-Play to add tracks!</div>
    </div>
  `;
};


// Toggle Vibe Anchor Lock
async function toggleAnchorLock() {
  const guildId = getActiveGuildId();
  if (!guildId) return;
  try {
    const res = await fetch(`/api/guild/${guildId}/control`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "toggle_anchor_lock" })
    });
    const data = await res.json();
    if (typeof showToast === "function") {
      if (data.is_locked) {
        showToast(`🔒 Anchor locked to: ${data.anchor}`, "⚓");
      } else {
        showToast("🔓 Anchor unlocked (Organic Flow)", "🌊");
      }
    }
    if (typeof fetchGuildState === "function") fetchGuildState();
  } catch (err) {
    console.error("toggleAnchorLock error:", err);
  }
}

// Update Anchor UI Badge
window.updateAnchorBadge = function(p) {
  const badge = document.getElementById("anchorBadge");
  const nameEl = document.getElementById("anchorArtistName");
  const iconEl = document.getElementById("anchorLockIcon");
  if (!badge) return;
  if (!p || !p.current_track) {
    badge.style.display = "none";
    return;
  }
  const brain = p.brain || {};
  const anchor = brain.vibe_anchor_artist || p.current_track.artist || "None";
  const isLocked = Boolean(brain.is_anchor_locked);
  
  if (nameEl) nameEl.textContent = anchor;
  if (iconEl) iconEl.textContent = isLocked ? "🔒" : "🔓";
  if (isLocked) {
    badge.classList.add("locked");
    badge.title = "Vibe Anchor is LOCKED to " + anchor + ". Click to unlock.";
  } else {
    badge.classList.remove("locked");
    badge.title = "Vibe Anchor: " + anchor + " (Free Flow). Click to lock.";
  }
  badge.style.display = "inline-flex";
};

// Global Keyboard & Wheel Shortcuts Setup
document.addEventListener("DOMContentLoaded", () => {
  // Volume Mouse Wheel
  const volSlider = document.getElementById("volumeSlider");
  if (volSlider) {
    volSlider.addEventListener("wheel", (e) => {
      e.preventDefault();
      let cur = parseInt(volSlider.value) || 100;
      let delta = e.deltaY < 0 ? 5 : -5;
      let next = Math.max(0, Math.min(100, cur + delta));
      volSlider.value = next;
      if (typeof setVolume === "function") setVolume(next);
    }, { passive: false });
  }

  // Enter Key on Search inputs
  const searchInput = document.getElementById("searchInput");
  if (searchInput) {
    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        if (typeof searchTracks === "function") searchTracks();
      }
    });
  }

  const discoInput = document.getElementById("discoArtistInput");
  if (discoInput) {
    discoInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        if (typeof searchDiscography === "function") searchDiscography();
      }
    });
  }

  const fastPlayInput = document.getElementById("fastPlayInput");
  if (fastPlayInput) {
    fastPlayInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        executeFastPlay(true);
      }
    });
  }
});

// Album Tracks Tray Toggle Extension
async function toggleAlbumTracks(btnOrId, title = '', artist = '', trayId = '', btn = null) {
  let albumId = '';
  if (btnOrId instanceof HTMLElement || (btnOrId && btnOrId.dataset)) {
    btn = btnOrId;
    albumId = btn.dataset.albumId || '';
    title = btn.dataset.title || '';
    artist = btn.dataset.artist || '';
  } else {
    albumId = String(btnOrId || '');
  }

  // 1. Locate the tray using DOM tree traversal first (guarantees zero ID collision)
  let tray = null;
  if (btn instanceof HTMLElement) {
    const container = btn.closest('.album-item-container');
    if (container) {
      tray = container.querySelector('.album-tracks-tray');
    }
  }
  if (!tray && trayId) {
    tray = document.getElementById(trayId);
  }
  if (!tray && albumId) {
    tray = document.getElementById('tray-' + albumId) || document.getElementById('tray-search-' + albumId);
  }
  if (!tray) {
    console.error("Album tracks tray not found for album:", albumId, title);
    return;
  }
  // 2. Toggle visibility
  const isHidden = (tray.style.display === "none" || tray.style.display === "");
  if (!isHidden) {
    tray.style.display = "none";
    if (btn) btn.innerHTML = "📋 View Tracks";
    return;
  }

  tray.style.display = "flex";
  if (btn) btn.innerHTML = "▲ Hide Tracks";
  if (tray.dataset.loaded === "true") return;
  tray.innerHTML = `
    <div style="padding:10px; color:var(--text-muted); font-size:0.8rem; text-align:center;">
      <span style="display:inline-block; animation:pulse 1s infinite;">⏳</span> Loading tracklist for "${escapeHtml(title)}"...
    </div>
  `;
  try {
    const url = `/api/album/tracks?id=${encodeURIComponent(albumId)}&title=${encodeURIComponent(title)}&artist=${encodeURIComponent(artist)}`;
    const res = await fetch(url);
    const data = await res.json();
    const tracks = data.tracks || [];
    if (!tracks || tracks.length === 0) {
      tray.innerHTML = `<div style="padding:8px; color:var(--text-muted); font-size:0.8rem; text-align:center;">No tracklist found for this release.</div>`;
      tray.dataset.loaded = "true";
      return;
    }
    let html = `
      <div class="album-tray-header">
        <span>${tracks.length} tracks • ${escapeHtml(data.title)}</span>
        <div style="display:flex; gap:6px;">
          <button class="btn-small btn-tray-action" data-album-id="${escapeHtml(String(albumId))}" data-title="${escapeHtml(title)}" data-artist="${escapeHtml(artist)}" onclick="queueAlbumDirect(this, true)">▶ Play All</button>
          <button class="btn-small btn-tray-action" data-album-id="${escapeHtml(String(albumId))}" data-title="${escapeHtml(title)}" data-artist="${escapeHtml(artist)}" onclick="queueAlbumDirect(this, false)">+ Add All</button>
        </div>
      </div>
    `;
    tracks.forEach((t, i) => {
      const trackPayload = encodeURIComponent(JSON.stringify({
        title: t.title,
        artist: t.artist,
        album: data.title,
        duration: t.duration,
        duration_seconds: t.duration_seconds,
        cover: data.cover || t.cover || "",
        source: t.source || "deezer"
      }));
      html += `
        <div class="subtrack-item">
          <span class="subtrack-num">#${t.track_num || i + 1}</span>
          <div class="subtrack-info">
            <span class="subtrack-title">${escapeHtml(t.title)}</span>
            <span class="subtrack-meta">${escapeHtml(t.artist)} • ${t.duration}</span>
          </div>
          <div class="subtrack-actions">
            <button class="btn-small btn-tray-action" title="Play This Track" data-track="${trackPayload}" onclick="queueTrackFromData(this, true)">▶ Play</button>
            <button class="btn-small btn-tray-action" title="Queue This Track" data-track="${trackPayload}" onclick="queueTrackFromData(this, false)">+ Queue</button>
          </div>
        </div>
      `;
    });
    tray.innerHTML = html;
    tray.dataset.loaded = "true";
  } catch (err) {
    tray.innerHTML = `<div style="padding:8px; color:#ef4444; font-size:0.8rem;">Failed to load tracks.</div>`;
  }
}
