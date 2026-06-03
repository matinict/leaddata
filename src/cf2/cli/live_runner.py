#cat > src/cf2/cli/live_runner.py << 'ENDOFFILE'
"""
cli/live_runner.py — Real-time split-pane execution dashboard
+ Auto-rotating completion slideshow (FBI/CIA monitor style)
+ CF2 360Ai watermark with cycling intelligence messages
"""
import subprocess
import threading
import time
import re
import json
import csv
import sys
import os
import select
import tty
import termios
from pathlib import Path
from collections import deque

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.live import Live
from rich.table import Table
from rich.text import Text
from rich.align import Align


console = Console()


# ── CF2 360Ai Watermark Messages ─────────────────────────────────────────────

WATERMARK_MESSAGES = [
    "▸ CF2 360Ai ▸ INTELLIGENCE PIPELINE ▸ CLASSIFIED ▸ EYES ONLY ▸",
    "▸ CF2 360Ai ▸ TARGET ACQUIRED ▸ DATA STREAM ACTIVE ▸",
    "▸ CF2 360Ai ▸ SURVEILLANCE MODE ▸ ALL SYSTEMS NOMINAL ▸",
    "▸ CF2 360Ai ▸ AUTO-COLLECT ENABLED ▸ THREAT LEVEL: LOW ▸",
    "▸ CF2 360Ai ▸ PROFILE ACTIVE ▸ SECURE CHANNEL ▸",
    "▸ CF2 360Ai ▸ INTEL HARVEST COMPLETE ▸ STAND BY ▸",
    "▸ CF2 360Ai ▸ ENCRYPTED FEED ▸ AUTHENTICATED ▸",
    "▸ CF2 360Ai ▸ DEEP SCAN ACTIVE ▸ NO ANOMALIES ▸",
]


def _get_watermark() -> str:
    """Get current watermark message based on time."""
    idx = int(time.time() / 3) % len(WATERMARK_MESSAGES)
    return WATERMARK_MESSAGES[idx]


# ── Utility Functions ────────────────────────────────────────────────────────

def _project_root() -> Path:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "src" / "cf2").is_dir():
            return parent
    return Path.cwd()


def _format_size(bytes_size: int) -> str:
    if bytes_size < 1024:
        return f"{bytes_size} B"
    if bytes_size < 1024 * 1024:
        return f"{bytes_size / 1024:.1f} KB"
    return f"{bytes_size / (1024 * 1024):.1f} MB"


def _find_workspace_from_log(log_lines: list):
    for line in log_lines:
        m = re.search(r"Workspace\s*:\s*(\S+)", line)
        if m:
            return Path(m.group(1))
    return None


def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])", "", text)


# ── Raw Terminal Mode ────────────────────────────────────────────────────────

_old_term_settings = None


def _enable_raw_mode():
    global _old_term_settings
    if sys.stdin.isatty():
        _old_term_settings = termios.tcgetattr(sys.stdin.fileno())
        tty.setcbreak(sys.stdin.fileno())


def _disable_raw_mode():
    global _old_term_settings
    if _old_term_settings is not None and sys.stdin.isatty():
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _old_term_settings)
        _old_term_settings = None


def _check_key_pressed(timeout: float = 0.1) -> str:
    """Non-blocking key check with raw terminal mode. Returns key or empty string."""
    if not sys.stdin.isatty():
        return ""
    try:
        if select.select([sys.stdin], [], [], timeout)[0]:
            b = os.read(sys.stdin.fileno(), 8)
            # Skip ANSI escape sequences (arrow keys, etc.)
            if b and b[0] == 0x1b:
                return ""
            return b.decode("utf-8", errors="ignore").lower() if b else ""
    except Exception:
        pass
    return ""


# ── Live Execution Dashboard ─────────────────────────────────────────────────

