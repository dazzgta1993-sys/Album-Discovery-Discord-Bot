import json
import os
from dotenv import load_dotenv

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT_DIR, ".env"))

CONFIG_PATH = os.path.join(ROOT_DIR, "config.json")

def load_bot_config() -> dict:
    defaults = {
        "command_prefix": "!",
        "default_volume": 1.0,
        "idle_disconnect_seconds": 300,
        "autoplay_dj": True,
        "startup_autoplay": True,
        "embed_color": "9d4edd",
        "max_queue_display": 10,
        "web_enabled": True,
        "web_host": "127.0.0.1",
        "web_port": 8905
    }
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
                defaults.update(data)
        except Exception:
            pass
    return defaults

def save_bot_config(updates: dict) -> bool:
    """Save/update configuration keys in config.json."""
    if not isinstance(updates, dict) or not updates:
        return False
    current = load_bot_config()
    current.update(updates)
    try:
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)
        return True
    except Exception:
        return False

_cfg = load_bot_config()
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "").strip()
COMMAND_PREFIX = _cfg.get("command_prefix", "!")
DEFAULT_VOLUME = float(_cfg.get("default_volume", 1.0))
IDLE_DISCONNECT_SECONDS = int(_cfg.get("idle_disconnect_seconds", 300))
AUTOPLAY_DJ = bool(_cfg.get("autoplay_dj", True))
STARTUP_AUTOPLAY = bool(_cfg.get("startup_autoplay", True))
EMBED_COLOR = int(_cfg.get("embed_color", "9d4edd"), 16)
MAX_QUEUE_DISPLAY = int(_cfg.get("max_queue_display", 10))
WEB_ENABLED = bool(_cfg.get("web_enabled", True))
WEB_HOST = os.getenv("WEB_HOST", _cfg.get("web_host", "127.0.0.1"))
WEB_PORT = int(os.getenv("WEB_PORT", _cfg.get("web_port", 8905)))
