#!/usr/bin/env python3
"""The design system's faces, as TrueType files iOS can load.

The web bundle ships them as woff2 from @fontsource (docs/70 "Type"). iOS wants
TTF, and the dot-matrix readout face is a variable font whose square-dot look
is an axis setting (ROND 0, weight 800) -- so it is pinned into a static
instance here. Run from ios/ after `npm install`; the outputs are committed,
so a build never needs node_modules. All three families are SIL OFL.
"""
import shutil
from pathlib import Path

from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

NM = Path(__file__).resolve().parents[2] / "node_modules"
OUT = Path(__file__).resolve().parents[1] / "App" / "Fonts"
OUT.mkdir(parents=True, exist_ok=True)

STATIC = {
    "IBMPlexSans-Regular.ttf": "@fontsource/ibm-plex-sans/files/ibm-plex-sans-latin-400-normal.woff2",
    "IBMPlexSans-Medium.ttf": "@fontsource/ibm-plex-sans/files/ibm-plex-sans-latin-500-normal.woff2",
    "IBMPlexSans-SemiBold.ttf": "@fontsource/ibm-plex-sans/files/ibm-plex-sans-latin-600-normal.woff2",
    "IBMPlexMono-Regular.ttf": "@fontsource/ibm-plex-mono/files/ibm-plex-mono-latin-400-normal.woff2",
    "IBMPlexMono-Medium.ttf": "@fontsource/ibm-plex-mono/files/ibm-plex-mono-latin-500-normal.woff2",
    "IBMPlexMono-SemiBold.ttf": "@fontsource/ibm-plex-mono/files/ibm-plex-mono-latin-600-normal.woff2",
}

for name, src in STATIC.items():
    f = TTFont(NM / src)
    f.flavor = None
    f.save(OUT / name)
    print(name, f["name"].getDebugName(4), f["name"].getDebugName(6))

# Doto: weight 800, square dots (ROND 0), as the web's .mu-readout__value.
doto = TTFont(NM / "@fontsource-variable/doto/files/doto-latin-full-normal.woff2")
doto.flavor = None
pixel = instancer.instantiateVariableFont(doto, {"wght": 800, "ROND": 0}, updateFontNames=False)
# Name it so iOS finds it by one PostScript name, apart from any other Doto.
names = pixel["name"]
for rec in list(names.names):
    if rec.nameID in (1, 4, 16):
        rec.string = "JF Doto Pixel"
    elif rec.nameID == 6:
        rec.string = "JFDotoPixel"
    elif rec.nameID in (2, 17):
        rec.string = "Regular"
pixel.save(OUT / "JFDotoPixel.ttf")
print("JFDotoPixel.ttf", pixel["name"].getDebugName(4), pixel["name"].getDebugName(6))

# The SIL OFL travels with the fonts.
shutil.copy(NM / "@fontsource/ibm-plex-sans/LICENSE", OUT / "LICENSE-IBMPlex.txt")
shutil.copy(NM / "@fontsource-variable/doto/LICENSE", OUT / "LICENSE-Doto.txt")
