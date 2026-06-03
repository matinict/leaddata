"""
cf2/core/logging_setup.py — Logging configuration for the cf2 namespace.

Single entry point: `setup()`. Idempotent — safe to call more than once
(re-imports during dev or test won't duplicate handlers).

Output
──────
    stdout                        Always.
    .runtime/logs/cf2-{ts}.log    One file per run. Symlinked from cf2-latest.log.

Environment overrides
─────────────────────
    LOGLEVEL=DEBUG                Default INFO.
    CF2_LOG_FILE=/path/to.log     Override the per-run file path.
    CF2_LOG_FILE=-                Disable file logging entirely.

Called from
───────────
    cf2.flow_controller.run() — should be the FIRST thing it does, before
    any other cf2 module emits a log line.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(".runtime") / "logs"
NS = "cf2"  # the logger namespace this module owns
NOISY_LIBS = ("litellm", "httpx", "openai", "urllib3")

# Internal flag so setup() is idempotent
_CONFIGURED = False


def setup() -> Path | None:
    """
    Configure the cf2 namespace logger.

    Returns:
        Path of the log file in use, or None if file logging is disabled.
    """
    global _CONFIGURED

    level_name = os.environ.get("LOGLEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    log_path = _resolve_log_path()
    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    handlers: list[logging.Handler] = [_make_stream_handler(fmt)]
    if log_path is not None:
        fh = _make_file_handler(log_path, fmt)
        if fh is not None:
            handlers.append(fh)
            if log_path.parent == LOG_DIR:
                _update_latest_alias(log_path)

    cf2_logger = logging.getLogger(NS)
    cf2_logger.setLevel(level)
    cf2_logger.propagate = False  # don't double-print via root
    # Replace handlers (idempotent — re-running setup() doesn't accumulate)
    for h in list(cf2_logger.handlers):
        cf2_logger.removeHandler(h)
    for h in handlers:
        cf2_logger.addHandler(h)

    # Quiet down noisy third-party libs but keep their warnings visible.
    for noisy in NOISY_LIBS:
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True
    return log_path


def is_configured() -> bool:
    return _CONFIGURED


# ── Internals ────────────────────────────────────────────────────────────────

def _resolve_log_path() -> Path | None:
    override = os.environ.get("CF2_LOG_FILE")
    if override == "-":
        return None
    if override:
        return Path(override)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return LOG_DIR / f"cf2-{timestamp}.log"


def _make_stream_handler(fmt: logging.Formatter) -> logging.Handler:
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(fmt)
    return h


def _make_file_handler(
    log_path: Path, fmt: logging.Formatter,
) -> logging.Handler | None:
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        h = logging.FileHandler(log_path, mode="a", encoding="utf-8")
        h.setFormatter(fmt)
        return h
    except OSError as exc:
        sys.stderr.write(f"warning: could not open log file {log_path}: {exc}\n")
        return None


def _update_latest_alias(log_path: Path) -> None:
    """Maintain .runtime/logs/cf2-latest.log → newest log file."""
    alias = LOG_DIR / "cf2-latest.log"
    try:
        if alias.is_symlink() or alias.exists():
            alias.unlink()
        alias.symlink_to(log_path.name)  # relative target survives moves
    except (OSError, NotImplementedError):
        # Symlinks unsupported on this platform — alias is best-effort.
        pass
