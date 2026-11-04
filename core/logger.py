import logging
import os
import sys
from logging.handlers import RotatingFileHandler

# Windows Console UTF-8 Guardrail: Prevent charmap UnicodeEncodeErrors on emojis and international artist names
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGS_DIR = os.path.join(ROOT_DIR, "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

# Clean, purpose-split rotating log files
LOG_FILES = {
    "bot": os.path.join(LOGS_DIR, "bot.log"),
    "search": os.path.join(LOGS_DIR, "search.log"),
    "audio": os.path.join(LOGS_DIR, "audio.log"),
    "errors": os.path.join(LOGS_DIR, "errors.log"),
}

# File Formatter (full date for audit)
_FILE_FORMATTER = logging.Formatter(
    "%(asctime)s [%(levelname)-5s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Console Formatter (clean, simple timestamp)
_CONSOLE_FORMATTER = logging.Formatter(
    "[%(asctime)s] %(message)s",
    datefmt="%H:%M:%S"
)

def _setup_handler(filepath: str, level=logging.INFO):
    h = RotatingFileHandler(filepath, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    h.setFormatter(_FILE_FORMATTER)
    h.setLevel(level)
    return h

_bot_file_handler = _setup_handler(LOG_FILES["bot"], logging.INFO)
_search_file_handler = _setup_handler(LOG_FILES["search"], logging.INFO)
_audio_file_handler = _setup_handler(LOG_FILES["audio"], logging.INFO)
_errors_file_handler = _setup_handler(LOG_FILES["errors"], logging.WARNING)

_console_handler = logging.StreamHandler(sys.stdout)
_console_handler.setFormatter(_CONSOLE_FORMATTER)
_console_handler.setLevel(logging.INFO)

_configured_loggers = {}

def get_bot_logger(name: str = "bot") -> logging.Logger:
    clean_name = name.replace("cogs.", "").replace("core.", "").lower()
    if clean_name in _configured_loggers:
        return _configured_loggers[clean_name]

    logger = logging.getLogger(clean_name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # Route to dedicated purpose log file
    if clean_name in ("search", "discovery", "musicbrainz", "deezer", "taxonomy", "itunes"):
        logger.addHandler(_search_file_handler)
    elif clean_name in ("stream", "audio", "player", "voice"):
        logger.addHandler(_audio_file_handler)
    else:
        logger.addHandler(_bot_file_handler)

    # All warnings & errors mirror to errors.log for instant debugging
    logger.addHandler(_errors_file_handler)
    logger.addHandler(_console_handler)

    _configured_loggers[clean_name] = logger
    return logger

def configure_discord_logging():
    d_logger = logging.getLogger("discord")
    d_logger.setLevel(logging.WARNING)
    d_logger.propagate = False
    
    for h in list(d_logger.handlers):
        d_logger.removeHandler(h)
        
    d_logger.addHandler(_bot_file_handler)
    d_logger.addHandler(_errors_file_handler)

    logging.getLogger("discord.client").setLevel(logging.WARNING)
    logging.getLogger("discord.gateway").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

def get_logger(name: str = "app") -> logging.Logger:
    """Unified logger bridge for app services and discovery components."""
    return get_bot_logger(name)


def get_search_logger() -> logging.Logger:
    """Dedicated search and catalog discovery logger."""
    return get_bot_logger("discovery")

