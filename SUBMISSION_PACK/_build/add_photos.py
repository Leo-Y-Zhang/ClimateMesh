"""Drop the team's real photos into the write-up, then rebuild Word and PDF.

    python SUBMISSION_PACK/_build/add_photos.py --pi IMG_1234.jpg --team IMG_1235.jpg

For each photo given it: honours the phone's rotation flag, converts the
colours to sRGB, strips every scrap of metadata (phone cameras embed GPS
coordinates, the device name, a serial number and a timestamp — none of that
belongs in a submitted entry), resizes so neither side exceeds 2000 px, saves
it into ``SUBMISSION_PACK/photos/`` under the name the write-up expects, and
replaces that figure's ► placeholder caption with the real one, sized to match
the page. Then it regenerates ``WRITEUP.docx`` and ``WRITEUP.pdf`` so the Word
file carries the photo too — no "right-click → Change Picture" needed.

Either photo may be given on its own; the other keeps its placeholder. A
caption you have already written by hand is kept unless you pass a new one.

Options:
    --pi PATH            photo for Figure 5 (the Pi running Climate Mesh)
    --team PATH          photo for Figure 6 (the two of you at the Pi)
    --caption-pi TEXT    set Figure 5's caption (may be used without --pi)
    --caption-team TEXT  set Figure 6's caption (may be used without --team)
    --no-build           update photos and captions but skip the Word/PDF rebuild

Needs the packages in ``_build/requirements-build.txt``:

    pip install -r SUBMISSION_PACK/_build/requirements-build.txt
    playwright install chromium        # once, about 130 MB, for the PDF

JPEG and PNG are read out of the box. iPhone .HEIC files work too if
``pillow-heif`` is installed (it is in that requirements file); otherwise the
tool says so and tells you how to export a JPEG instead.
"""

from __future__ import annotations

import argparse
import importlib.util
import io
import re
import shutil
import subprocess
import sys
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    try:  # a non-UTF-8 console (Windows, or a redirect) must not kill the run
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

HERE = Path(__file__).resolve().parent
PACK = HERE.parent
MD = PACK / "WRITEUP.md"
DOCX = PACK / "WRITEUP.docx"
PDF = PACK / "WRITEUP.pdf"
PHOTOS = PACK / "photos"

MAX_PX = 2000          # neither side larger than this
MAX_HEIGHT_CM = 7.0    # mirrors `figure img.photo { max-height: 70mm }` in writeup.css
MAX_WIDTH_CM = 14.8    # the text column
JPEG_QUALITY = 88

# slot -> (figure number, destination file, default caption)
SLOTS = {
    "pi": (6, "photo-1-pi-running.jpg", "The Raspberry Pi 5 running Climate Mesh."),
    "team": (7, "photo-2-team.jpg", "Luis and Leo testing the flood scenario on the Pi."),
}


class PhotoError(Exception):
    """A photo could not be read; the message is written for a human."""


def _figure_pattern(figure: int, filename: str) -> re.Pattern[str]:
    # Trailing spaces only: \s* here would eat the blank line after the figure
    # and turn the next heading into a lazy continuation of the image paragraph.
    return re.compile(
        r"^!\[Figure %d — (?P<cap>.*?)\]\(photos/%s\)(?P<attrs>\{[^}]*\})?[^\S\n]*(?=\n|\Z)"
        % (figure, re.escape(filename)),
        re.MULTILINE,
    )


