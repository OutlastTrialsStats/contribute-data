"""Local build script for TOTStatsMonitor.exe — also used by CI."""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERSION_FILE = ROOT / "src" / "totstats" / "__init__.py"
MANIFEST_FILE = ROOT / ".release-please-manifest.json"


def get_version():
    """The version from the package, cross-checked against the release-please manifest.

    release-please bumps both, so a mismatch means a hand edit slipped through and the
    executable's VERSIONINFO would disagree with the release tag.
    """
    source = VERSION_FILE.read_text(encoding="utf-8")
    match = re.search(r'^__version__ = "([^"]+)"', source, re.M)
    if match is None:
        raise SystemExit(f"no __version__ found in {VERSION_FILE}")
    version = match.group(1)

    manifest = json.loads(MANIFEST_FILE.read_text(encoding="utf-8"))["."]
    if version != manifest:
        raise SystemExit(
            f"version drift: {VERSION_FILE.name} says {version}, manifest says {manifest}"
        )
    return version


def generate_version_info(version):
    parts = list(map(int, version.split(".")))
    while len(parts) < 3:
        parts.append(0)
    maj, min_, patch = parts[0], parts[1], parts[2]

    vi = "\n".join([
        "VSVersionInfo(",
        "  ffi=FixedFileInfo(",
        f"    filevers=({maj}, {min_}, {patch}, 0),",
        f"    prodvers=({maj}, {min_}, {patch}, 0),",
        "    mask=0x3f,",
        "    flags=0x0,",
        "    OS=0x40004,",
        "    fileType=0x1,",
        "    subtype=0x0,",
        "    date=(0, 0)",
        "  ),",
        "  kids=[",
        "    StringFileInfo([",
        "      StringTable(",
        "        u'040904B0',",
        "        [StringStruct(u'CompanyName', u'OutlastTrialsStats'),",
        "         StringStruct(u'FileDescription', u'TOTStatsMonitor'),",
        f"         StringStruct(u'FileVersion', u'{version}'),",
        "         StringStruct(u'InternalName', u'TOTStatsMonitor'),",
        "         StringStruct(u'LegalCopyright', u'GPL-3.0'),",
        "         StringStruct(u'OriginalFilename', u'TOTStatsMonitor.exe'),",
        "         StringStruct(u'ProductName', u'TOTStatsMonitor'),",
        f"         StringStruct(u'ProductVersion', u'{version}')])]),",
        "    VarFileInfo([VarStruct(u'Translation', [0x0409, 1200])])",
        "  ])",
    ])

    with open("version_info.txt", "w") as f:
        f.write(vi)


def build(version):
    print(f"Building TOTStatsMonitor v{version}...")

    result = subprocess.run([
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--noconsole",
        "--icon", "icon.ico",
        "--add-data", "icon.ico;.",
        "--name", "TOTStatsMonitor",
        "--version-file", "version_info.txt",
        # src layout: the totstats package is not on the default path.
        "--paths", "src",
        # pystray picks its backend through importlib at import time, so the Windows backend is
        # not statically discoverable.
        "--hidden-import", "pystray._win32",
        "src/totstats/__main__.py",
    ])

    if result.returncode == 0:
        print("\nBuild successful! Output: dist/TOTStatsMonitor.exe")
    else:
        print(f"\nBuild failed with exit code {result.returncode}")
        sys.exit(result.returncode)


def main():
    version = get_version()
    generate_version_info(version)

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"version={version}\n")

    build(version)


if __name__ == "__main__":
    main()
