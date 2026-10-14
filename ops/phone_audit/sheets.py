"""Contact sheets from audit.py screenshots: sheets.py <audit-dir> <out-dir> <width>."""
import glob
import os
import re
import sys

from PIL import Image

src, dst, width = sys.argv[1], sys.argv[2], int(sys.argv[3])
os.makedirs(dst, exist_ok=True)
shots = glob.glob(os.path.join(src, f"{width}-*~*.png"))
keys = sorted({re.sub(r"~\d+\.png$", "", os.path.basename(p)) for p in shots})
for key in keys:
    tiles = [Image.open(p).convert("RGB") for p in sorted(glob.glob(os.path.join(src, key + "~*.png")))]
    per = 3
    for i in range(0, len(tiles), per):
        group = tiles[i:i + per]
        th = int(group[0].height * width / group[0].width)
        sheet = Image.new("RGB", (width * per + 8 * (per - 1), th), (120, 120, 120))
        for k, t in enumerate(group):
            sheet.paste(t.resize((width, th)), (k * (width + 8), 0))
        sheet.save(os.path.join(dst, f"{key}-{i // per + 1}.jpg"), quality=82)
print(" ".join(sorted(os.listdir(dst))))