def open_photo(src: Path):
    """Open an image, or raise PhotoError with advice a student can act on."""
    from PIL import Image, UnidentifiedImageError

    if not src.exists():
        raise PhotoError(f"no such file: {src}")
    if not src.is_file():
        raise PhotoError(f"{src} is a folder, not a photo.")
    if src.stat().st_size == 0:
        raise PhotoError(f"{src} is empty (0 bytes) — the copy off the phone did not finish.")
    try:
        image = Image.open(src)
        image.load()
        return image
    except UnidentifiedImageError:
        if src.suffix.lower() in {".heic", ".heif"}:
            raise PhotoError(
                f"{src.name} is an iPhone HEIC photo and this Python cannot read it.\n"
                "  Either: pip install pillow-heif   (then re-run this command)\n"
                "  or: open the photo on the phone, Share → Options → Most Compatible,\n"
                "      or set Settings → Camera → Formats → Most Compatible and retake it."
            )
        raise PhotoError(
            f"{src.name} is not an image this tool can read (JPEG, PNG and, with "
            "pillow-heif, HEIC).\n  Check you picked the photo itself, not a folder, "
            "a screenshot shortcut or a document."
        )
    except OSError as exc:
        raise PhotoError(f"{src.name} is damaged or only partly copied ({exc}).\n"
                         "  Copy it off the phone again and retry.")


def describe_metadata(image) -> list[str]:
    """Everything about to be discarded, named where it is worth naming.

    Phones scatter this across four places: IFD0, the Exif sub-IFD, an XMP
    packet and a JPEG comment — plus an ICC profile. Looking only at IFD0
    reports "nothing found" for a photo that still carries GPS in its XMP.
    """
    found: list[str] = []
    named = {"Make", "Model", "Software", "DateTime", "DateTimeOriginal",
             "Artist", "HostComputer", "ImageDescription", "CameraOwnerName",
             "BodySerialNumber", "LensSerialNumber", "LensModel", "LensMake"}
    withheld = {"MakerNote", "UserComment"}  # may hold a typed-in address; do not echo
    counted = 0
    try:
        from PIL.ExifTags import GPSTAGS, TAGS

        exif = image.getexif()
        items = list(exif.items())
        try:
            items += list(exif.get_ifd(0x8769).items())  # Exif sub-IFD
        except Exception:  # noqa: BLE001
            pass
        counted = len(items)
        for tag_id, value in items:
            name = TAGS.get(tag_id, str(tag_id))
            if name == "GPSInfo":
                try:
                    gps = exif.get_ifd(0x8825)
                except Exception:  # noqa: BLE001
                    gps = {}
                keys = sorted(GPSTAGS.get(k, str(k)) for k in gps) if gps else []
                # Never print the coordinates themselves: they would then sit in
                # the student's terminal scrollback and any screenshot of it.
                found.append(f"GPS location ({', '.join(keys)})" if keys else "GPS location")
            elif name in withheld:
                size = len(value) if hasattr(value, "__len__") else 0
                found.append(f"{name} ({size} bytes, not shown)")
            elif name in named:
                found.append(f"{name}={str(value)[:40]}")
        try:
            if exif.get_ifd(0x8825):
                pass  # already reported through GPSInfo above
        except Exception:  # noqa: BLE001
            pass
    except Exception:  # noqa: BLE001 - a photo without EXIF is the normal case
        pass

    info = getattr(image, "info", {}) or {}
    if info.get("xmp") or "XML:com.adobe.xmp" in info:
        found.append("XMP block (often repeats the GPS position and a place name)")
    if info.get("comment"):
        found.append("JPEG comment")
    if info.get("icc_profile"):
        found.append("ICC colour profile (converted to sRGB first)")
    if getattr(image, "n_frames", 1) > 1:
        found.append("embedded preview frames")

    other = counted - sum(1 for f in found if "=" in f or f.startswith(("GPS", "MakerNote", "UserComment")))
    if other > 0:
        found.append(f"{other} other EXIF field(s)")
    return found


