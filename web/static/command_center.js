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
    if (tabId === "crate") loadCrate(window.currentCratePlaylist || "Favorites");
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
              <button class="btn-small" style="background:var(--accent-purple); color:#fff;" title="Play Now" data-tid="${window.registerTrackRef ? window.registerTrackRef(t) : ''}" onclick="handleTrackBtn(this, 'play')" >▶ Play Now</button>
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
  const lockIcon = document.getElementById("anchorLockIcon");
  if (lockIcon) lockIcon.innerText = lockIcon.innerText.includes("🔒") ? "🔓" : "🔒";
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
    if (typeof pollGuildState === "function") pollGuildState(guildId);
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
  const volSlider = document.getElementById("volSlider");
  if (volSlider) {
    volSlider.addEventListener("wheel", (e) => {
      e.preventDefault();
      let cur = parseInt(volSlider.value) || 100;
      let delta = e.deltaY < 0 ? 5 : -5;
      let next = Math.max(0, Math.min(100, cur + delta));
      volSlider.value = next;
      if (typeof onVolumeInput === "function") onVolumeInput(next);
    }, { passive: false });
  }

  // Enter Key on Search inputs
  const searchInput = document.getElementById("searchInput");
  if (searchInput) {
    searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        if (typeof executeSearch === "function") executeSearch();
      }
    });
  }

  const discoInput = document.getElementById("discoArtistInput");
  if (discoInput) {
    discoInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        if (typeof executeDiscographySearch === "function") executeDiscographySearch();
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

// Thumbs Up / Down Vibe Training Feedback System
window.sendTasteFeedback = async function(vote) {
  const guildId = typeof getActiveGuildId === "function" ? getActiveGuildId() : (window.currentGuildId || "");
  if (!guildId) return;

  const btnUp = document.getElementById("btnThumbUp");
  const btnDown = document.getElementById("btnThumbDown");
  const artistEl = document.getElementById("trackArtist");
  const titleEl = document.getElementById("trackTitle");
  const artist = artistEl ? artistEl.innerText.trim() : "";
  const title = titleEl ? titleEl.innerText.trim() : "";

  // 0ms Optimistic UI Feedback
  if (vote === "up") {
    if (btnUp) btnUp.classList.add("active-up");
    if (btnDown) btnDown.classList.remove("active-down");
    if (typeof showToast === "function") showToast(`👍 AI Vibe Trained: Boosted "${artist}"`, "✨");
  } else {
    if (btnDown) btnDown.classList.add("active-down");
    if (btnUp) btnUp.classList.remove("active-up");
    if (typeof showToast === "function") showToast(`👎 Disliked: Banish "${artist}" & skipping`, "⛔");
    if (typeof skipTrack === "function") skipTrack();
  }

  try {
    const res = await fetch(`/api/guild/${guildId}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ artist, title, vote })
    });
    const data = await res.json();
    if (data && data.taste_profile) {
      window.updateTasteStats(data.taste_profile);
    }
  } catch (e) {
    console.error("sendTasteFeedback error:", e);
  }
};

window.updateTasteStats = function(profile) {
  if (!profile) return;
  const pill = document.getElementById("tasteStatPill");
  const txt = document.getElementById("tasteStatText");
  if (!pill || !txt) return;
  const likes = profile.likes_count || 0;
  const dislikes = profile.dislikes_count || 0;
  if (likes > 0 || dislikes > 0) {
    pill.style.display = "inline-flex";
    txt.innerText = `${likes} 👍 | ${dislikes} 👎`;
  }
};


// ============================================================
// Music DNA & Genre Spectrum Visualization Engine
// ============================================================
window.refreshMusicDna = async function(btnEl) {
  const btn = btnEl || document.getElementById("btnRefreshDna");
  if (btn) {
    btn.style.opacity = "0.6";
    btn.style.pointerEvents = "none";
    const icon = btn.querySelector(".refresh-icon");
    if (icon) icon.style.animation = "spin 0.6s linear infinite";
  }
  const dnaCard = document.getElementById("sec-dna");
  if (dnaCard) dnaCard.style.transition = "opacity 0.2s ease";

  const guildId = typeof getActiveGuildId === "function" ? getActiveGuildId() : (window.currentGuildId || "");
  if (!guildId) {
    if (btn) {
      btn.style.opacity = "1";
      btn.style.pointerEvents = "auto";
      const icon = btn.querySelector(".refresh-icon");
      if (icon) icon.style.animation = "";
    }
    return;
  }

  try {
    const res = await fetch(`/api/guild/${guildId}/dna`);
    if (res.ok) {
      const dna = await res.json();
      window.renderMusicDnaGraph(dna);
      if (btnEl && typeof showToast === "function") {
        showToast("Music DNA Analyzed & Updated", "🧬");
      }
    }
  } catch (err) {
    console.error("refreshMusicDna error:", err);
  } finally {
    if (btn) {
      setTimeout(() => {
        btn.style.opacity = "1";
        btn.style.pointerEvents = "auto";
        const icon = btn.querySelector(".refresh-icon");
        if (icon) icon.style.animation = "";
      }, 350);
    }
  }
};

window.renderMusicDnaGraph = function(dna) {
  if (!dna) return;

  const genreIcons = {
    "Pop & Mainstream": "🌟",
    "Dance & Electronic": "🎧",
    "Rock & Alternative": "🎸",
    "Hip-Hop & Rap": "🎤",
    "R&B & Soul": "🎷",
    "Indie & Folk": "🌿",
    "Soundtrack & Film": "🎬",
    "Jazz & Blues": "🎺",
    "Metal & Hardcore": "⚡",
    "Latin & World": "💃"
  };

  // Subtitle
  const subEl = document.getElementById("dnaSummarySubtitle");
  if (subEl) {
    const total = dna.total_analyzed ?? dna.total_tracks_analyzed ?? 0;
    const dom = dna.dominant_genre || dna.primary_genre || "Awaiting Tracks";
    const sub = dna.dominant_subgenre ? ` • Style: ${dna.dominant_subgenre}` : "";
    subEl.innerText = `${total} session tracks analyzed • Dominant Genre: ${dom}${sub}`;
  }

  // Multi-color spectrum bar
  const barEl = document.getElementById("dnaSpectrumBar");
  if (barEl && Array.isArray(dna.genres) && dna.genres.length > 0) {
    barEl.innerHTML = dna.genres.map(g => {
      const name = g.genre || g.name || "Music";
      const pct = g.percent ?? g.percentage ?? 0;
      const col = g.color || "#8b5cf6";
      const icon = genreIcons[name] || "🎵";
      return `
        <div class="dna-bar-segment" style="width: ${pct}%; background: ${col};" title="${escapeHtml(name)}: ${pct}% (${g.count} tracks)">
          ${pct >= 10 ? `${icon} ${pct}%` : ''}
        </div>
      `;
    }).join("");
  } else if (barEl) {
    barEl.innerHTML = `<div class="dna-bar-segment" style="width:100%; background:rgba(255,255,255,0.06); color:#94a3b8;">No session tracks yet. Play music to generate DNA!</div>`;
  }

  // Genre pills grid
  const gridEl = document.getElementById("dnaGenresGrid");
  if (gridEl && Array.isArray(dna.genres)) {
    gridEl.innerHTML = dna.genres.map(g => {
      const name = g.genre || g.name || "Music";
      const pct = g.percent ?? g.percentage ?? 0;
      const col = g.color || "#8b5cf6";
      const icon = genreIcons[name] || "🎵";
      return `
        <div class="dna-genre-pill" style="border-left: 3px solid ${col};">
          <span class="dna-genre-dot" style="background: ${col};"></span>
          <span>${icon} <strong>${escapeHtml(name)}</strong></span>
          <span style="color:#94a3b8; font-size:0.7rem;">${pct}% (${g.count})</span>
        </div>
      `;
    }).join("");
  }

  // Meters: Energy, Danceability, Acoustic Ratio, Profile
  const energy = dna.avg_energy ?? dna.energy_score ?? 0;
  const energyBar = document.getElementById("dnaEnergyBar");
  const energyVal = document.getElementById("dnaEnergyVal");
  if (energyBar && energyVal) {
    energyBar.style.width = `${energy}%`;
    energyVal.innerText = `${energy}%`;
  }

  const dance = dna.avg_danceability ?? dna.danceability_score ?? 0;
  const danceBar = document.getElementById("dnaDanceBar");
  const danceVal = document.getElementById("dnaDanceVal");
  if (danceBar && danceVal) {
    danceBar.style.width = `${dance}%`;
    danceVal.innerText = `${dance}%`;
  }

  const acoustic = dna.avg_acoustic ?? dna.acousticness_score ?? 0;
  const acousticBar = document.getElementById("dnaAcousticBar");
  const acousticVal = document.getElementById("dnaAcousticVal");
  if (acousticBar && acousticVal) {
    acousticBar.style.width = `${acoustic}%`;
    const elecRatio = dna.electronic_ratio !== undefined ? `${dna.electronic_ratio}% Elec` : "";
    acousticVal.innerText = elecRatio ? `${elecRatio} / ${acoustic}% Acous` : `${acoustic}%`;
  }

  const profileEl = document.getElementById("dnaSonicProfile");
  if (profileEl) {
    profileEl.innerText = dna.vibe_description || dna.sonic_profile || "Dynamic Flow";
  }

  // Top artists pills (Clean curated view: max 8)
  const artistsEl = document.getElementById("dnaTopArtists");
  const rawArtists = dna.artist_pills || dna.top_artists || [];
  const artists = rawArtists.slice(0, 8);
  if (artistsEl && Array.isArray(artists)) {
    if (artists.length === 0) {
      artistsEl.innerHTML = `<span style="font-size:0.7rem; color:var(--text-muted);">Queue songs to build influence map</span>`;
    } else {
      artistsEl.innerHTML = artists.map(a => {
        const art = a.artist || "Artist";
        const sub = a.sub_genre ? ` • ${escapeHtml(a.sub_genre)}` : (a.count ? ` ×${a.count}` : "");
        const col = a.color || "#c084fc";
        return `<span class="dna-artist-pill" style="border-color:${col}40;">${escapeHtml(art)} <strong style="color:${col};">${sub}</strong></span>`;
      }).join("");
    }
  }
};

// Auto-hook into brain tab switch
document.addEventListener("DOMContentLoaded", () => {
  const brainTabBtn = document.querySelector(`.tab-btn[onclick*="'brain'"]`);
  if (brainTabBtn) {
    brainTabBtn.addEventListener("click", () => {
      setTimeout(window.refreshMusicDna, 100);
    });
  }
});

// Periodic DNA update when brain tab is active
setInterval(() => {
  const tab = document.getElementById("tabBrain");
  if (tab && tab.classList.contains("active") && typeof window.refreshMusicDna === "function") {
    window.refreshMusicDna();
  }
}, 12000);

// ============================================================
// ❤️ My Crate (Saved Favorites & Custom Playlists) Engine
// ============================================================
window.currentCratePlaylist = "Favorites";
window.cachedCrateKeys = new Set();

async function postCrateAction(payload) {
  const guildId = getActiveGuildId();
  if (!guildId) return null;
  const res = await fetch(`/api/guild/${guildId}/crate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  return { ok: res.ok, data: await res.json() };
}

window.loadCrate = async function(playlistName = null) {
  const guildId = getActiveGuildId();
  if (!guildId) return;
  if (playlistName) window.currentCratePlaylist = playlistName;
  const pl = window.currentCratePlaylist || "Favorites";
  try {
    const res = await fetch(`/api/guild/${guildId}/crate?playlist=${encodeURIComponent(pl)}`);
    if (res.ok) renderCrateUI(await res.json());
  } catch (e) { console.warn("loadCrate error:", e); }
};

function renderCrateUI(data) {
  if (!data) return;
  const pl = data.playlist || window.currentCratePlaylist || "Favorites";
  window.currentCratePlaylist = pl;
  const playlists = data.playlists || [{ name: "Favorites", count: 0 }];
  const tracks = data.tracks || [];
  const badge = document.getElementById("crateBadgeCount");
  if (badge) badge.innerText = data.total_count ?? tracks.length;

  if (pl === "Favorites") {
    window.cachedCrateKeys = new Set(tracks.map(t => `${(t.artist || '').toLowerCase().trim()}:::${(t.title || '').toLowerCase().trim()}`));
    syncSaveCrateButtonState();
  }

  const nav = document.getElementById("cratePlaylistsNav");
  if (nav) {
    nav.innerHTML = playlists.map(p => {
      const safeName = typeof escapeHtml === "function" ? escapeHtml(p.name) : p.name;
      return `<button class="sub-nav-pill ${p.name === pl ? 'active' : ''}" onclick="selectCratePlaylist('${safeName.replace(/'/g, "\\'")}')">${p.name === "Favorites" ? "❤️" : "💿"} ${safeName} (${p.count || 0})</button>`;
    }).join("");
  }

  const summary = document.getElementById("crateSummaryText");
  if (summary) summary.innerText = `${pl === "Favorites" ? "❤️" : "💿"} ${pl} (${tracks.length} saved song${tracks.length === 1 ? "" : "s"})`;
  const delBtn = document.getElementById("btnDeleteCratePlaylist");
  if (delBtn) delBtn.innerText = pl === "Favorites" ? "🗑️ Clear Favorites" : "🗑️ Delete Playlist";

  const list = document.getElementById("crateTrackList");
  if (!list) return;
  if (tracks.length === 0) {
    list.innerHTML = `<div class="empty-state"><div class="empty-icon">❤️</div><div>No saved tracks in "${typeof escapeHtml === "function" ? escapeHtml(pl) : pl}" yet.</div><div style="font-size:0.8rem; color:var(--text-muted)">Click the ❤️ Save button on the player deck, search results, or history to build your crate!</div></div>`;
    return;
  }

  const placeholder = typeof ALBUM_PLACEHOLDER_SVG !== "undefined" ? ALBUM_PLACEHOLDER_SVG : "";
  list.innerHTML = tracks.map((t, idx) => {
    const safeKey = (t.track_key || `${(t.artist || '').toLowerCase()}:::${(t.title || '').toLowerCase()}`).replace(/'/g, "\\'");
    const payload = JSON.stringify(t).replace(/'/g, "&#39;");
    return `<div class="track-item">
      <span style="font-weight:700; color:#fda4af; font-size:0.8rem; width:24px;">#${idx + 1}</span>
      <img class="track-thumb" src="${t.cover || placeholder}" onerror="this.onerror=null; this.src='${placeholder}';" />
      <div class="track-info-col">
        <span class="item-title">${typeof escapeHtml === "function" ? escapeHtml(t.title) : t.title}</span>
        <span class="item-artist">${typeof escapeHtml === "function" ? escapeHtml(t.artist) : t.artist} • ${t.duration || '--:--'} • <span class="tag-badge">${(t.source || 'SAVED').toUpperCase()}</span></span>
      </div>
      <div class="track-action-btns">
        <button class="btn-small" title="Play Now" onclick='queueTrackDirect(${payload}, true)'>▶ Play</button>
        <button class="btn-small" title="Add to Queue" onclick='queueTrackDirect(${payload}, false)'>+ Queue</button>
        <button class="btn-small btn-danger" title="Remove from Crate" onclick="removeCrateTrack('${safeKey}')">✕</button>
      </div>
    </div>`;
  }).join("");
}

function syncSaveCrateButtonState() {
  const btnTxt = document.getElementById("btnSaveCrateText");
  const titleEl = document.getElementById("trackTitle");
  const artistEl = document.getElementById("trackArtist");
  if (!btnTxt || !titleEl || !artistEl) return;
  const key = `${artistEl.innerText.trim().toLowerCase()}:::${titleEl.innerText.trim().toLowerCase()}`;
  btnTxt.innerText = (window.cachedCrateKeys && window.cachedCrateKeys.has(key)) ? "Saved" : "Save";
}

window.selectCratePlaylist = function(name) { window.currentCratePlaylist = name || "Favorites"; loadCrate(window.currentCratePlaylist); };

window.saveCurrentToCrate = async function() {
  const titleEl = document.getElementById("trackTitle"), artistEl = document.getElementById("trackArtist"), coverEl = document.getElementById("trackCover");
  const title = titleEl ? titleEl.innerText.trim() : "", artist = artistEl ? artistEl.innerText.trim() : "";
  if (!title || title === "Nothing Playing" || title === "Skipping...") {
    if (typeof showToast === "function") showToast("No active track playing to save", "⚠️");
    return;
  }
  await saveTrackToCrate({
    title, artist, cover: (coverEl && coverEl.style.display !== "none") ? coverEl.src : "",
    duration_seconds: typeof localTotal !== "undefined" ? localTotal : 0,
    duration: typeof formatTime === "function" && typeof localTotal !== "undefined" ? formatTime(localTotal) : ""
  });
};

window.saveTrackToCrate = async function(trackObj, targetPlaylist = null) {
  if (!trackObj) return;
  const pl = targetPlaylist || window.currentCratePlaylist || "Favorites";
  try {
    const res = await postCrateAction({ action: "add", playlist: pl, track: trackObj });
    if (res && res.ok) {
      renderCrateUI(res.data);
      if (typeof showToast === "function") showToast(res.data.added ? `❤️ Saved "${trackObj.title}" to ${pl}!` : `❤️ Already in ${pl}`, "❤️");
    }
  } catch (e) { if (typeof showToast === "function") showToast("Failed to save track", "❌"); }
};

window.removeCrateTrack = async function(trackKey) {
  const pl = window.currentCratePlaylist || "Favorites";
  try {
    const res = await postCrateAction({ action: "remove", playlist: pl, track_key: trackKey });
    if (res && res.ok) { renderCrateUI(res.data); if (typeof showToast === "function") showToast("Removed from " + pl, "🗑️"); }
  } catch (e) {}
};

window.createNewCratePlaylist = async function() {
  const input = document.getElementById("newPlaylistInput");
  const name = (input ? input.value : "").trim();
  if (!name) { if (typeof showToast === "function") showToast("Enter a playlist name first", "⚠️"); return; }
  input.value = "";
  try {
    const res = await postCrateAction({ action: "create_playlist", playlist: name });
    if (res && res.ok) { renderCrateUI(res.data); if (typeof showToast === "function") showToast(`💿 Created playlist: ${name}`, "✨"); }
  } catch (e) {}
};

window.deleteActiveCratePlaylist = async function() {
  const pl = window.currentCratePlaylist || "Favorites";
  if (!confirm(pl === "Favorites" ? "Clear all saved songs in Favorites?" : `Delete custom playlist "${pl}" and its saved songs?`)) return;
  try {
    const res = await postCrateAction({ action: "delete_playlist", playlist: pl });
    if (res && res.ok) { renderCrateUI(res.data); if (typeof showToast === "function") showToast(pl === "Favorites" ? "Favorites cleared" : `Deleted playlist "${pl}"`, "🗑️"); }
  } catch (e) {}
};

window.playCrateAll = async function(shuffle = false, playNow = false) {
  const pl = window.currentCratePlaylist || "Favorites";
  try {
    const res = await postCrateAction({ action: "play_all", playlist: pl, shuffle, play_now: playNow });
    if (res && res.ok) {
      if (typeof showToast === "function") showToast(`${shuffle ? "🔀 Shuffled" : "▶️ Queued"} ${res.data.enqueued_count} tracks from ${pl}!`, "❤️");
      if (typeof pollGuildState === "function") pollGuildState(getActiveGuildId());
    } else if (res && typeof showToast === "function") {
      showToast(res.data.error || "Playlist is empty", "⚠️");
    }
  } catch (e) { if (typeof showToast === "function") showToast("Failed to play crate", "❌"); }
};

setTimeout(() => { if (typeof window.loadCrate === "function") window.loadCrate("Favorites"); }, 1500);
setInterval(() => { syncSaveCrateButtonState(); }, 1500);
