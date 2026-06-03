"""
cf2/tools/debate_video_renderer.py — 3D Debate Silent Video Renderer
Migrated from: cf2/core/render/video_renderer_3d.py
Responsibility: Read clip frames, apply overlays, write silent .mp4.
No config loading, no TTS, no audio ops — pure frame rendering.
Multi-clip sequence support:
Each key has a ClipSequence:
{"paths": [(path, frames), ...], "loops": [(path, frames), ...]}
paths : played once each in order
loops : cycled indefinitely after all paths exhausted
frames: for images — hold for exactly N frames before advancing
Image support:
Any path ending in .jpg .jpeg .png .webp .bmp .tiff is treated as a
static image. Explicit "frames" value controls hold duration.
"""
import os
import cv2
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from PIL import Image
from cf2.tools import debate_timeline_builder as timeline_builder
from cf2.tools import debate_topic_overlay as topic_overlay
from cf2.tools import debate_subtitle_overlay as subtitle_overlay

TimelineEntry = Tuple[int, int, str]
MediaEntry = Tuple[Optional[str], Optional[int]]
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}
IMAGE_DEFAULT_HOLD = 90   # 3 seconds at 30fps

def _is_image(path: str) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTS

def _load_image_as_frame(path: str) -> Optional[np.ndarray]:
    """Load static image as BGR numpy array. Returns None on failure."""
    try:
        img = cv2.imread(path, cv2.IMREAD_COLOR)
        if img is None:
            pil_img = Image.open(path).convert("RGB")
            img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        return img
    except Exception:
        return None

