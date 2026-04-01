"""Local build script for TOTStatsMonitor.exe — also used by CI."""
import os
import re
import subprocess
import sys


def get_version():
    with open("outlast_analyzer.py", encoding="utf-8") as f:
        return re.search(r'__version__ = "(.+)"', f.read()).group(1)


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
        "         StringStruct(u'FileDescription', u'OutlastTrials Stats Monitor'),",
        f"         StringStruct(u'FileVersion', u'{version}'),",
        "         StringStruct(u'InternalName', u'TOTStatsMonitor'),",
        "         StringStruct(u'OriginalFilename', u'TOTStatsMonitor.exe'),",
        "         StringStruct(u'ProductName', u'OutlastTrials Stats Contributor'),",
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
        "outlast_analyzer.py"
    ])

    if result.returncode == 0:
        print(f"\nBuild successful! Output: dist/TOTStatsMonitor.exe")
    else:
        print(f"\nBuild failed with exit code {result.returncode}")
        sys.exit(result.returncode)


def main():
    version = get_version()
    generate_version_info(version)

    # Write version to GITHUB_OUTPUT if running in CI
    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a") as f:
            f.write(f"version={version}\n")

    build(version)


if __name__ == "__main__":
    main()