def run_with_dashboard(cmd: str, title: str = "CF2 Pipeline"):
    """
    Run command and display live split-pane dashboard:
    - Left: execution log (last 25 lines)
    - Right: live output files in workspace
    + CF2 360Ai watermark
    """
    root = _project_root()

    log_buffer = deque(maxlen=30)
    workspace = [None]
    start_time = time.time()
    process_done = [False]
    exit_code = [None]

    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="watermark", size=2),
        Layout(name="body"),
        Layout(name="footer", size=3),
    )
    layout["body"].split_row(
        Layout(name="log"),
        Layout(name="files"),
    )

    def build_header():
        elapsed = int(time.time() - start_time)
        mm, ss = divmod(elapsed, 60)
        hh, mm = divmod(mm, 60)
        status = "🔴 RUNNING" if not process_done[0] else (
            "✅ DONE" if exit_code[0] == 0 else "❌ FAILED"
        )
        return Panel(
            f"[bold cyan]🎬 {title}[/bold cyan]  │  "
            f"{status}  │  "
            f"⏱️  {hh:02d}:{mm:02d}:{ss:02d}",
            border_style="cyan",
        )

    def build_watermark():
        return Align.center(
            Text(_get_watermark(), style="dim red blink")
        )

    def build_log_panel():
        text = Text()
        for line in list(log_buffer)[-25:]:
            clean = _strip_ansi(line.rstrip())
            if "✅" in clean or "done" in clean.lower():
                text.append(clean + "\n", style="green")
            elif "❌" in clean or "fail" in clean.lower() or "error" in clean.lower():
                text.append(clean + "\n", style="red")
            elif "⚠️" in clean or "warn" in clean.lower():
                text.append(clean + "\n", style="yellow")
            elif "🚀" in clean or "running" in clean.lower():
                text.append(clean + "\n", style="cyan")
            else:
                text.append(clean + "\n")
        return Panel(text, title="📜 EXECUTION LOG", border_style="blue")

    def build_files_panel():
        ws = workspace[0]
        if not ws or not ws.exists():
            return Panel(
                "[dim]Waiting for workspace...[/dim]",
                title="📁 OUTPUT FILES",
                border_style="magenta",
            )

        table = Table(show_header=True, header_style="bold magenta", expand=True)
        table.add_column("File", overflow="fold")
        table.add_column("Size", justify="right", width=10)
        table.add_column("Modified", justify="right", width=8)

        files = sorted(
            ws.rglob("*"),
            key=lambda p: p.stat().st_mtime if p.is_file() else 0,
            reverse=True,
        )

        count = 0
        for f in files:
            if not f.is_file():
                continue
            if count >= 20:
                break

            rel = f.relative_to(ws)
            size = _format_size(f.stat().st_size)

            mtime = time.time() - f.stat().st_mtime
            if mtime < 5:
                age = "[green]now[/green]"
            elif mtime < 60:
                age = f"{int(mtime)}s"
            else:
                age = f"{int(mtime / 60)}m"

            icon = {
                ".csv":  "📊",
                ".json": "📋",
                ".txt":  "📄",
                ".mp3":  "🎵",
                ".wav":  "🎵",
                ".mp4":  "🎬",
                ".jpg":  "🖼️",
                ".png":  "🖼️",
            }.get(f.suffix.lower(), "📁")

            table.add_row(f"{icon} {rel}", size, age)
            count += 1

        if count == 0:
            return Panel(
                f"[dim]Workspace: {ws.name}\n(no files yet)[/dim]",
                title="📁 OUTPUT FILES",
                border_style="magenta",
            )

        return Panel(
            table,
            title=f"📁 {ws.name}  ({count} files)",
            border_style="magenta",
        )

    def build_footer():
        ws = workspace[0]
        ws_str = str(ws) if ws else "(detecting...)"
        return Panel(
            f"[dim]Workspace: {ws_str}[/dim]\n"
            f"[dim]Command: {cmd}[/dim]",
            border_style="dim",
        )

    def update_layout():
        layout["header"].update(build_header())
        layout["watermark"].update(build_watermark())
        layout["log"].update(build_log_panel())
        layout["files"].update(build_files_panel())
        layout["footer"].update(build_footer())

    def run_process():
        proc = subprocess.Popen(
            cmd,
            cwd=root,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        for line in iter(proc.stdout.readline, ""):
            log_buffer.append(line)

            if workspace[0] is None:
                ws = _find_workspace_from_log([line])
                if ws and ws.exists():
                    workspace[0] = ws

        proc.wait()
        exit_code[0] = proc.returncode
        process_done[0] = True

    thread = threading.Thread(target=run_process, daemon=True)
    thread.start()

    _enable_raw_mode()
    try:
        with Live(layout, refresh_per_second=2, screen=True):
            try:
                while not process_done[0]:
                    update_layout()
                    time.sleep(0.5)
                update_layout()
                time.sleep(1)
            except KeyboardInterrupt:
                console.print("[yellow]Interrupted![/yellow]")
    finally:
        _disable_raw_mode()

    elapsed = int(time.time() - start_time)

    # Show FBI-style completion dashboard with auto-rotating slideshow
    _completion_dashboard(
        workspace[0],
        exit_code[0],
        elapsed,
        title,
    )


# ── Stats Parser ─────────────────────────────────────────────────────────────

def _parse_stats(workspace: Path) -> tuple:
    """Parse stats and top leads from workspace files."""
    stats = {
        "total_leads":      0,
        "hot":              0,
        "warm":             0,
        "cold":             0,
        "avg_score":        0.0,
        "phone_coverage":   0,
        "email_coverage":   0,
        "website_coverage": 0,
    }
    top_leads = []

    files = sorted(workspace.rglob("*"))
    files = [f for f in files if f.is_file()]

    scored_csv = None
    for f in files:
        if "scored" in str(f) and f.suffix == ".csv":
            scored_csv = f
            break

    if scored_csv:
        try:
            with open(scored_csv, "r", encoding="utf-8") as fp:
                reader = csv.DictReader(fp)
                rows = list(reader)

                stats["total_leads"] = len(rows)
                scores = []
                phone_count = email_count = website_count = 0

                for row in rows:
                    seg = (row.get("segment") or "").lower()
                    if seg == "hot":
                        stats["hot"] += 1
                    elif seg == "warm":
                        stats["warm"] += 1
                    elif seg == "cold":
                        stats["cold"] += 1

                    try:
                        scores.append(float(row.get("score", 0)))
                    except (ValueError, TypeError):
                        pass

                    if row.get("phone") or row.get("phone_formatted"):
                        phone_count += 1
                    if row.get("email"):
                        email_count += 1
                    if row.get("website"):
                        website_count += 1

                if scores:
                    stats["avg_score"] = sum(scores) / len(scores)
                if rows:
                    stats["phone_coverage"] = int(phone_count * 100 / len(rows))
                    stats["email_coverage"] = int(email_count * 100 / len(rows))
                    stats["website_coverage"] = int(website_count * 100 / len(rows))

                rows_sorted = sorted(
                    rows,
                    key=lambda r: float(r.get("score", 0) or 0),
                    reverse=True,
                )
                for r in rows_sorted[:5]:
                    top_leads.append({
                        "name":    (r.get("name") or "")[:30],
                        "rating":  r.get("rating") or "—",
                        "reviews": r.get("reviews") or r.get("review_count") or "—",
                    })
        except Exception:
            pass

    return stats, top_leads, files


# ── Overview Slide ───────────────────────────────────────────────────────────

def _build_overview_layout(workspace, exit_code, elapsed, title, stats, top_leads, files):
    """Build the overview dashboard layout with CF2 360Ai watermark."""
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="watermark", size=2),
        Layout(name="body"),
        Layout(name="files", size=10),
        Layout(name="actions", size=3),
    )
    layout["body"].split_row(
        Layout(name="stats"),
        Layout(name="top"),
    )

    # Header
    status = "✅ COMPLETE" if exit_code == 0 else "❌ FAILED"
    style = "green" if exit_code == 0 else "red"
    mm, ss = divmod(elapsed, 60)
    hh, mm = divmod(mm, 60)
    layout["header"].update(Panel(
        f"[bold cyan]🎬 {title}[/bold cyan]  │  "
        f"[bold {style}]{status}[/bold {style}]  │  "
        f"⏱️  {hh:02d}:{mm:02d}:{ss:02d}",
        border_style=style,
    ))

    # Watermark
    layout["watermark"].update(Align.center(
        Text(_get_watermark(), style="dim red blink")
    ))

    # Stats
    stats_table = Table.grid(padding=(0, 2))
    stats_table.add_column(style="cyan", justify="right")
    stats_table.add_column(style="bold white")
    stats_table.add_row("Total Leads:", str(stats["total_leads"]))
    stats_table.add_row("🔥 Hot:", f"[red]{stats['hot']}[/red]")
    stats_table.add_row("🔶 Warm:", f"[yellow]{stats['warm']}[/yellow]")
    stats_table.add_row("❄️  Cold:", f"[blue]{stats['cold']}[/blue]")
    stats_table.add_row("Avg Score:", f"{stats['avg_score']:.1f}")
    stats_table.add_row("", "")
    stats_table.add_row("📞 Phone:", f"{stats['phone_coverage']}%")
    stats_table.add_row("✉️  Email:", f"{stats['email_coverage']}%")
    stats_table.add_row("🌐 Website:", f"{stats['website_coverage']}%")

    layout["stats"].update(Panel(
        stats_table, title="📊 STATS", border_style="cyan",
    ))

    # Top leads
    if top_leads:
        top_table = Table(show_header=True, header_style="bold magenta", expand=True)
        top_table.add_column("#", width=3)
        top_table.add_column("Name", overflow="fold")
        top_table.add_column("⭐", width=4)
        top_table.add_column("Reviews", width=8)

        for i, lead in enumerate(top_leads, 1):
            top_table.add_row(
                str(i), lead["name"], str(lead["rating"]), str(lead["reviews"]),
            )

        layout["top"].update(Panel(
            top_table, title="🔥 TOP LEADS", border_style="magenta",
        ))
    else:
        layout["top"].update(Panel(
            "[dim]No lead data[/dim]", title="🔥 TOP LEADS", border_style="magenta",
        ))

    # Files
    files_table = Table(show_header=True, header_style="bold yellow", expand=True)
    files_table.add_column("File", overflow="fold")
    files_table.add_column("Size", justify="right", width=10)
    files_table.add_column("Records", justify="right", width=10)

    for f in files[:8]:
        rel = f.relative_to(workspace)
        size = _format_size(f.stat().st_size)

        records = "—"
        try:
            if f.suffix == ".csv":
                with open(f, "r", encoding="utf-8") as fp:
                    records = str(sum(1 for _ in fp) - 1)
            elif f.suffix == ".json":
                content = json.loads(f.read_text(encoding="utf-8", errors="ignore"))
                if isinstance(content, list):
                    records = str(len(content))
        except Exception:
            pass

        icon = {
            ".csv":  "📊",
            ".json": "📋",
            ".txt":  "📄",
            ".mp3":  "🎵",
            ".wav":  "🎵",
            ".mp4":  "🎬",
        }.get(f.suffix, "📁")

        files_table.add_row(f"{icon} {rel}", size, records)

    if len(files) > 8:
        files_table.add_row(f"[dim]... +{len(files) - 8} more[/dim]", "", "")

    layout["files"].update(Panel(
        files_table,
        title=f"📁 FILES GENERATED ({len(files)})",
        border_style="yellow",
    ))

    # Actions
    layout["actions"].update(Panel(
        "[bold green]ENTER[/bold green] menu  │  "
        "[bold cyan]o[/bold cyan] open folder  │  "
        "[bold yellow]v#[/bold yellow] view file  │  "
        "[bold magenta]p[/bold magenta] pause  │  "
        "[bold red]q[/bold red] quit",
        border_style="dim",
    ))

    return layout