def _apply_smart_crop_shorts(frame: np.ndarray, target_w: int, target_h: int) -> np.ndarray:
    """
    Safely converts any frame to 1080x1920 (Shorts) without stretching.
    Uses 'cover' scaling: zooms/crops to fill, adds blurred background for edges.
    Fixed broadcasting error by guaranteeing crop dimensions match target.
    """
    h, w, _ = frame.shape

    # 1. Calculate scale to COVER the entire target area
    scale = max(target_w / w, target_h / h)
    new_w = int(w * scale)
    new_h = int(h * scale)

    # 2. Resize to cover target
    resized = cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

    # 3. Center crop coordinates
    x = (new_w - target_w) // 2
    y = (new_h - target_h) // 2

    # 4. Extract sharp center
    crop = resized[y:y+target_h, x:x+target_w]

    # 5. Create blurred background (original aspect stretched to fit target)
    bg = cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)
    bg = cv2.GaussianBlur(bg, (51, 51), 0)

    # 6. Composite: sharp crop over blurred bg
    result = bg.copy()
    # Safe paste (handles edge cases where crop might be slightly off due to int math)
    ch, cw, _ = crop.shape
    if ch == target_h and cw == target_w:
        result[:] = crop
    else:
        py = max(0, (target_h - ch) // 2)
        px = max(0, (target_w - cw) // 2)
        result[py:py+ch, px:px+cw] = crop

    return result

class _MediaSource:
    """Wraps a single media source — video clip or static image."""
    def __init__(self, path: str, hold_frames: Optional[int] = None):
        self._path       = path
        self._is_img     = _is_image(path)
        self._exhausted  = False
        self._frame: Optional[np.ndarray] = None
        self._hold       = hold_frames if hold_frames is not None else IMAGE_DEFAULT_HOLD
        self._count      = 0
        self._cap: Optional[cv2.VideoCapture] = None

        if self._is_img:
            self._frame = _load_image_as_frame(path)
        else:
            cap = cv2.VideoCapture(path)
            if cap.isOpened():
                self._cap = cap

    @property
    def is_image(self) -> bool:
        return self._is_img

    def read(self) -> Tuple[bool, Optional[np.ndarray]]:
        if self._exhausted:
            return False, None

        if self._is_img:
            if self._frame is None:
                self._exhausted = True
                return False, None
            self._count += 1
            if self._count >= self._hold:
                self._exhausted = True
            return True, self._frame

        if self._cap is None:
            self._exhausted = True
            return False, None

        ret, frame = self._cap.read()
        if not ret:
            self._exhausted = True
            return False, None
        return True, frame

    def reset(self):
        self._exhausted = False
        self._count     = 0
        if not self._is_img and self._cap:
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    def release(self):
        if self._cap:
            self._cap.release()
            self._cap = None

class _SequencePlayer:
    """Plays a sequence of MediaEntry items."""
    def __init__(self, paths: List[MediaEntry], loops: List[MediaEntry],
                 tail: List[MediaEntry] = None, total_frames: int = 0):
        self._path_sources: List[_MediaSource]  = []
        self._loop_sources: List[_MediaSource] = []
        self._tail_sources: List[_MediaSource] = []

        for path, frames in paths:
            if path: self._path_sources.append(_MediaSource(path, frames))
        for path, frames in loops:
            if path: self._loop_sources.append(_MediaSource(path, frames))
        for path, frames in (tail or []):
            if path:  self._tail_sources.append(_MediaSource(path, frames))

        self._path_idx   = 0
        self._loop_idx   = 0
        self._tail_idx   = 0
        self._paths_done = len(self._path_sources) == 0
        self._tail_active = False
        self._total_frames = total_frames
        self._frame_count  = 0

        self._tail_budget = sum(
            (src._hold if src.is_image else self._get_video_frame_count(src._path))
            for src in self._tail_sources
        )

        if not self._loop_sources and self._path_sources:
            last = self._path_sources[-1]
            self._loop_sources.append(_MediaSource(last._path, last._hold if last.is_image else None))

    def _get_video_frame_count(self, path: str) -> int:
        cap = cv2.VideoCapture(path)
        if not cap.isOpened(): return 0
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        return count

    def _cur_path(self) -> Optional[_MediaSource]:
        return self._path_sources[self._path_idx] if self._path_idx < len(self._path_sources) else None

    def _cur_loop(self) -> Optional[_MediaSource]:
        return self._loop_sources[self._loop_idx % max(len(self._loop_sources), 1)] if self._loop_sources else None

    def _advance_path(self):
        self._path_idx += 1
        if self._path_idx >= len(self._path_sources):
            self._paths_done = True

    def _advance_loop(self):
        cur = self._cur_loop()
        if cur: cur.reset()
        self._loop_idx = (self._loop_idx + 1) % max(len(self._loop_sources), 1)

    def read(self) -> Optional[np.ndarray]:
        self._frame_count += 1
        frames_remaining = self._total_frames - self._frame_count

        if self._tail_sources and not self._tail_active:
            if frames_remaining <= self._tail_budget:
                self._tail_active = True

        if self._tail_active and self._tail_idx < len(self._tail_sources):
            src = self._tail_sources[self._tail_idx]
            ret, frame = src.read()
            if ret: return frame
            self._tail_idx += 1
            if self._tail_idx < len(self._tail_sources):
                return self.read()
            return None

        if not self._paths_done:
            src = self._cur_path()
            if src:
                ret, frame = src.read()
                if ret: return frame
                self._advance_path()
                if not self._paths_done:
                    return self.read()

        src = self._cur_loop()
        if src is None: return None

        ret, frame = src.read()
        if ret: return frame

        self._advance_loop()
        src = self._cur_loop()
        if src:
            ret, frame = src.read()
            if ret: return frame

        return None

    def release(self):
        for s in self._path_sources: s.release()
        for s in self._loop_sources: s.release()

def render(
    timeline: List[TimelineEntry],
    clip_map: Dict[str, Optional[str]],
    block_map: Dict[Tuple[str, str], str],
    subtitle_map: Dict[str, str],
    topic: str,
    fmt: str,
    fps: int,
    output_path: str,
    logger=print,
    loop_map: Optional[Dict[str, Optional[str]]] = None,
    clip_sequences: Optional[Dict[str, Dict]] = None,
) -> bool:
    """
    Render a silent video by reading clip frames and applying overlays.
    """
    if not timeline:
        logger("❌ Empty timeline — nothing to render.")
        return False

    width, height = (1080, 1920) if "Shorts" in fmt else (1920, 1080)
    total_f       = timeline[-1][1]
    is_shorts     = "Shorts" in fmt

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

    frames_by_key: Dict[str, int] = {}
    for start, end, key in timeline:
        frames_by_key[key] = frames_by_key.get(key, 0) + (end - start)

    players: Dict[str, _SequencePlayer] = {}
    if clip_sequences:
        for key, seq in clip_sequences.items():
            players[key] = _SequencePlayer(
                paths=seq.get("paths", []),
                loops=seq.get("loops", []),
                tail=seq.get("tail", []),
                total_frames=frames_by_key.get(key, 0),
            )
    else:
        loop_map = loop_map or {}
        for key, path in clip_map.items():
            paths = [(path, None)] if path else []
            loop  = loop_map.get(key)
            loops = [(loop, None)] if loop else []
            players[key] = _SequencePlayer(paths=paths, loops=loops)

    def _get_frame(key: str) -> Optional[np.ndarray]:
        player = players.get(key)
        return player.read() if player else None

    try:
        for f_idx in range(total_f):
            active_key = timeline_builder.lookup_key(timeline, f_idx)
            bg_frame = _get_frame(active_key) if active_key else None

            if bg_frame is None:
                bg_frame = np.zeros((height, width, 3), dtype=np.uint8)
                if active_key:
                    cv2.putText(bg_frame, f"Clip Missing: {active_key}",
                                (50, height // 2), cv2.FONT_HERSHEY_SIMPLEX,
                                1, (255, 255, 255), 2)

            # ✅ SMART CROP LOGIC: Replaces the stretching resize
            if bg_frame.shape[:2] != (height, width):
                if is_shorts:
                    # Apply smart crop with blurred background (Classroom pattern)
                    bg_frame = _apply_smart_crop_shorts(bg_frame, width, height)
                else:
                    # HD: simple resize is usually fine (both landscape)
                    bg_frame = cv2.resize(bg_frame, (width, height))

            pil_img = Image.fromarray(cv2.cvtColor(bg_frame, cv2.COLOR_BGR2RGB))
            pil_img = topic_overlay.draw(pil_img, topic, fmt, width, height)

            sub_text = subtitle_map.get(active_key, "") if active_key else ""
            if sub_text.strip():
                pil_img = subtitle_overlay.draw(pil_img, sub_text, fmt, width, height)

            writer.write(cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR))

            if (f_idx + 1) % 100 == 0:
                logger(f"  Rendering {(f_idx + 1) / total_f * 100:.1f}%")

        writer.release()
        for player in players.values():
            player.release()
        return os.path.exists(str(output_path))

    except Exception as e:
        writer.release()
        for player in players.values():
            player.release()
        logger(f"❌ Render error: {e}")
        import traceback
        traceback.print_exc()
        return False
