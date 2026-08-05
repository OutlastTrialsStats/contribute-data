"""Builds icon.ico from tools/icon-source.png.

An .ico holds independent images, and the frames here deliberately are not the same picture.
Below 32 pixels the badge does not survive: an opaque square among transparent icons, and
hairlines that dissolve into grey. Those sizes get the monogram alone, cut out. From 48 up the
badge stays as it is.

    python tools/make_icon.py [--preview]

--preview also writes tools/icon-preview.png, every frame magnified without smoothing.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "tools" / "icon-source.png"
TARGET = ROOT / "icon.ico"
PREVIEW = ROOT / "tools" / "icon-preview.png"

# The tray never asks for more than 32: 16 at 100% scaling, 24 at 150%, 32 at 200%.
GLYPH_SIZES = (16, 20, 24, 32)
# Explorer, the desktop and Alt-Tab, where the badge has room to work.
BADGE_SIZES = (48, 64, 256)

# Luminance below the first is background, above the second is monogram, between is the edge.
CUTOFF_LOW = 90
CUTOFF_HIGH = 170

# The artwork's brightest pixel. Painting it on flat removes the photographic grain, which
# would otherwise turn into speckle when downscaled.
GLYPH_RGB = (203, 202, 153)

# Applied to the alpha channel after downscaling, to bring back strokes that LANCZOS spread
# into grey. Lower where less of each stroke lands on a whole pixel.
#
# Thickening the strokes beforehand is the obvious alternative and it does not work: the gaps in
# this monogram are narrower than the strokes, so dilation closes the negative space before it
# rescues anything, and 16px turns into a filled blob.
ALPHA_GAMMA = {16: 0.55, 20: 0.60, 24: 0.65, 32: 0.75}


def cut_out_glyph(source: Image.Image) -> Image.Image:
    """The monogram on transparency: luminance becomes alpha, colour becomes flat."""
    luminance = source.convert("L")
    span = CUTOFF_HIGH - CUTOFF_LOW
    alpha = luminance.point(
        lambda v: 0 if v <= CUTOFF_LOW else 255 if v >= CUTOFF_HIGH else (v - CUTOFF_LOW) * 255 // span
    )
    glyph = Image.new("RGBA", source.size, (*GLYPH_RGB, 0))
    glyph.putalpha(alpha)
    return glyph


def render_glyph(glyph: Image.Image, size: int) -> Image.Image:
    frame = glyph.resize((size, size), Image.LANCZOS)
    gamma = ALPHA_GAMMA[size]
    frame.putalpha(
        frame.getchannel("A").point(lambda v: min(255, int(255 * (v / 255) ** gamma)))
    )
    return frame


def build_frames(source: Image.Image) -> dict[int, Image.Image]:
    glyph = cut_out_glyph(source)
    frames = {size: render_glyph(glyph, size) for size in GLYPH_SIZES}
    frames.update({size: source.resize((size, size), Image.LANCZOS) for size in BADGE_SIZES})
    return frames


def write_preview(frames: dict[int, Image.Image], path: Path) -> None:
    cell, pad = 128, 8
    sheet = Image.new("RGBA", ((cell + pad) * len(frames), cell), (40, 40, 40, 255))
    for index, size in enumerate(sorted(frames)):
        blown = frames[size].resize((cell, cell), Image.NEAREST)
        sheet.paste(blown, (index * (cell + pad), 0), blown)
    sheet.convert("RGB").save(path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preview", action="store_true", help=f"also write {PREVIEW.name}")
    args = parser.parse_args()

    source = Image.open(SOURCE).convert("RGBA")
    if source.size != (256, 256):
        raise SystemExit(f"{SOURCE.name} must be 256x256, got {source.size[0]}x{source.size[1]}")

    frames = build_frames(source)
    ordered = [frames[size] for size in sorted(frames, reverse=True)]
    ordered[0].save(TARGET, format="ICO", sizes=[im.size for im in ordered], append_images=ordered[1:])
    print(f"wrote {TARGET.name}: {', '.join(str(s) for s in sorted(frames))}")

    if args.preview:
        write_preview(frames, PREVIEW)
        print(f"wrote {PREVIEW.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