# ── File View Slide ──────────────────────────────────────────────────────────

def _build_file_view_layout(workspace, file: Path, exit_code, elapsed, title, slide_num, total_slides):
    """Build layout showing single file content with CF2 360Ai watermark."""
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=3),
        Layout(name="watermark", size=2),
        Layout(name="info", size=4),
        Layout(name="content"),
        Layout(name="actions", size=3),
    )

    status = "✅ COMPLETE" if exit_code == 0 else "❌ FAILED"
    style = "green" if exit_code == 0 else "red"

    layout["header"].update(Panel(
        f"[bold cyan]🎬 {title}[/bold cyan]  │  "
        f"[bold {style}]{status}[/bold {style}]  │  "
        f"[bold yellow]Slide {slide_num}/{total_slides}[/bold yellow]",
        border_style=style,
    ))

    # Watermark
    layout["watermark"].update(Align.center(
        Text(_get_watermark(), style="dim red blink")
    ))

    rel = file.relative_to(workspace)
    size = _format_size(file.stat().st_size)

    info_table = Table.grid(padding=(0, 2))
    info_table.add_column(style="cyan")
    info_table.add_column(style="bold white")
    info_table.add_row("📄 File:", str(rel))
    info_table.add_row("📊 Size:", size)
    info_table.add_row("🗂️  Type:", file.suffix.upper().lstrip("."))

    layout["info"].update(Panel(
        info_table, title="📋 FILE INFO", border_style="cyan",
    ))

    # Content panel
    try:
        if file.suffix == ".csv":
            content_table = Table(show_header=True, header_style="bold yellow", expand=True)
            with open(file, "r", encoding="utf-8") as fp:
                reader = csv.reader(fp)
                rows = list(reader)

                if rows:
                    headers = rows[0][:6]
                    for h in headers:
                        content_table.add_column(h[:20], overflow="fold")

                    for row in rows[1:16]:
                        content_table.add_row(*[str(c)[:25] for c in row[:6]])

            layout["content"].update(Panel(
                content_table,
                title="📊 CSV PREVIEW (first 15 rows)",
                border_style="green",
            ))

        elif file.suffix == ".json":
            try:
                data = json.loads(file.read_text(encoding="utf-8", errors="ignore"))
                preview = json.dumps(data, indent=2, ensure_ascii=False)[:2000]
                if len(json.dumps(data)) > 2000:
                    preview += "\n\n... (truncated)"
                layout["content"].update(Panel(
                    Text(preview, style="white"),
                    title="📋 JSON PREVIEW",
                    border_style="green",
                ))
            except Exception:
                content = file.read_text(encoding="utf-8", errors="ignore")[:2000]
                layout["content"].update(Panel(
                    Text(content),
                    title="📋 RAW CONTENT",
                    border_style="green",
                ))
        else:
            content = file.read_text(encoding="utf-8", errors="ignore")[:2000]
            layout["content"].update(Panel(
                Text(content),
                title="📄 TEXT PREVIEW",
                border_style="green",
            ))
    except Exception as e:
        layout["content"].update(Panel(
            f"[red]Cannot preview: {e}[/red]",
            border_style="red",
        ))

    layout["actions"].update(Panel(
        "[bold green]ENTER[/bold green] menu  │  "
        "[bold cyan]o[/bold cyan] open folder  │  "
        "[bold magenta]p[/bold magenta] pause  │  "
        "[bold yellow]n[/bold yellow] next  │  "
        "[bold red]q[/bold red] quit",
        border_style="dim",
    ))

    return layout


