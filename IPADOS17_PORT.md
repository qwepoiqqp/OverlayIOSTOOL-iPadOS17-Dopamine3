# iPadOS 17 + Dopamine 3 rootless port

This branch is based on upstream commit `3349e24a8ab4a076aa5239400da1958ce9e2b886`
(`main`, package version 5.27.0) and keeps the tweak behavior unchanged.

## Audit result

- The published `v5.8.12` rootless DEB declares
  `firmware (>= 14.0), firmware (<< 17.0)`, so package managers correctly reject
  iPadOS 17.
- Its tweak dylib contains only an `arm64` slice. The tweak is injected into
  SpringBoard, so an `arm64e` slice built with the current ABI is required for
  A12 and newer platform processes.
- The current `Tweak.x` hooks the public `-[UIApplication sendEvent:]` method and
  uses public UIKit scene/window APIs. No hard-coded iOS 16 version gate or
  SpringBoard private-class hook was found, so this port does not change hook
  behavior without device evidence.

## Port changes

- Package version: `5.27.0+ios17.1`
- Firmware range: iPadOS/iOS 17.x only
- Rootless package architecture: `iphoneos-arm64`
- Tweak slices: `arm64 arm64e`
- Companion app slice: `arm64`
- Deployment target: iOS 15.0 (the supported rootless floor)
- Native iPad declaration added to `UIDeviceFamily`
- CI now validates package metadata, `/var/jb` layout, Mach-O slices, deployment
  target, Substrate dependency, and rootless rpath before uploading a DEB.

## Trusted build path

Use macOS with current Xcode and Theos, or run the included GitHub Actions
workflow. Do not build the SpringBoard `arm64e` slice with an old Linux clang.

```sh
export THEOS="$HOME/theos"
gmake clean package FINALPACKAGE=1
python3 tools/verify_ios17_rootless.py "$(ls packages/*.deb | head -1)"
```

The source-only check can be run on any platform with Python 3:

```sh
python3 tools/verify_ios17_rootless.py
```

## Verification boundary

The upstream base commit has a successful macOS/Xcode GitHub Actions build. This
port's source checks pass locally, but the current Windows host has no WSL,
macOS/Xcode, Theos, `lipo`, or `otool`, so no new DEB is claimed from this host.
The tweak has not been installed or runtime-tested on a user's device. A package
must pass the included DEB audit and then be tested cautiously on iPadOS 17 with
a working jailbreak recovery path before it is considered runtime-compatible.
