"""Build "Etsy Insights.app" (a small launcher bundle) and the zip that is sent to the user.

Usage: python -m tools.build_app [version]
"""
from __future__ import annotations

import plistlib
import shutil
import struct
import sys
import zlib
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ACCENT = (0x1F, 0x6F, 0x5C)


def _png(size: int) -> bytes:
    """Rounded green square with three white bars (a tiny bar chart)."""
    radius = size * 0.22
    bars = [(0.26, 0.58), (0.44, 0.40), (0.62, 0.24)]  # (left, top) as fractions; bars end at 0.76
    width = 0.12
    rows = []
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            cx = min(max(x, radius), size - 1 - radius)
            cy = min(max(y, radius), size - 1 - radius)
            inside = (x - cx) ** 2 + (y - cy) ** 2 <= radius ** 2
            if not inside:
                row += b"\x00\x00\x00\x00"
                continue
            fx, fy = x / size, y / size
            white = any(left <= fx <= left + width and top <= fy <= 0.76 for left, top in bars)
            row += bytes((255, 255, 255, 255) if white else (*ACCENT, 255))
        rows.append(bytes(row))
    raw = zlib.compress(b"".join(rows), 9)

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", raw) + chunk(b"IEND", b"")


def make_icns(path: Path) -> None:
    body = b""
    for kind, size in ((b"ic08", 256), (b"ic09", 512)):
        png = _png(size)
        body += kind + struct.pack(">I", len(png) + 8) + png
    Path(path).write_bytes(b"icns" + struct.pack(">I", len(body) + 8) + body)


def build_app(repo: Path, out_dir: Path, version: str) -> Path:
    repo, out_dir = Path(repo), Path(out_dir)
    app = out_dir / "Etsy Insights.app"
    if app.exists():
        shutil.rmtree(app)
    contents = app / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    resources = contents / "Resources"
    resources.mkdir()
    info = plistlib.loads((repo / "macos" / "Info.plist").read_bytes())
    info["CFBundleShortVersionString"] = version
    info["CFBundleVersion"] = version
    (contents / "Info.plist").write_bytes(plistlib.dumps(info))
    launcher = contents / "MacOS" / "etsy-insights"
    shutil.copyfile(repo / "macos" / "launcher.sh", launcher)
    launcher.chmod(0o755)
    shutil.copyfile(repo / "macos" / "bootstrap.py", resources / "bootstrap.py")
    shutil.copyfile(repo / "requirements.txt", resources / "requirements.txt")
    shutil.copytree(repo / "etsy_insights", resources / "app" / "etsy_insights",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for name in ("config.toml", "keywords.txt"):
        shutil.copyfile(repo / name, resources / "app" / name)
    make_icns(resources / "AppIcon.icns")
    return app


def make_zip(app: Path, readme: Path, out_zip: Path) -> Path:
    app, out_zip = Path(app), Path(out_zip)
    out_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(app.rglob("*")):
            name = f"{app.name}/{path.relative_to(app).as_posix()}"
            mode = path.stat().st_mode & 0xFFFF
            if path.is_dir():
                info = zipfile.ZipInfo(name + "/")
                info.external_attr = (mode << 16) | 0x10
                archive.writestr(info, b"")
            else:
                info = zipfile.ZipInfo(name)
                info.external_attr = mode << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, path.read_bytes())
        archive.write(readme, "README.txt")
    return out_zip


def main(argv: list[str]) -> int:
    version = argv[0] if argv else "3.0.0"
    dist = REPO / "dist"
    app = build_app(REPO, dist, version)
    archive = make_zip(app, REPO / "macos" / "README.txt", dist / "Etsy-Insights.zip")
    print(f"App: {app}\nZip: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
