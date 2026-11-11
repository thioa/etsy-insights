import plistlib
import subprocess
import zipfile
from pathlib import Path

from tools.build_app import build_app, make_zip


def test_build_app_bundle(tmp_path):
    app = build_app(Path("."), tmp_path, "3.0.0")
    c = app / "Contents"
    info = plistlib.loads((c / "Info.plist").read_bytes())
    assert info["CFBundleExecutable"] == "etsy-insights" and info["CFBundleName"] == "Etsy Insights"
    assert info["CFBundleShortVersionString"] == "3.0.0" and info["CFBundleIconFile"] == "AppIcon"
    exe = c / "MacOS" / "etsy-insights"
    assert exe.stat().st_mode & 0o111 and subprocess.run(["bash", "-n", str(exe)]).returncode == 0
    assert (c / "Resources" / "app" / "etsy_insights" / "__main__.py").exists()
    assert (c / "Resources" / "app" / "etsy_insights" / "web" / "templates" / "base.html").exists()
    assert (c / "Resources" / "AppIcon.icns").read_bytes()[:4] == b"icns"
    assert not list((c / "Resources" / "app").rglob("__pycache__"))
    assert not (c / "Resources" / "app" / "tests").exists()
    z = make_zip(app, Path("macos/README.txt"), tmp_path / "x.zip")
    member = zipfile.ZipFile(z).getinfo("Etsy Insights.app/Contents/MacOS/etsy-insights")
    assert (member.external_attr >> 16) & 0o111
