/* ==========================================================================
   Album Discovery Web Hub - Channel Announcer Manager
   Binds a dedicated text channel for live interactive Discord player cards
   ========================================================================== */

let currentBoundChannelId = null;

async function loadChannelAnnouncer() {
  const guildId = typeof getActiveGuildId === "function" ? getActiveGuildId() : "1566871711058497716";
  const select = document.getElementById("announcerChannelSelect");
  if (!select) return;

  try {
    const res = await fetch(`/api/guild/${guildId}/channel`);
    if (!res.ok) return;
    const data = await res.json();

    currentBoundChannelId = data.bound_channel_id || "";
    
    // Populate dropdown
    select.innerHTML = '<option value="">🔇 Silent (Zero Chat Spam)</option>';
    if (data.text_channels && Array.isArray(data.text_channels)) {
      data.text_channels.forEach(ch => {
        const opt = document.createElement("option");
        opt.value = ch.id;
        opt.textContent = ch.name;
        if (ch.id === currentBoundChannelId) {
          opt.selected = true;
        }
        select.appendChild(opt);
      });
    }

    if (currentBoundChannelId) {
      select.style.borderColor = "#38bdf8";
      select.style.color = "#38bdf8";
    } else {
      select.style.borderColor = "rgba(255,255,255,0.15)";
      select.style.color = "var(--text-muted)";
    }
  } catch (err) {
    console.debug("Channel announcer sync:", err.message);
  }
}

async function onAnnouncerChannelChange(channelId) {
  const guildId = typeof getActiveGuildId === "function" ? getActiveGuildId() : "1566871711058497716";
  const select = document.getElementById("announcerChannelSelect");
  try {
    const res = await fetch(`/api/guild/${guildId}/channel`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ channel_id: channelId || null })
    });
    if (res.ok) {
      const data = await res.json();
      currentBoundChannelId = data.bound_channel_id || "";
      if (select) {
        if (currentBoundChannelId) {
          select.style.borderColor = "#38bdf8";
          select.style.color = "#38bdf8";
        } else {
          select.style.borderColor = "rgba(255,255,255,0.15)";
          select.style.color = "var(--text-muted)";
        }
      }
      if (typeof showToast === "function") {
        if (data.bound_channel_name) {
          showToast(`📢 Live player card bound to #${data.bound_channel_name}!`);
        } else {
          showToast("🔇 Discord text chat set to Silent & Clean.");
        }
      }
    }
  } catch (err) {
    if (typeof showToast === "function") {
      showToast("Failed to update channel binding: " + err.message);
    }
  }
}

window.loadChannelAnnouncer = loadChannelAnnouncer;
window.onAnnouncerChannelChange = onAnnouncerChannelChange;

// Auto-sync on page load and server changes
document.addEventListener("DOMContentLoaded", () => {
  setTimeout(loadChannelAnnouncer, 600);
});
