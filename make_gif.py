#!/usr/bin/env python3
"""Creates results/animation.gif from all PNGs in results/"""

import re
from pathlib import Path
from PIL import Image

results = Path(__file__).parent / "results"
pngs = sorted(
    (p for p in results.glob("*.png") if p.name != "animation.png"),
    key=lambda p: [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", p.stem)],
)
frames = [Image.open(p).convert("RGBA") for p in pngs]
output = results / "animation.gif"

frames[0].save(
    output,
    save_all=True,
    append_images=frames[1:],
    loop=0,
    duration=[5000] * (len(frames) - 1) + [15000],  # linger on last frame
)
print(f"Saved: {output}")