def install_photo(src: Path, dest: Path) -> tuple[str, int, int]:
    """Normalise one photo into ``dest``. Returns (report, width, height)."""
    from PIL import Image, ImageCms, ImageOps

    image = open_photo(src)
    with image:
        dropped = describe_metadata(image)
        # Apply the phone's rotation flag, then drop it with the rest of EXIF.
        image = ImageOps.exif_transpose(image)
        icc = (image.info or {}).get("icc_profile")
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        if icc:
            # Dropping a Display P3 profile without converting would silently
            # reassign the numbers to sRGB and shift every colour.
            try:
                image = ImageCms.profileToProfile(
                    image, ImageCms.ImageCmsProfile(io.BytesIO(icc)),
                    ImageCms.createProfile("sRGB"), outputMode="RGB")
            except Exception:  # noqa: BLE001 - a broken profile must not fail the run
                pass
        if max(image.size) > MAX_PX:
            image.thumbnail((MAX_PX, MAX_PX), Image.LANCZOS)
        # A fresh image object carries no EXIF, ICC, XMP or comment. paste()
        # copies the buffer; putdata() would build a per-pixel Python list and
        # cost four times the memory, which matters on a Pi.
        clean = Image.new(image.mode, image.size)
        clean.paste(image)
        width, height = clean.size
        PHOTOS.mkdir(parents=True, exist_ok=True)
        clean.save(dest, "JPEG", quality=JPEG_QUALITY, optimize=True,
                   progressive=True, exif=b"")
    size_kb = dest.stat().st_size / 1024
    report = f"{dest.name}: {width}x{height}, {size_kb:.0f} KB — "
    report += ("removed: " + "; ".join(dropped)) if dropped else "no metadata found"
    return report, width, height


def page_width_cm(width: int, height: int) -> float:
    """Width to print the photo at, so Word matches the PDF's height cap."""
    return round(min(MAX_WIDTH_CM, MAX_HEIGHT_CM * width / height), 1)


def escape_caption(caption: str) -> str:
    """Make a caption safe to drop into a Markdown image title."""
    caption = " ".join(caption.split())          # no newlines or tabs
    return re.sub(r"([\\\[\]])", r"\\\1", caption)  # a stray ] would kill the link


def set_caption(slot: str, caption: str | None,
                size: tuple[int, int] | None) -> tuple[str, bool] | None:
    """Rewrite that figure's line.

    Returns (caption used, kept_the_team's_own) or None if the line was absent.
    """
    figure, filename, default_caption = SLOTS[slot]
    text = MD.read_text(encoding="utf-8")
    pattern = _figure_pattern(figure, filename)
    match = pattern.search(text)
    if not match:
        print(f"  note: no Figure {figure} line found for {filename}; left alone")
        return None

    current = match.group("cap")
    kept = False
    if caption is None:
        if "►" in current:
            caption = default_caption
        else:
            caption, kept = current, True   # the team wrote their own; keep it

    attrs = match.group("attrs") or "{.photo}"
    if size:
        attrs = re.sub(r'\s*width="[^"]*"', "", attrs)
        attrs = attrs[:-1] + f' width="{page_width_cm(*size)}cm"' + "}"
    new_line = f"![Figure {figure} — {escape_caption(caption)}](photos/{filename}){attrs}"
    MD.write_text(pattern.sub(lambda _: new_line, text, count=1), encoding="utf-8")
    return caption, kept


def remaining_placeholders() -> list[str]:
    text = MD.read_text(encoding="utf-8")
    left = []
    for slot, (figure, filename, _) in SLOTS.items():
        match = _figure_pattern(figure, filename).search(text)
        if match and "►" in match.group("cap"):
            left.append(f"Figure {figure} (--{slot})")
    return left


def missing_build_packages() -> list[str]:
    return [name for name, module in (("pypandoc_binary", "pypandoc"),
                                      ("python-docx", "docx"),
                                      ("playwright", "playwright"),
                                      ("pymupdf", "pymupdf"))
            if importlib.util.find_spec(module) is None]


def backup_if_newer(path: Path, md_mtime: float) -> None:
    """Keep hand edits: the rebuild regenerates both files from WRITEUP.md.

    ``md_mtime`` must be WRITEUP.md's timestamp from before this run edited it,
    or the comparison always says the Markdown is newer.
    """
    if path.exists() and path.stat().st_mtime > md_mtime:
        backup = path.with_suffix(path.suffix + ".bak")
        shutil.copy2(path, backup)
        print(f"  {path.name} had edits newer than WRITEUP.md — copied to {backup.name} first")


