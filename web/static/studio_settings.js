/* ==========================================================================
   Album Discovery Web Hub - Master Studio Settings & System Control Center
   ========================================================================== */

let studioConfigData = null;

async function loadStudioSettings() {
  const container = document.getElementById("studioSettingsContainer");
  if (!container) return;

  const guildId = typeof getActiveGuildId === "function" ? getActiveGuildId() : (window.currentGuildId || "1566871711058497716");

  try {
    const res = await fetch(`/api/system/settings?guild_id=${guildId}`);
    if (!res.ok) {
      container.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><div>Could not load studio settings.</div></div>`;
      return;
    }
    const data = await res.json();
    studioConfigData = data;
    renderStudioSettings(data);
  } catch (err) {
    container.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><div>Connection error: ${err.message}</div></div>`;
  }
}

function renderStudioSettings(data) {
  const container = document.getElementById("studioSettingsContainer");
  if (!container) return;

  const cfg = data.config || {};
  const sys = data.system || {};
  const guild = data.guild_settings || {};
  const chs = data.text_channels || [];

  const vol = Math.round((cfg.default_volume || 1.0) * 100);
  const idle = cfg.idle_disconnect_seconds !== undefined ? cfg.idle_disconnect_seconds : 300;
  const quality = guild.audio_quality || "auto";
  const boundCh = guild.bound_channel_id || "";
  const startupAuto = cfg.startup_autoplay !== false;
  const deck2 = cfg.deck2_enabled !== false;
  const deck3 = cfg.deck3_enabled !== false;

  container.innerHTML = `
    <!-- Top Overview Banner -->
    <div style="display:flex; align-items:center; justify-content:space-between; background:linear-gradient(135deg, rgba(168,85,247,0.12), rgba(56,189,248,0.08)); border:1px solid rgba(168,85,247,0.25); border-radius:var(--radius-md); padding:14px 18px; margin-bottom:12px;">
      <div style="display:flex; align-items:center; gap:12px;">
        <div style="font-size:1.8rem; background:rgba(168,85,247,0.2); width:44px; height:44px; display:flex; align-items:center; justify-content:center; border-radius:var(--radius-sm); border:1px solid rgba(168,85,247,0.4);">⚙️</div>
        <div>
          <div style="font-weight:800; font-size:1.05rem; color:#fff; letter-spacing:0.3px;">Master Studio Controls & System Station</div>
          <div style="font-size:0.75rem; color:var(--text-muted);">Real-time bot parameters, hardware diagnostics, and pipeline automation rules.</div>
        </div>
      </div>
      <button class="btn-small" onclick="loadStudioSettings()" style="display:flex; align-items:center; gap:5px;">🔄 Refresh Specs</button>
    </div>

    <!-- Main Settings Grid -->
    <div class="studio-settings-grid">

      <!-- Card 1: Audio Transmission & Bitrate Engine -->
      <div class="studio-settings-card">
        <div class="settings-card-header">
          <div>
            <div class="settings-card-title">🎛️ Audio Transmission & Bitrate</div>
            <div class="settings-card-subtitle">Master voice stream encoding parameters</div>
          </div>
          <span class="safety-badge" style="background:rgba(56,189,248,0.15); color:#38bdf8; border-color:rgba(56,189,248,0.3);">48kHz Opus Native</span>
        </div>

        <div class="settings-field">
          <div class="settings-field-row">
            <span class="settings-field-label">Target Transcode Bitrate</span>
            <span style="font-size:0.75rem; color:#38bdf8; font-family:monospace;" id="lblBitrateSetting">${quality.toUpperCase()}</span>
          </div>
          <div class="settings-pills-row">
            <button class="settings-pill-btn ${quality === 'auto' ? 'active' : ''}" onclick="applySetting('audio_quality', 'auto')">🌐 Auto (Best Available)</button>
            <button class="settings-pill-btn ${quality === '128k' ? 'active' : ''}" onclick="applySetting('audio_quality', '128k')">⚡ 128 kbps</button>
            <button class="settings-pill-btn ${quality === '192k' ? 'active' : ''}" onclick="applySetting('audio_quality', '192k')">📻 192 kbps (HQ)</button>
            <button class="settings-pill-btn ${quality === '320k' ? 'active' : ''}" onclick="applySetting('audio_quality', '320k')">💎 320 kbps (Lossless)</button>
          </div>
        </div>

        <div class="settings-field" style="margin-top:4px;">
          <div class="settings-field-row">
            <span class="settings-field-label">Default Playback Volume Scale</span>
            <span style="font-size:0.75rem; color:#4ade80; font-family:monospace;" id="lblDefaultVol">${vol}%</span>
          </div>
          <input type="range" class="volume-slider" min="10" max="100" value="${vol}" oninput="document.getElementById('lblDefaultVol').textContent=this.value+'%'" onchange="applySetting('default_volume', this.value / 100)" style="width:100%; margin-top:4px;" />
          <div class="settings-field-desc">Base volume scale when bot joins voice channels or plays songs.</div>
        </div>

        <div class="settings-field" style="margin-top:4px;">
          <div class="settings-field-row">
            <span class="settings-field-label">Inactivity Auto-Disconnect</span>
            <span style="font-size:0.75rem; color:var(--text-muted); font-family:monospace;">${idle > 0 ? (idle / 60) + ' min' : 'Never'}</span>
          </div>
          <div class="settings-pills-row">
            <button class="settings-pill-btn ${idle === 300 ? 'active' : ''}" onclick="applySetting('idle_disconnect_seconds', 300)">5 Minutes</button>
            <button class="settings-pill-btn ${idle === 600 ? 'active' : ''}" onclick="applySetting('idle_disconnect_seconds', 600)">10 Minutes</button>
            <button class="settings-pill-btn ${idle === 900 ? 'active' : ''}" onclick="applySetting('idle_disconnect_seconds', 900)">15 Minutes</button>
            <button class="settings-pill-btn ${idle === 0 ? 'active' : ''}" onclick="applySetting('idle_disconnect_seconds', 0)">♾️ Never (Persistent)</button>
          </div>
        </div>
      </div>

      <!-- Card 2: Triple-Deck Pipeline & Startup Automation -->
      <div class="studio-settings-card">
        <div class="settings-card-header">
          <div>
            <div class="settings-card-title">🚀 Pipeline Automation & Preloaders</div>
            <div class="settings-card-subtitle">Zero-gap chute and boot triggers</div>
          </div>
          <span class="safety-badge" style="background:rgba(34,197,94,0.15); color:#4ade80; border-color:rgba(34,197,94,0.3);">Pipeline Active</span>
        </div>

        <div class="settings-field">
          <div class="settings-field-row">
            <div>
              <div class="settings-field-label">🚀 Startup Auto-Play (Auto-Join on Boot)</div>
              <div class="settings-field-desc">Automatically connects to human listeners in voice on boot.</div>
            </div>
            <button class="btn-small" onclick="applySetting('startup_autoplay', ${!startupAuto})" style="color:${startupAuto ? '#4ade80' : '#94a3b8'};">
              ${startupAuto ? '✅ ON' : '⚪ OFF'}
            </button>
          </div>
        </div>

        <div class="settings-field" style="border-top:1px solid rgba(255,255,255,0.05); padding-top:8px;">
          <div class="settings-field-row">
            <div>
              <div class="settings-field-label">⚡ Deck 2 Standby Preloader</div>
              <div class="settings-field-desc">Pre-resolves stream tokens ahead of time for instant drops.</div>
            </div>
            <button class="btn-small" onclick="applySetting('deck2_enabled', ${!deck2})" style="color:${deck2 ? '#38bdf8' : '#94a3b8'};">
              ${deck2 ? '✅ READY' : '⚪ OFF'}
            </button>
          </div>
        </div>

        <div class="settings-field" style="border-top:1px solid rgba(255,255,255,0.05); padding-top:8px;">
          <div class="settings-field-row">
            <div>
              <div class="settings-field-label">🎛️ Deck 3 2-Step Lookahead Chute</div>
              <div class="settings-field-desc">Buffers metadata 2 songs ahead for double-skip immunity.</div>
            </div>
            <button class="btn-small" onclick="applySetting('deck3_enabled', ${!deck3})" style="color:${deck3 ? '#c084fc' : '#94a3b8'};">
              ${deck3 ? '✅ CUED' : '⚪ OFF'}
            </button>
          </div>
        </div>
      </div>

      <!-- Card 3: Live Discord Announcer & Broadcast Route -->
      <div class="studio-settings-card">
        <div class="settings-card-header">
          <div>
            <div class="settings-card-title">📢 Discord Announcer Broadcast Channel</div>
            <div class="settings-card-subtitle">Select where the interactive card lives</div>
          </div>
          <span class="safety-badge" style="background:rgba(168,85,247,0.15); color:#c084fc; border-color:rgba(168,85,247,0.3);">In-Place Edits</span>
        </div>

        <div class="settings-field">
          <div class="settings-field-label">Bound Output Channel</div>
          <select class="server-select" style="width:100%; padding:8px 10px; font-size:0.8rem; margin-top:4px;" onchange="applyChannelBinding(this.value)">
            <option value="">🔇 Silent (Dashboard Only — Zero Chat Spam)</option>
            ${chs.map(c => `
              <option value="${c.id}" ${c.id === boundCh ? 'selected' : ''}>${c.name}</option>
            `).join('')}
          </select>
          <div class="settings-field-desc" style="margin-top:4px;">
            The bot will maintain a single, interactive live player card with buttons in this channel, editing it in place whenever songs change.
          </div>
        </div>

        <div class="settings-field" style="border-top:1px solid rgba(255,255,255,0.05); padding-top:8px;">
          <div class="settings-field-row">
            <div>
              <div class="settings-field-label">🎶 Voice Channel Status Topic</div>
              <div class="settings-field-desc">Updates room header with real-time "🎶 Artist - Title".</div>
            </div>
            <span class="safety-badge" style="background:rgba(34,197,94,0.15); color:#4ade80; border-color:rgba(34,197,94,0.3);">🟢 Synced</span>
          </div>
        </div>
      </div>

      <!-- Card 4: Bot Hardware, Memory & Process Diagnostics -->
      <div class="studio-settings-card">
        <div class="settings-card-header">
          <div>
            <div class="settings-card-title">💻 Bot Hardware & Memory Diagnostics</div>
            <div class="settings-card-subtitle">Live system telemetry & resource utilization</div>
          </div>
          <span class="safety-badge" style="background:rgba(34,197,94,0.15); color:#4ade80; border-color:rgba(34,197,94,0.3);">Healthy</span>
        </div>

        <div class="sys-metrics-grid">
          <div class="sys-metric-box">
            <span class="sys-metric-label">Memory Allocation</span>
            <div class="sys-metric-val">${sys.ram_mb || 0} MB</div>
            <span class="sys-metric-sub">Resident Process RAM</span>
          </div>
          <div class="sys-metric-box">
            <span class="sys-metric-label">CPU Load</span>
            <div class="sys-metric-val">${sys.cpu_pct !== undefined ? sys.cpu_pct : 0}%</div>
            <span class="sys-metric-sub">Event Loop Utilization</span>
          </div>
          <div class="sys-metric-box">
            <span class="sys-metric-label">Studio Uptime</span>
            <div class="sys-metric-val">${sys.uptime_formatted || '0m'}</div>
            <span class="sys-metric-sub">Session Duration</span>
          </div>
          <div class="sys-metric-box">
            <span class="sys-metric-label">SQLite WAL</span>
            <div class="sys-metric-val">${sys.db_size_kb || 0} KB</div>
            <span class="sys-metric-sub">Persistent Storage</span>
          </div>
        </div>

        <div style="font-size:0.72rem; color:var(--text-muted); display:flex; justify-content:space-between; border-top:1px solid rgba(255,255,255,0.05); padding-top:8px;">
          <span>Host: <strong>${sys.host_os || 'Windows'}</strong></span>
          <span>Runtime: <strong>Python ${sys.python_version || '3.12'}</strong></span>
          <span>Discord.py: <strong>v${sys.discord_version || '2.3'}</strong></span>
        </div>
      </div>

      <!-- Card 5: Maintenance & Studio Tools -->
      <div class="studio-settings-card" style="grid-column: 1 / -1;">
        <div class="settings-card-header">
          <div>
            <div class="settings-card-title">🛠️ Studio Maintenance & Pipeline Tools</div>
            <div class="settings-card-subtitle">Cache flushing and diagnostics actions</div>
          </div>
        </div>

        <div style="display:flex; flex-wrap:wrap; gap:10px;">
          <button class="studio-action-btn" onclick="executeStudioAction('flush_cache')">
            🗑️ Flush Stream URL & API Cache
          </button>
          <button class="studio-action-btn" onclick="if(typeof switchTab==='function') switchTab('audiolab')">
            🎛️ Jump to Mastering Audio Lab
          </button>
          <button class="studio-action-btn" onclick="if(typeof switchTab==='function') switchTab('logs')">
            📜 View Real-Time Multi-Logs
          </button>
          <button class="studio-action-btn danger" onclick="executeStudioAction('clear_history')">
            🧹 Wipe Session Playback History
          </button>
        </div>
      </div>

    </div>
  `;
}

async function applySetting(key, val) {
  const guildId = typeof getActiveGuildId === "function" ? getActiveGuildId() : (window.currentGuildId || "1566871711058497716");
  try {
    const res = await fetch(`/api/system/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ guild_id: guildId, key: key, value: val })
    });
    if (res.ok) {
      if (typeof showToast === "function") {
        showToast(`⚙️ Saved: ${key.replace(/_/g, ' ')} -> ${val}`);
      }
      setTimeout(loadStudioSettings, 200);
    }
  } catch (err) {
    if (typeof showToast === "function") showToast("Error saving setting: " + err.message);
  }
}

async function applyChannelBinding(channelId) {
  if (typeof onAnnouncerChannelChange === "function") {
    await onAnnouncerChannelChange(channelId);
    setTimeout(loadStudioSettings, 300);
  }
}

async function executeStudioAction(action) {
  const guildId = typeof getActiveGuildId === "function" ? getActiveGuildId() : (window.currentGuildId || "1566871711058497716");
  try {
    const res = await fetch(`/api/system/action`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ guild_id: guildId, action: action })
    });
    if (res.ok) {
      const data = await res.json();
      if (typeof showToast === "function") showToast(data.message || `Action ${action} executed.`);
      setTimeout(loadStudioSettings, 300);
    }
  } catch (err) {
    if (typeof showToast === "function") showToast("Action failed: " + err.message);
  }
}

window.loadStudioSettings = loadStudioSettings;
window.applySetting = applySetting;
window.applyChannelBinding = applyChannelBinding;
window.executeStudioAction = executeStudioAction;
