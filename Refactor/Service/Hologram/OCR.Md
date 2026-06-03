
The HD render will now show Ms. Layla-style panel (cyan border, filename header, progress bar) with your 2_Classes_Objects.mp4 auto-cropped inside it.

2. Screen OCR / code text
    From visible screen:
    code snippets
    output text
    menu labels
    terminal


    # 🎯 Hologram Type 2 - Screen OCR / Code Text Extraction Plan

    You're right - current system is just **video clipper + filter**. You need **real screen content extraction** that captures what's VISIBLE on screen (code, terminal, UI).

    ---

    ## 📐 Understanding the Difference

    | | Type 1 (Current) | Type 2 (Needed) |
    |---|---|---|
    | **Input** | Tutorial video (talking head) | Tutorial video (screen recording) |
    | **Extraction** | Audio-based (when speaking) | **Visual-based (what's on screen)** |
    | **Output** | Cropped video segments | **Screen content as hologram** |
    | **Use case** | "Watch teacher explain" | **"See the code/terminal floating"** |

    ---

    ## 🧠 Three Possible Approaches

    ### **Approach A: Screen Region Crop + Hologram Filter** ⭐ RECOMMENDED
    ```
    Tutorial Video → Detect screen region → Crop → Apply hologram effect → Output
    ```
    - Define screen area (manual or auto-detect dark region)
    - Crop just that region
    - Apply existing hologram filters (blue tint, vignette)
    - **Pros**: Simple, fast, preserves exact visuals
    - **Cons**: Need to define screen region

    ### **Approach B: OCR Extraction + Code Reconstruction**
    ```
    Tutorial Video → Frame extraction → OCR → Reconstruct code blocks → Hologram style
    ```
    - Extract frames from tutorial
    - Run OCR (Tesseract/EasyOCR) on screen region
    - Reconstruct as clean code/text with syntax highlighting
    - Apply hologram glow effect
    - **Pros**: Searchable, clean, resizable
    - **Cons**: Complex, OCR errors, loses visual fidelity

    ### **Approach C: Hybrid (Best of Both)**
    ```
    Tutorial Video → Screen crop → OCR on frames → Overlay detected code regions → Hologram filter
    ```
    - Crop screen region
    - OCR to detect where code/terminal/UI appears
    - Enhance with bounding boxes or highlights
    - Apply hologram styling
    - **Pros**: Best UX, interactive feel
    - **Cons**: Most complex

    ---

    ## 📋 Recommended Implementation Plan

    ### **Phase 1: Screen Region Detection + Crop** (Week 1-2)

    ```python
    # New config structure
    {
      "hologram": {
        "enabled": true,
        "type": 2,  # Screen OCR / Code Text
        "screen_region": {
          "mode": "auto",  # or "manual"
          "x": 100, "y": 100, "w": 1280, "h": 720  # if manual
        },
        "detection": {
          "method": "dark_region",  # Auto-detect code editor (dark bg)
          "threshold": 0.3,
          "min_area": 0.5  # 50% of frame
        }
      }
    }
    ```

    **Key additions to `hologram.py`**:

    ```python
    class ScreenDetector:
        """Detect screen/code region in tutorial video"""

        def detect_dark_region(self, frame: np.ndarray) -> tuple[int,int,int,int]:
            """
            Code editors/terminals are dark → find largest dark rectangle
            Returns (x, y, w, h)
            """
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            _, thresh = cv2.threshold(gray, 30, 255, cv2.THRESH_BINARY_INV)

            contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            largest = max(contours, key=cv2.contourArea)
            x, y, w, h = cv2.boundingRect(largest)

            # Expand slightly to include borders
            pad = 10
            return (max(0,x-pad), max(0,y-pad), w+2*pad, h+2*pad)

        def detect_by_edges(self, frame: np.ndarray) -> tuple[int,int,int,int]:
            """Detect screen by finding monitor bezel edges"""
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            lines = cv2.HoughLinesP(edges, 1, np.pi/180, 100)
            # Find rectangular contour → screen region
            ...
    ```

    **New method in HologramService**:

    ```python
    def _extract_screen_content(self, source: HologramSource, hologram_dir: Path) -> Path:
        """
        Type 2: Extract screen region from tutorial video
        Returns cropped screen content with hologram effect
        """
        screen_region = self._detect_screen_region(source.path)

        # Crop screen region
        cmd = [
            self.ffmpeg_bin, "-y",
            "-i", str(source.path),
            "-vf", f"crop={screen_region.w}:{screen_region.h}:{screen_region.x}:{screen_region.y}",
            "-c:v", "libx264", "-preset", "fast",
            str(hologram_dir / "screen_crop.mp4")
        ]
        subprocess.run(cmd, ...)

        # Apply hologram filter
        self._build_hologram_overlay(
            ClipEntry(..., filename="screen_crop.mp4", clip_type=ClipType.CODE),
            hologram_dir, self.default_mode
        )
    ```

    ---

    ### **Phase 2: OCR Enhancement** (Week 3-4)

    ```python
    class ScreenOCR:
        """Extract text from screen region for searchable holograms"""

        def extract_code_blocks(self, video_path: Path) -> list[dict]:
            """
            Sample frames → OCR → group into code blocks
            Returns [{"text": "print('hello')", "bbox": (x,y,w,h), "type": "code"}]
            """
            import easyocr
            reader = easyocr.Reader(['en'])

            frames = self._sample_frames(video_path, fps=1)  # 1 frame/sec
            blocks = []

            for frame_num, frame in enumerate(frames):
                # Crop to screen region first
                screen = self._crop_screen(frame)
                results = reader.readtext(screen)

                for (bbox, text, confidence) in results:
                    if confidence > 0.7:
                        blocks.append({
                            "frame": frame_num,
                            "text": text,
                            "bbox": bbox,
                            "type": self._classify_block(text)  # code/terminal/ui
                        })

            return self._group_into_segments(blocks)
    ```

    **Enhanced hologram with OCR overlay**:

    ```python
    def _build_hologram_with_ocr(self, clip: ClipEntry, hologram_dir: Path):
        """Render hologram + OCR bounding boxes"""
        # Get OCR data
        ocr_blocks = self.ocr_extractor.extract_code_blocks(clip.source_path)

        # Build FFmpeg filter with text overlays
        filter_parts = [self._mode_filter(self.default_mode)]

        for block in ocr_blocks:
            # Add glowing box around code
            filter_parts.append(
                f"drawbox=x={block.bbox[0]}:y={block.bbox[1]}:"
                f"w={block.bbox[2]}:h={block.bbox[3]}:"
                f"color=cyan@0.3:t=2"
            )

        filter_graph = ",".join(filter_parts)
        # ... apply filter
    ```

    ---

    ### **Phase 3: Smart Segmentation** (Week 5)

    Instead of fixed thirds, detect **content changes** on screen:

    ```python
    def _detect_content_changes(self, video_path: Path) -> list[tuple[float,float]]:
        """
        Detect when code/terminal content changes
        Returns [(start, end), ...] segments
        """
        frames = self._sample_frames(video_path, fps=2)

        segments = []
        last_hash = None
        segment_start = 0

        for i, frame in enumerate(frames):
            frame_hash = hashlib.md5(frame.tobytes()).hexdigest()

            if last_hash and frame_hash != last_hash:
                # Content changed → new segment
                segments.append((segment_start, i/2.0))
                segment_start = i/2.0

            last_hash = frame_hash

        return segments
    ```

    ---

    ## 📁 Updated Storage for Type 2

    ```
    .runtime/output/{TopicSlug}/_runtime_media/hologram/
    ├── manifest.json
    ├── screen_region.json       # ← NEW: detected screen coords
    ├── raw/                     # Original tutorial
    ├── screen_crop/             # ← NEW: cropped screen content
    ├── ocr/                     # ← NEW: extracted text blocks
    │   ├── code_blocks.json
    │   ├── terminal_output.json
    │   └── ui_labels.json
    ├── renders/
    │   ├── holo_screen_crop.mp4      # ← Main output
    │   ├── holo_code_only.mp4        # ← Code with glow
    │   └── holo_terminal.mp4         # ← Terminal with glow
    └── cache/
    ```

    ---

    ## 🔌 Updated Public API

    ```python
    # Type 1: Audio-based clips (existing)
    service.prepare("PythonBasics", {"type": 1, ...})

    # Type 2: Screen content extraction (NEW)
    service.prepare("PythonBasics", {
        "type": 2,
        "screen_region": {"mode": "auto"},  # or manual coords
        "ocr_enabled": true,                 # extract text too
        "segments": "auto"                   # detect content changes
    })

    # Resolve
    clip = service.resolve("PythonBasics", "screen_01", "code_block")
    # Returns: hologram/renders/holo_screen_crop.mp4
    ```

    ---

    ## ⚡ Quick Win: Start with Phase 1 Only

    If you want **fastest path to working Type 2**:

    1. **Add screen region config** (manual coordinates first)
    2. **Add `_crop_screen_region()` method** using FFmpeg crop filter
    3. **Reuse existing `_build_hologram_overlay()`** for styling
    4. **Done** - you have screen content as hologram

    Then add OCR later if needed.

    ---

    **Want me to implement Phase 1 (screen crop + hologram filter) right now?** I can modify `hologram.py` to add:
    - Screen region detection (auto + manual)
    - Screen crop extraction
    - Updated config schema for type 2

    Just say the word! 🚀

    You're absolutely right! The current implementation is just creating styled video clips with overlays, not actual holographic video content. Let me provide a comprehensive plan to transform this into a true hologram video generation system.

## Phase 1: Enhanced Hologram Types

**Type 1 (Enhanced): "Video-to-Hologram" Conversion**
- Convert existing tutorial videos into volumetric hologram format
- Extract depth information using AI/ML models
- Generate light field data for multi-angle viewing
- Create holographic encoding that can be projected in 3D space

**Type 2 (New): "Screen OCR Hologram"**
- Real-time screen content extraction during recording
- OCR processing of visible code, terminal output, menus
- Dynamic text overlay generation with holographic effects
- Synchronized audio-to-text transcription

## Phase 2: Core Hologram Technology Stack

**Depth Estimation Pipeline**
```python
# New DepthEstimationService
class DepthEstimationService:
    def estimate_depth(video_path: Path) -> np.ndarray:
        # Use pre-trained models (MiDaS, DPT, or custom)
        # Generate per-frame depth maps
        # Create point cloud data
        # Output depth metadata for hologram encoding
```

**Light Field Generation**
```python
# New LightFieldService
class LightFieldService:
    def generate_light_field(depth_maps: np.ndarray, video_frames: np.ndarray) -> LightField:
        # Convert depth + RGB to light field representation
        # Generate multiple viewing angles
        # Create holographic projection data
```

**Hologram Encoding**
```python
# New HologramEncoder
class HologramEncoder:
    def encode_to_hologram(video_path: Path, depth_data: np.ndarray) -> HologramFile:
        # Apply Fourier transform techniques
        # Generate interference patterns
        # Create wavefront encoding
        # Output .holo format for CF2 projection
```

## Phase 3: Screen OCR Enhancement

**Real-time Screen Analysis**
```python
# Enhanced OCR processing during recording
class ScreenHologramService:
    def process_screen_content(screen_capture: Image) -> HologramElements:
        # OCR code blocks, terminal output, menu labels
        # Extract text regions with bounding boxes
        # Generate dynamic holographic text overlays
        # Synchronize with audio transcript
```

**Multi-layer Hologram Composition**
```python
# Combine multiple data sources
def compose_holographic_video(
    base_video: Video,
    depth_data: DepthMap,
    screen_ocr: TextOverlay,
    audio_transcript: Transcript
) -> HologramVideo:
    # Layer depth information
    # Add floating text elements
    # Apply holographic shaders
    # Generate final 3D hologram output
```

## Phase 4: CF2 Integration

**Hologram Projection Service**
```python
# New HologramProjectionService
class HologramProjectionService:
    def project_hologram(hologram_file: HologramFile, position: Vector3) -> None:
        # Interface with CF2's 3D projection system
        # Handle spatial positioning
        # Manage multiple simultaneous holograms
        # Optimize for different CF2 unit capabilities
```

**Performance Optimization**
- Adaptive resolution based on viewing distance
- Progressive hologram loading
- Efficient compression for holographic data
- Real-time rendering optimization

## Implementation Strategy

**Phase 1 (Weeks 1-2)**:
- Research existing hologram generation libraries
- Set up depth estimation pipeline
- Create basic hologram encoding prototype

**Phase 2 (Weeks 3-4)**:
- Implement Screen OCR enhancement
- Build multi-layer composition system
- Test with sample tutorial videos

**Phase 3 (Weeks 5-6)**:
- Integrate with CF2 projection system
- Optimize performance and compression
- Create configuration interface for hologram types

**Phase 4 (Weeks 7-8)**:
- Comprehensive testing and validation
- Documentation and examples
- Performance benchmarking

## Technical Considerations

**Hardware Requirements**:
- GPU acceleration for depth estimation
- Sufficient RAM for light field processing
- Fast storage for large hologram files

**File Formats**:
- Develop .holo format specification
- Support for existing video formats as input
- Efficient compression algorithms

**Quality vs Performance**:
- Multiple quality presets
- Adaptive processing based on source material
- Real-time vs offline processing options

This plan transforms the current overlay system into a true holographic video generation platform that can create immersive 3D content from tutorial videos and screen recordings. Would you like me to elaborate on any specific aspect of this plan?



Here's exactly what changed and why it now makes a real hologram look:
_mode_filter — completely rebuilt as a 7-stage pipeline:
StageWhat it doesWhy1. Desaturatehue=s=0.08 strips the source colours down to near-greySo the tint is clean cyan, not muddied by original colours2. Cyan/blue tintcurves crushes the R channel, lifts G gently, lifts B stronglyGives the deep hologram blue-cyan cast3. Edge glowsplit → gblur(sigma=18) → blend=screenBright edges get a luminous halo — objects look like they're emitting light4. Scanlinesgeq formula burns a dark band every 4/6/8 rowsThe classic CRT/hologram horizontal stripe texture5. Shimmer/flickergeq with sin(freq*PI*T) per frameBrightness oscillates slightly — the unstable light of a real projection6. Vignettevignette=PI/3.2:eval=frameDarkens corners so the clip looks like it's floating in space7. Polisheq for final contrast/gamma/saturationPops the cyan and keeps it punchy
_build_hologram_overlay — switched from -vf to -filter_complex so the split/blend glow graph (which uses named pads [base] and [gblurred]) is handled correctly by FFmpeg.
Three modes now feel distinct:

FLOATING_SCREEN — densest scanlines (4px), strongest shimmer, hardest vignette
PROJECTOR — wider scanlines (6px), beam-shaped vignette, blue-violet tint
GLASS_PANEL — softest scanlines (8px), subtle shimmer, ice-blue frosted lookI'll analyze the attached image to understand the visual style and requirements, then search for relevant information about creating this hologram-style educational video interface.
Based on the uploaded image and your code files, I can see you want to create a **hologram-style educational video** with a futuristic sci-fi interface. The image shows:

- A dark background with cyan/teal UI elements
- A teacher avatar (Ms. Layla) on the left side
- A large hologram panel displaying code (Python `for` loop)
- Progress bar, REC indicator, and download button
- "HologramService active" status

Your existing codebase already has the infrastructure for this! Let me analyze what you have and what might need adjustment:

## What You Already Have (From Your Code)

### 1. **Hologram Service** (`hologram.py`)
Your `HologramService` class handles:
- **Type 2 (Screen OCR)**: Auto-detects IDE/terminal screens and crops them
- **7-stage sci-fi filter pipeline**: Desaturate → Cyan tint → Edge glow → Scanlines → Flicker/shimmer → Vignette → Polish
- FFmpeg-based rendering with fallback options

### 2. **Classroom Video Renderer** (`classroom_video_renderer.py`)
Already supports:
- Hologram overlay compositing via `_build_hologram_frame()`
- Position configs (`bottom_left`, `center_right`, `center_bottom` for Shorts)
- Scale, zoom, clip_speed, and animation controls
- Bubble overlays with 14 random shapes (geometric + animal)

### 3. **CTutor Configuration** (`ctutor.json`)
Configured for:
- Single teacher mode (`"classroom_mode": "single"`)
- Hologram enabled with `type: 2` (Screen OCR)
- Position: `center_right` (HD), `center_bottom` (Shorts)
- Scale: 52%, Zoom: 1.75x
- Animation: fade_in, slide_up

## Key Differences from Your Target Image

| Feature | Your Current Setup | Target Image |
|---------|-------------------|--------------|
| **Teacher position** | Not explicitly shown | Left side with circular avatar |
| **Hologram border** | Cyan border (`0x00e5ff`) | Rounded corners, glowing edge |
| **Progress bar** | Not implemented | Bottom of hologram panel |
| **REC indicator** | Not implemented | Top-right corner |
| **Topic label** | `drawtext` overlay | Clean UI badge |
| **Code styling** | Raw screen capture | Syntax highlighted, dark theme |

## To Match Your Target Image Exactly

Here are the specific modifications needed:

### 1. **Enhanced Hologram Panel Design**
Your current `_build_hologram_frame()` uses a simple cyan border. For the target look:

```python
# In classroom_video_renderer.py, modify the hologram filter chain:

# Add rounded corners and glow effect
holo_filter_parts.append(
    f"pad={holo_w}:{holo_h}:{border}:{border}:color=0x00e5ff,"
    f"format=rgba,"
    f"geq="
    f"a='if(between(X,{border},{holo_w-border})*between(Y,{border},{holo_h-border}),255,0)'"  # rounded corners mask
)

# Add outer glow via split/blend
glow_filter = (
    f"split[base][glw];"
    f"[glw]gblur=sigma=15,eq=brightness=0.3[glw2];"
    f"[glw2][base]blend=all_mode=screen:all_opacity=0.6"
)
```

### 2. **Add Progress Bar & REC Indicator**
Add to the FFmpeg filter chain in `_build_hologram_frame()`:

```python
# Progress bar (bottom of hologram)
progress_bar = (
    f",drawbox=x={holo_x}:y={holo_y+holo_h-8}:"
    f"w={holo_w}*t/{audio_dur}:h=6:color=0x00e5ff:t=fill"
)

# REC indicator (top-right)
rec_indicator = (
    f",drawtext=text='● REC':"
    f"fontcolor=red:fontsize=24:"
    f"x={holo_x+holo_w-80}:y={holo_y+10}:"
    f"enable='gte(t,0)'"
)
```

### 3. **Teacher Avatar Overlay**
You need to add a teacher avatar image overlay. In your config:

```json
"teacher_avatar": {
    "enabled": true,
    "image": "assets/avatars/ms_layla.png",
    "position": "left",
    "size": 120
}
```

Then in the video renderer, composite it:

```python
# Add teacher avatar overlay
if teacher_avatar_path:
    avatar_filter = (
        f"[avatar]scale=120:120,"
        f"format=rgba,"
        f"geq=a='if(sqrt((X-60)^2+(Y-60)^2)<55,255,0)'"  # circular mask
        f"[avatar_masked];"
        f"[base][avatar_masked]overlay=40:{h//2-60}[base2]"
    )
```

### 4. **Syntax Highlighting for Code**
Your `hologram.py` Type 2 (Screen OCR) extracts the screen region but doesn't apply syntax highlighting. For the target look, you have two options:

**Option A**: Pre-process the source video with syntax highlighting before feeding to HologramService

**Option B**: Add a post-processing step in `_build_hologram_overlay()`:

```python
# In hologram.py, add color curves for code syntax
syntax_tint = (
    f"curves="
    f"r='0 0 0.1 0.05 0.3 0.2 0.5 0.4 0.7 0.6 1 0.9':"
    f"g='0 0 0.1 0.1 0.3 0.35 0.5 0.55 0.7 0.75 1 0.95':"
    f"b='0 0 0.1 0.15 0.3 0.4 0.5 0.65 0.7 0.85 1 1.0'"
)
```

## Immediate Action Items

1. **Verify your source video** (`/home/matin/Desktop/2_Classes_Objects.mp4`) has the code content you want displayed
2. **Check hologram rendering** - run the pipeline and inspect `_hologram/renders/`
3. **Adjust zoom** - your config has `zoom: 1.75` which might crop too aggressively; try `1.0` first
4. **Add the missing UI elements** (progress bar, REC, avatar) to the video renderer

Would you like me to:
1. **Generate the specific FFmpeg filter chain** for the exact target look?
2. **Create a modified `classroom_video_renderer.py`** with the progress bar and REC indicator?
3. **Debug your current hologram rendering** to see why it might not match the target?

The core architecture is solid — you mainly need UI polish on the compositing layer.