def main() -> int:
    ap = argparse.ArgumentParser(description="Add the team's photos to the write-up")
    ap.add_argument("--pi", type=Path, help="photo for Figure 5 (the Pi running Climate Mesh)")
    ap.add_argument("--team", type=Path, help="photo for Figure 6 (the two of you at the Pi)")
    ap.add_argument("--caption-pi", help="set Figure 5's caption")
    ap.add_argument("--caption-team", help="set Figure 6's caption")
    ap.add_argument("--no-build", action="store_true", help="skip the Word/PDF rebuild")
    args = ap.parse_args()

    md_mtime_before = MD.stat().st_mtime if MD.exists() else 0.0

    jobs = [(key, src, caption) for key, src, caption in
            (("pi", args.pi, args.caption_pi), ("team", args.team, args.caption_team))
            if src or caption]
    if not jobs:
        ap.error("give --pi and/or --team with a path to a photo "
                 "(or --caption-pi/--caption-team on their own to fix a caption)")

    # Check every photo before changing anything, so a typo in the second path
    # cannot leave the write-up half updated.
    opened = {}
    for key, src, _ in jobs:
        if not src:
            continue
        try:
            open_photo(Path(src)).close()
        except PhotoError as exc:
            print(f"error: {exc}", file=sys.stderr)
            print("\nNothing was changed.", file=sys.stderr)
            return 1
        opened[key] = Path(src)

    if not args.no_build:
        missing = missing_build_packages()
        if missing:
            print("error: the Word/PDF rebuild needs packages that are not installed:",
                  ", ".join(missing), file=sys.stderr)
            print("  pip install -r SUBMISSION_PACK/_build/requirements-build.txt\n"
                  "  playwright install chromium\n"
                  "Nothing was changed. Add --no-build to update the photos and "
                  "captions only.", file=sys.stderr)
            return 1

    for key, src, caption in jobs:
        figure, filename, _ = SLOTS[key]
        print(f"Figure {figure}:")
        size = None
        if src:
            report, width, height = install_photo(opened[key], PHOTOS / filename)
            print("  " + report)
            size = (width, height)
        outcome = set_caption(key, caption, size)
        if outcome is not None:
            used, kept = outcome
            print(f'  caption{" (kept, yours)" if kept else ""}: "{used}"')
            if size:
                print(f"  printed at {page_width_cm(*size)} cm wide, matching the PDF")

    left = remaining_placeholders()
    if left:
        print("\nStill a grey PHOTO GOES HERE box: " + ", ".join(left)
              + ". Do not submit until it is gone.")
    else:
        print("\nBoth photos are in; no placeholders left in the write-up.")

    if args.no_build:
        print("Skipped the rebuild (--no-build). Run _build/build_writeup.py when ready.")
        return 0

    print("\nRebuilding WRITEUP.docx and WRITEUP.pdf …")
    for path in (DOCX, PDF):
        backup_if_newer(path, md_mtime_before)
    before = {p: (p.stat().st_mtime if p.exists() else 0) for p in (DOCX, PDF)}
    result = subprocess.run([sys.executable, str(HERE / "build_writeup.py")],
                            cwd=str(PACK.parent))
    if result.returncode == 0:
        print("Done. Check SUBMISSION_PACK/WRITEUP.pdf, then send the zip.")
        return 0

    # Say exactly which file is current and which is stale; the rebuild writes
    # the Word file first, so a Chromium failure leaves a correct docx and a
    # stale PDF, and guessing the wrong way round would be worse than silence.
    print("\nThe rebuild did not finish. The photos and captions in WRITEUP.md are saved.",
          file=sys.stderr)
    for path in (DOCX, PDF):
        current = path.exists() and path.stat().st_mtime > before[path]
        state = "rebuilt and up to date" if current else "NOT rebuilt — still the old version"
        print(f"  {path.name}: {state}", file=sys.stderr)
    if not (PDF.exists() and PDF.stat().st_mtime > before[PDF]):
        print("Do not send WRITEUP.pdf until it rebuilds: it still shows the placeholder.\n"
              "Usually this means Chromium is missing — run: playwright install chromium",
              file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