# ── Completion Dashboard ─────────────────────────────────────────────────────

def _completion_dashboard(workspace: Path, exit_code: int, elapsed: int, title: str):
    """
    FBI-style auto-rotating completion dashboard.
    Cycles through: Overview → File 1 → File 2 → ... → Overview
    User can pause, navigate, or exit anytime.
    """
    if not workspace or not workspace.exists():
        return

    stats, top_leads, files = _parse_stats(workspace)

    if not files:
        console.print(f"\n[yellow]No files generated in {workspace}[/yellow]")
        try:
            input("\n  Press ENTER to return... ")
        except (KeyboardInterrupt, EOFError):
            pass
        return

    # Slide configuration
    SLIDE_DURATION = 5.0  # seconds per slide
    total_slides = 1 + len(files)  # overview + each file

    slide_index = 0
    paused = [False]
    last_change = time.time()

    def get_current_layout():
        if slide_index == 0:
            return _build_overview_layout(
                workspace, exit_code, elapsed, title,
                stats, top_leads, files,
            )
        else:
            file = files[slide_index - 1]
            return _build_file_view_layout(
                workspace, file, exit_code, elapsed, title,
                slide_index + 1, total_slides,
            )

    try:
        _enable_raw_mode()
        with Live(get_current_layout(), refresh_per_second=4, screen=True) as live:
            while True:
                live.update(get_current_layout())

                key = _check_key_pressed(timeout=0.25)

                if key:
                    if key in {"", "\r", "\n", "q", "quit", "exit"}:
                        break

                    if key == "p":
                        paused[0] = not paused[0]
                        continue

                    if key == "n":
                        slide_index = (slide_index + 1) % total_slides
                        last_change = time.time()
                        continue

                    if key == "o":
                        subprocess.run(
                            ["xdg-open", str(workspace)],
                            capture_output=True,
                        )
                        continue

                    view_match = re.match(r"^v(\d+)$", key)
                    if view_match:
                        idx = int(view_match.group(1))
                        if 1 <= idx <= len(files):
                            slide_index = idx
                            last_change = time.time()
                            paused[0] = True
                        continue

                # Auto-rotate
                if not paused[0]:
                    if time.time() - last_change >= SLIDE_DURATION:
                        slide_index = (slide_index + 1) % total_slides
                        last_change = time.time()

    except KeyboardInterrupt:
        pass
    finally:
        _disable_raw_mode()

    console.print()
    console.print(f"[dim]Workspace: {workspace}[/dim]")
#ENDOFFILE
