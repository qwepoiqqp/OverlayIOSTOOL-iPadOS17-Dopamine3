#!/usr/bin/env python3
"""Validate the iPadOS 17 Dopamine rootless source and optional DEB."""

from __future__ import annotations

import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_VERSION = "5.27.0+ios17.1"
EXPECTED_DEPENDS = "mobilesubstrate, firmware (>= 17.0), firmware (<< 18.0)"


def read_control(path: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            key, value = line.split(":", 1)
            fields[key] = value.strip()
    return fields


def run(*args: str) -> str:
    return subprocess.run(args, check=True, text=True, capture_output=True).stdout


def require_tool(name: str, errors: list[str]) -> bool:
    if shutil.which(name):
        return True
    errors.append(f"required package-audit tool is missing: {name}")
    return False


def verify_source(errors: list[str]) -> None:
    control = read_control(ROOT / "control")
    if control.get("Version") != EXPECTED_VERSION:
        errors.append(f"control Version must be {EXPECTED_VERSION!r}, got {control.get('Version')!r}")
    if control.get("Depends") != EXPECTED_DEPENDS:
        errors.append(f"control Depends must be {EXPECTED_DEPENDS!r}, got {control.get('Depends')!r}")
    if control.get("Architecture") != "iphoneos-arm64":
        errors.append("control Architecture must be iphoneos-arm64 for rootless packages")

    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    required_make_patterns = {
        r"(?m)^TARGET\s*:?=\s*iphone:clang:latest:15\.0\s*$": "deployment target must be iOS 15.0",
        r"(?m)^THEOS_PACKAGE_SCHEME\s*=\s*rootless\s*$": "Theos rootless package scheme is required",
        r"(?m)^OverlayIOSTOOL_ARCHS\s*=\s*arm64 arm64e\s*$": "SpringBoard tweak must contain arm64 and arm64e",
        r"(?m)^OverlayIOSTOOLApp_ARCHS\s*=\s*arm64\s*$": "companion app must remain arm64",
    }
    for pattern, message in required_make_patterns.items():
        if not re.search(pattern, makefile):
            errors.append(message)

    with (ROOT / "Resources" / "Info.plist").open("rb") as stream:
        info = plistlib.load(stream)
    if info.get("MinimumOSVersion") != "15.0":
        errors.append("companion app MinimumOSVersion must be 15.0")
    if 2 not in info.get("UIDeviceFamily", []):
        errors.append("companion app must declare native iPad support in UIDeviceFamily")

    with (ROOT / "OverlayIOSTOOL.plist").open("rb") as stream:
        substrate_filter = plistlib.load(stream)
    classes = substrate_filter.get("Filter", {}).get("Classes", [])
    if "UIApplication" not in classes:
        errors.append("substrate filter must target UIApplication for the app touch relay")

    workflow = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
    if "runs-on: macos-latest" not in workflow:
        errors.append("arm64e package workflow must run on macOS/Xcode")
    if "tools/verify_ios17_rootless.py" not in workflow:
        errors.append("build workflow must audit the generated DEB")


def verify_deb(deb: Path, errors: list[str]) -> None:
    tools = ("dpkg-deb", "lipo", "otool")
    if not all(require_tool(name, errors) for name in tools):
        return

    fields = read_control_from_deb(deb)
    for key, expected in {
        "Version": EXPECTED_VERSION,
        "Depends": EXPECTED_DEPENDS,
        "Architecture": "iphoneos-arm64",
    }.items():
        if fields.get(key) != expected:
            errors.append(f"DEB {key} must be {expected!r}, got {fields.get(key)!r}")

    with tempfile.TemporaryDirectory(prefix="overlayiostool-audit-") as temp:
        extracted = Path(temp)
        subprocess.run(("dpkg-deb", "-R", str(deb), str(extracted)), check=True)
        dylib = extracted / "var/jb/Library/MobileSubstrate/DynamicLibraries/OverlayIOSTOOL.dylib"
        app = extracted / "var/jb/Applications/OverlayIOSTOOLApp.app/OverlayIOSTOOLApp"
        for artifact in (dylib, app):
            if not artifact.is_file():
                errors.append(f"missing rootless artifact: {artifact.relative_to(extracted)}")
        if not dylib.is_file() or not app.is_file():
            return

        dylib_archs = set(run("lipo", "-archs", str(dylib)).split())
        if not {"arm64", "arm64e"}.issubset(dylib_archs):
            errors.append(f"tweak architectures must include arm64 and arm64e, got {sorted(dylib_archs)}")
        app_archs = run("lipo", "-archs", str(app)).split()
        if app_archs != ["arm64"]:
            errors.append(f"companion app must be arm64-only, got {app_archs}")

        libraries = run("otool", "-L", str(dylib))
        if "@rpath/CydiaSubstrate.framework/CydiaSubstrate" not in libraries:
            errors.append("tweak is missing the rootless CydiaSubstrate @rpath dependency")
        load_commands = run("otool", "-l", str(dylib))
        if "/var/jb/Library/Frameworks" not in load_commands:
            errors.append("tweak is missing the /var/jb rootless framework rpath")
        if not re.search(r"\bminos 15\.0\b", load_commands):
            errors.append("tweak Mach-O deployment target must be iOS 15.0")


def read_control_from_deb(deb: Path) -> dict[str, str]:
    output = run("dpkg-deb", "-f", str(deb))
    fields: dict[str, str] = {}
    for line in output.splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            key, value = line.split(":", 1)
            fields[key] = value.strip()
    return fields


def main() -> int:
    errors: list[str] = []
    verify_source(errors)
    if len(sys.argv) > 2:
        print("usage: verify_ios17_rootless.py [package.deb]", file=sys.stderr)
        return 2
    if len(sys.argv) == 2:
        verify_deb(Path(sys.argv[1]).resolve(), errors)
    if errors:
        print("iPadOS 17 rootless verification failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("iPadOS 17 rootless verification passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
