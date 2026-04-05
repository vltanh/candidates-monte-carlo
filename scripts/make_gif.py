#!/usr/bin/env python3
"""Creates an animated GIF from all PNGs in a directory."""

import argparse
import re
from pathlib import Path
from PIL import Image


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path, help="Directory containing PNG files")
    parser.add_argument(
        "-o", "--output", type=Path, default=None,
        help="Output GIF path (default: <input_dir>/animation.gif)",
    )
    parser.add_argument(
        "-d", "--duration", type=int, default=5000,
        help="Frame duration in ms (default: 5000)",
    )
    parser.add_argument(
        "--last-duration", type=int, default=15000,
        help="Last frame duration in ms (default: 15000)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    output = args.output or args.input_dir / "animation.gif"

    pngs = sorted(
        (p for p in args.input_dir.glob("*.png") if p != output.with_suffix(".png")),
        key=lambda p: [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", p.stem)],
    )
    if not pngs:
        raise SystemExit(f"No PNG files found in {args.input_dir}")

    frames = [Image.open(p).convert("RGBA") for p in pngs]
    frames[0].save(
        output,
        save_all=True,
        append_images=frames[1:],
        loop=0,
        duration=[args.duration] * (len(frames) - 1) + [args.last_duration],
    )
    print(f"Saved: {output}")


if __name__ == "__main__":
    main()
