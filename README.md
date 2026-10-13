# PixelOS Android 17 for Pixel 4 XL

Build setup for **Pixel 4 XL (`coral`)** using PixelOS `seventeen`, independent
Nahida-derived device/vendor copies, the CNB kernel, and the standalone Floral
**3D Face ID** and **Motion Sense** plugins.

## Sources

| Checkout path | Repository | Revision |
| --- | --- | --- |
| `device/google/coral` | [PixelOS device copy](https://github.com/its-hecker/pixelos_android_device_google_coral) | `main` |
| `vendor/google/coral` | [PixelOS vendor copy](https://github.com/its-hecker/pixelos_proprietary_vendor_google_coral) | `main` |
| `kernel/google/msm-4.14` | [CNB kernel](https://github.com/its-hecker/infinity_cnb_kernel_google_msm-4.14) | pinned `aaaa03e4`, from `cnb-Latest-stable` |
| `packages/apps/ElmyraService` | [ElmyraService](https://github.com/LineageOS/android_packages_apps_ElmyraService) | pinned `baab2beb`, from `lineage-24.0` |
| `vendor/lunaris/dolby` | [Lunaris Dolby](https://github.com/its-hecker/vendor_lunaris_dolby) | pinned `cf47b515`, from `main` |
| `vendor/hecker/floral/motionsense` | [Motion Sense plugin](https://github.com/its-hecker/floral-motionsense-plugin) | pinned `75c8e5ff`, from `main` |
| `vendor/hecker/floral/faceid` | [3D Face ID plugin](https://github.com/its-hecker/floral-3D-faceid-plugin) | pinned `0ba71789`, from `main` |

The old kernel branch `cnb` was renamed to `cnb-Latest-stable`. This setup uses
that same CNB source, including its pinned KernelSU submodule (`sync-s="true"`).
The optimized Wireshark kernel is not selected.

This kernel pin includes the committed `path_umount`/seccomp compatibility
backports and the Coral KernelSU-Next UAPI 5 driver for the official v3.4.1
manager. The backports exist before parallel compilation begins; older pins
could let KernelSU patch `namespace.c` after its object had already compiled.
The driver also records its version for shallow submodule checkouts.

Device/vendor snapshots come from Nahida's `lineage-24.0` trees. Each copy records
its upstream commit in `UPSTREAM.json`. General HardwareInfo/SELinux, HWUI property,
mainline-module and camera packaging fixes are retained. PixelOS's GoogleParts
eSIM receiver uses local resources because PixelOS disables the Lineage SDK.
The unused base Oslo application policy and debug-property labels are removed;
the standalone plugin generates its own scoped platform policy. Stock Soli/CHRE,
FaceAuth, Citadel and camera services/firmware remain present.

Face compatibility code, enhanced Oslo APKs and Motion Sense settings are selected
through the plugins' product/board files. Plugin inheritance is last, after the
vendor product. PixelOS's software `ParanoidSense` Face Unlock is disabled before
common inheritance so it cannot compete with the real IR hardware provider.
GoogleParts has no second Motion Sense page.

## Initialize and sync

Use an Android build host with the normal AOSP build dependencies, Repo, Git LFS,
Python 3 and sufficient RAM/storage for an Android source build.

Create and enter a separate PixelOS build directory:

```bash
mkdir -p ~/pixelos
cd ~/pixelos
repo init -u https://github.com/PixelOS-AOSP/android_manifest.git -b seventeen --git-lfs
git clone https://github.com/its-hecker/Pixelos-localmanifest.git .repo/local_manifests
repo sync -c -j8
```

Use this manifest in a separate PixelOS checkout. If `.repo/local_manifests`
already exists, copy `floral.xml` and the setup scripts into it after reviewing
other Floral project entries. Do not select two projects at the same checkout
path. The manifest's removals replace those exact paths only.

### Recover missing checkout files

If sync reports success but tracked files such as `build/make/envsetup.sh`,
`device/google/coral/custom_coral.mk` or `BoardConfig-common.mk` are absent,
restore the missing files across the source checkout:

```bash
git -C .repo/local_manifests pull --ff-only
python3 .repo/local_manifests/tools/restore_checkout.py --restore
repo sync -l -j1 --fail-fast build/make trusty/vendor/google/aosp
bash .repo/local_manifests/build.sh
```

The helper enumerates the active Repo projects and restores only missing files
from each Git index, including files excluded by skip-worktree/sparse rules and
files in initialized submodules. Existing files, local edits, staged deletions,
plugin caches and build outputs are preserved. Git's configured checkout filters,
including Git LFS, still apply. Running without `--restore` only reports missing
files; repeated `--project PATH` options limit recovery to selected projects.
The local sync above recreates the build links and Trusty root copy afterward.
Sparse rules are left unchanged; if another sync excludes files again, rerun
recovery after that sync. Missing projects still need `repo sync` first.

### Repair the Trusty root copy

PixelOS's upstream manifest copies `trusty/vendor/google/aosp/lk_inc.mk` to
`lk_inc.mk` at the Android checkout root. This is a Repo checkout/copy step;
the separate Coral device/vendor repositories do not supply that file.
If Repo prints `Cannot copy file`, restore the source and rerun its local copy:

```bash
cd ~/pixelos &&
git -C .repo/local_manifests pull --ff-only &&
python3 .repo/local_manifests/tools/restore_checkout.py \
    --project build/make --project trusty/vendor/google/aosp --restore &&
repo sync -l -j1 --fail-fast build/make trusty/vendor/google/aosp &&
cmp -- trusty/vendor/google/aosp/lk_inc.mk lk_inc.mk &&
echo "Trusty copy verified"
```

`build.sh` verifies both Android environment markers and the Trusty source/root
copy before preparing plugins or compiling. A successful Repo summary alone is
insufficient when the copy step reported an error. If recovery still fails,
inspect both paths with `ls -ld trusty/vendor/google/aosp/lk_inc.mk lk_inc.mk`;
missing source files and destination type/permission problems need different
repairs.

### Pick up the shared kernel fixes

The manifest pins an exact kernel commit, so updating the shared kernel's branch
does not advance a PixelOS checkout until this manifest is updated and synced.
Before replacing an old pin, save its known generated compatibility edits:

```bash
cd ~/pixelos &&
pixel_kernel_backup="$(mktemp -d "$HOME/pixelos-kernel-update-XXXXXXXX")" &&
git -C kernel/google/msm-4.14 diff --binary HEAD -- \
    fs/namespace.c fs/internal.h include/linux/seccomp.h \
    > "$pixel_kernel_backup/ksu-compatibility.patch" &&
git -C kernel/google/msm-4.14 restore \
    --source=HEAD --staged --worktree --ignore-skip-worktree-bits -- \
    fs/namespace.c fs/internal.h include/linux/seccomp.h &&
echo "Previous kernel edits saved in: $pixel_kernel_backup" &&
git -C .repo/local_manifests pull --ff-only &&
repo sync -c -j1 --fail-fast kernel/google/msm-4.14 &&
git -C kernel/google/msm-4.14 submodule update --init --recursive &&
rm -rf -- out/target/product/coral/obj/KERNEL_OBJ &&
PIXEL_BUILD_JOBS=8 bash .repo/local_manifests/build.sh
```

Run recovery and sync only after any current build has finished. This replaces
the backed-up local compatibility edits with the committed backports. Keep the
provider's RBE environment and host integration patches when using ServerHive.

## Prepare and build

Builds use PixelOS's default signing configuration; no private-key setup is
required. If you already ran the previous signing helper, move
`vendor/lineage-priv/keys` outside the Android checkout to disable its overrides
while keeping your generated keys.

From the Android checkout root:

```bash
bash .repo/local_manifests/build.sh
```

The script resolves the vendor radio images through the existing upstream LFS
endpoint, verifies plugin inputs and native/APK bindings, applies the guarded
Face framework patches, and generates the active SystemUI/biometric overlays.
It then checks source wiring and all 11 stock radio checksums, runs
`breakfast coral userdebug`, and builds with `m pixelos`.
PixelOS's actual product name is **`custom_coral`**. The lunch release is read by
PixelOS's `breakfast` command from the synced sources; do not hard-code it.

The same steps can be run separately:

```bash
git -C vendor/google/coral lfs pull
python3 .repo/local_manifests/tools/prepare.py
python3 .repo/local_manifests/tools/validate.py --rom-root "$PWD"
source build/envsetup.sh
breakfast coral userdebug
m pixelos
```

`PIXEL_BUILD_JOBS=8` controls parallel build jobs. `PIXEL_BUILD_VARIANT=user` selects
a production build when calling `build.sh`. `--offline` passed to the script
uses previously cached, checksum-verified plugin binaries. The full Android
build itself performs no plugin downloads.

**Rerun preparation after every sync** of framework, vendor, overlay or plugin
sources. Changed inputs invalidate the plugins' build-time checks. Framework
patching is idempotent and backs up the original adapter under
`out/face-framework-patches/`. An unfamiliar framework implementation is refused
for review instead of force-patched.

Default overlay inputs are the selected PixelOS common overlays followed by the
Floral common and Coral overlays. Extra active overlays can be supplied with
repeated `--allowlist-xml` or `--biometrics-xml` options, in increasing priority.
The generated allowlist retains PixelOS's entries and appends both Oslo
components; the hardware Face sensor remains `0:8:15` on this Coral base.

Output is under `out/target/product/coral/`, with a `PixelOS_*.zip` OTA package.
For a record of all exact commits used by a completed build:

```bash
repo manifest -r -o out/pixelos-coral-source-manifest.xml
```

## Validation and first phone test

CI checks the real PixelOS source and both standalone plugin packages: framework
patch compatibility, native ABI/crypto/calibration bindings, APK interfaces,
setup idempotence, allowlist preservation, hardware sensor configuration and
stale-input rejection. It uses small checkouts; it **does not compile Android**.
Initial upstream inputs used by CI are recorded in `source-revisions.json`.

Full ROM compilation, SELinux/VINTF build checks and a PixelOS phone test remain
required. A passing setup test does not establish boot or hardware behavior.
For the first test on Coral, check:

- Boot, front/rear camera, telephony/data, Wi-Fi, eSIM and audio.
- Face enrollment, lock-screen unlock, repeated Face settings visits,
  removal/re-enrollment and hardware-backed BiometricPrompt.
- Motion Sense skip/pause, silence, reach/wake, glow preview, music glow,
  Air DJ, training and the production SystemUI plugin allowlist.

Collect immediately after a failure:

```bash
adb logcat -b all -d > pixelos-floral-logcat.txt
adb logcat -b crash -d > pixelos-floral-crash.txt
adb shell dumpsys face > pixelos-face-service.txt
adb shell lshal > pixelos-hal-services.txt
adb shell dumpsys activity service com.android.systemui/.SystemUIService > pixelos-systemui.txt
adb shell dumpsys package com.google.oslo > pixelos-oslo-package.txt
adb shell cmd overlay list --user 0 > pixelos-overlays.txt
```

Plugin-specific verification and troubleshooting are documented in each plugin's
README. Google proprietary inputs retain their upstream attribution and
immutable checksum records. The phone's own persist/calibration data is required.
