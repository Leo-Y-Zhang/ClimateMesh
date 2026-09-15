"""Drop the team's real photos into the write-up, then rebuild Word and PDF.

    python SUBMISSION_PACK/_build/add_photos.py --pi IMG_1234.jpg --team IMG_1235.jpg

For each photo given it: honours the phone's rotation flag, strips every scrap
of metadata (phone cameras embed GPS coordinates, the device name and a serial
number — none of that belongs in a submitted entry), resizes to 2000 px wide,
saves it into ``SUBMISSION_PACK/photos/`` under the name the write-up expects,
and replaces that figure's ► placeholder caption with the real one. Then it
regenerates ``WRITEUP.docx`` and ``WRITEUP.pdf`` so the Word file carries the
photo too — no "right-click → Change Picture" needed.

Either photo may be given on its own; the other keeps its placeholder.

Options:
    --pi PATH          photo of the Raspberry Pi 5 running Climate Mesh (Figure 1)
    --team PATH        photo of the two of you at the Pi (Figure 6)
    --caption-pi TEXT  override Figure 1's caption
    --caption-team TEXT  override Figure 6's caption
    --no-build         update the photos and captions but skip the Word/PDF rebuild
    --keep-metadata    do not strip EXIF (not recommended; it carries GPS)

Needs Pillow (the dashboard already installs it) plus, for the rebuild, the
packages listed at the top of build_writeup.py.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PACK = HERE.parent
MD = PACK / "WRITEUP.md"
PHOTOS = PACK / "photos"

MAX_WIDTH = 2000
JPEG_QUALITY = 88

# figure number -> (destination file, default caption)
SLOTS = {
    "pi": (1, "photo-1-pi-running.jpg", "The Raspberry Pi 5 running Climate Mesh."),
    "team": (6, "photo-2-team.jpg", "Luis and Leo testing the flood scenario on the Pi."),
}


def describe_metadata(image) -> list[str]:
    """Human-readable list of the metadata about to be discarded."""
    try:
        exif = image.getexif()
    except Exception:  # noqa: BLE001 - a file without EXIF is the normal case
        return []
    if not exif:
        return []
    from PIL.ExifTags import GPSTAGS, TAGS

    found = []
    for tag_id, value in exif.items():
        name = TAGS.get(tag_id, str(tag_id))
        if name == "GPSInfo":
            gps = exif.get_ifd(tag_id) if hasattr(exif, "get_ifd") else {}
            keys = sorted(GPSTAGS.get(k, str(k)) for k in gps) if gps else []
            found.append(f"GPS location ({', '.join(keys)})" if keys else "GPS location")
        elif name in {"Make", "Model", "BodySerialNumber", "LensModel",
                      "DateTime", "DateTimeOriginal", "Software", "Artist",
                      "HostComputer", "SerialNumber"}:
            found.append(f"{name}={str(value)[:40]}")
    # Anything else still counts as metadata, just not worth naming.
    other = len(exif) - len(found)
    if other > 0:
        found.append(f"{other} other EXIF field(s)")
    return found


def install_photo(src: Path, dest: Path, *, strip: bool = True) -> str:
    """Normalise one photo into ``dest``. Returns a one-line report."""
    from PIL import Image, ImageOps

    if not src.is_file():
        raise SystemExit(f"error: no such file: {src}")
    with Image.open(src) as im:
        dropped = describe_metadata(im) if strip else []
        # Apply the phone's rotation flag, then drop it with the rest of EXIF.
        im = ImageOps.exif_transpose(im)
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        if im.width > MAX_WIDTH:
            height = round(im.height * MAX_WIDTH / im.width)
            im = im.resize((MAX_WIDTH, height), Image.LANCZOS)
        if strip:
            # A fresh image object carries no EXIF, ICC profile or comment.
            clean = Image.new(im.mode, im.size)
            clean.putdata(list(im.getdata()))
            im = clean
        PHOTOS.mkdir(parents=True, exist_ok=True)
        im.save(dest, "JPEG", quality=JPEG_QUALITY, optimize=True,
                progressive=True, exif=b"")
        size_kb = dest.stat().st_size / 1024
        report = f"{dest.name}: {im.width}x{im.height}, {size_kb:.0f} KB"
    if strip:
        report += (" — metadata removed: " + "; ".join(dropped)) if dropped else " — no metadata found"
    else:
        report += " — metadata KEPT (--keep-metadata)"
    return report


def set_caption(figure: int, filename: str, caption: str) -> bool:
    """Replace that figure's whole caption line in WRITEUP.md. True if changed."""
    text = MD.read_text(encoding="utf-8")
    # Trailing spaces only: \s* here would eat the blank line after the figure
    # and turn the next heading into a lazy continuation of the image paragraph.
    pattern = re.compile(
        r"^!\[Figure %d —.*?\]\(photos/%s\)(\{[^}]*\})?[^\S\n]*(?=\n|\Z)"
        % (figure, re.escape(filename)),
        re.MULTILINE,
    )
    matches = pattern.findall(text)
    if not matches:
        print(f"  note: no Figure {figure} caption line found for {filename}; left alone")
        return False
    attrs = matches[0] or "{.photo}"
    new_line = f"![Figure {figure} — {caption}](photos/{filename}){attrs}"
    MD.write_text(pattern.sub(lambda _: new_line, text, count=1), encoding="utf-8")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description="Add the team's photos to the write-up")
    ap.add_argument("--pi", type=Path, help="photo for Figure 1 (the Pi running Climate Mesh)")
    ap.add_argument("--team", type=Path, help="photo for Figure 6 (the two of you at the Pi)")
    ap.add_argument("--caption-pi", help="override Figure 1's caption")
    ap.add_argument("--caption-team", help="override Figure 6's caption")
    ap.add_argument("--no-build", action="store_true", help="skip the Word/PDF rebuild")
    ap.add_argument("--keep-metadata", action="store_true",
                    help="keep EXIF (not recommended: phone photos carry GPS)")
    args = ap.parse_args()

    if not args.pi and not args.team:
        ap.error("give --pi and/or --team with a path to a photo")

    for key, src, caption in (("pi", args.pi, args.caption_pi),
                              ("team", args.team, args.caption_team)):
        if not src:
            continue
        figure, filename, default_caption = SLOTS[key]
        print(f"Figure {figure}:")
        print("  " + install_photo(Path(src), PHOTOS / filename, strip=not args.keep_metadata))
        if set_caption(figure, filename, caption or default_caption):
            print(f'  caption: "{caption or default_caption}"')

    remaining = MD.read_text(encoding="utf-8").count("►")
    print(f"\n► items still to write in WRITEUP.md: {remaining}"
          + (" (§1, the reason you picked this project)" if remaining == 1 else ""))

    if args.no_build:
        print("Skipped the rebuild (--no-build). Run _build/build_writeup.py when ready.")
        return 0
    print("\nRebuilding WRITEUP.docx and WRITEUP.pdf …")
    result = subprocess.run([sys.executable, str(HERE / "build_writeup.py")],
                            cwd=str(PACK.parent))
    if result.returncode != 0:
        print("The rebuild failed; the photos and captions are still updated.\n"
              "Fix the build (see _build/build_writeup.py) or edit WRITEUP.docx by hand.")
        return result.returncode
    print("Done. Check SUBMISSION_PACK/WRITEUP.pdf, then send the zip.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
