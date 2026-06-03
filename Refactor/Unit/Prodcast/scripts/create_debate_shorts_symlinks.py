"""Utility script to ensure that all required Shorts (`*_s`) clip files exist.

The Debate video renderer expects Shorts versions of clips (e.g. ``p0fl_s.mkv``).
If a ``*_s`` file is missing the renderer falls back to the HD version, but in
some environments the fallback logic may not be triggered (e.g. when the path
resolution fails).  To guarantee that Shorts pipelines work we create symbolic
links from the missing ``*_s`` filenames to their existing non‑suffix counterparts.

The script walks ``assets/debate`` and for each ``.mkv`` or ``.png`` file:
  * If the filename already contains ``_s`` it is left untouched.
* If the ``*_s`` variant does **not** exist, a symlink ``<name>_s<ext>`` is
  created pointing to the original file.

Running this script is safe – it only creates links when the target file is
present and the link does not already exist.
"""

import os
from pathlib import Path


def _create_symlink(src: Path, dst: Path) -> None:
    """Create a symlink ``dst`` → ``src`` if it does not already exist.

    ``src`` must be an existing file. ``dst`` is created as a relative symlink
    (so the repository remains portable). If ``dst`` already exists we skip it.
    """
    if not src.exists():
        return
    if dst.exists():
        return
    # Use a relative path for the symlink target
    rel_target = os.path.relpath(src, dst.parent)
    try:
        dst.symlink_to(rel_target)
        print(f"Created symlink: {dst} → {src}")
    except OSError as exc:
        print(f"Failed to create symlink {dst}: {exc}")


def main() -> None:
    # Resolve the assets/debate directory relative to this script location
    assets_root = Path(__file__).resolve().parents[2] / "assets" / "debate"
    if not assets_root.is_dir():
        print(f"Assets directory not found: {assets_root}")
        return

    for folder in assets_root.iterdir():
        if not folder.is_dir():
            continue
        for file in folder.iterdir():
            if file.suffix.lower() not in {".mkv", ".png", ".jpg", ".jpeg"}:
                continue
            # Skip already a Shorts version
            if "_s" in file.stem:
                continue
            # Build the Shorts filename
            short_name = f"{file.stem}_s{file.suffix}"
            short_path = folder / short_name
            _create_symlink(file, short_path)


if __name__ == "__main__":
    main()
