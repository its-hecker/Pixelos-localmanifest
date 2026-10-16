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
| `vendor/lunaris/dolby` | [Lunaris Dolby](https://github.com/its-hecker/vendor_lunaris_dolby) | pinned `544e6271`, from `pixelos-compat` |
| `vendor/hecker/floral/motionsense` | [Motion Sense plugin](https://github.com/its-hecker/floral-motionsense-plugin) | pinned `e66def12`, from `main` |
| `vendor/hecker/floral/faceid` | [3D Face ID plugin](https://github.com/its-hecker/floral-3D-faceid-plugin) | pinned `96b7e58a`, from `main` |

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

Lunaris Dolby uses a PixelOS compatibility pin with a distinct exported
sysconfig module and installed XML filename. This avoids collisions with
PixelOS's checked-out `DolbyAtmos` app during Make module registration.

The Face ID plugin declares library replacements for generated vendor images,
including libraries pulled in through transitive dependencies. It shares the
ROM's byte-identical v33 base, crypto and stagefright foundation providers,
retaining their 32-bit variants. Preparation checks each provider against the
plugin's immutable ABI inputs. The eight replaced stock Face ID service/library
modules retain dependency resolution with `no_full_install: true`; their full
copy rules would otherwise collide with the selected plugin modules in Make.

The stock camera binary uses a distinct `-coral` build module name, with its
original filename retained through `stem`. This keeps its AIDL V1 dependencies
separate from the newer AOSP source service. Device/vendor product entries and
the blob extraction suffix select that module together. Preparation backs up
and sets `no_full_install: true` on the AOSP eager camera service and its VINTF
fragment, so Make receives one binary/manifest installer. The source service
keeps its `init_rc` attachment: its script is byte-identical to Coral's stock
script, and the redundant vendor `PRODUCT_COPY_FILES` entry is removed. Soong
exports init scripts independently of `no_full_install`; integration checks both
those exports and the resolved vendor/plugin Make copies. Other camera modules
and local source edits are preserved. The original Blueprint is saved
under `out/floral-camera-install/`. If an older checkout
reports camera metadata V1/V3 conflicts through `android.prebuiltDependencyTag`,
sync both copies before rebuilding:

```bash
git -C .repo/local_manifests pull --ff-only
repo sync -c -j2 --fail-fast device/google/coral vendor/google/coral
PIXEL_BUILD_JOBS=8 bash .repo/local_manifests/build.sh
```

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
repo sync -l -j1 --fail-fast \
    build/make trusty/vendor/google/aosp hardware/qcom-caf/common
bash .repo/local_manifests/build.sh
```

The helper enumerates the active Repo projects and restores only missing files
from each Git index, including files excluded by skip-worktree/sparse rules and
files in initialized submodules. Existing files, local edits, staged deletions,
plugin caches and build outputs are preserved. Git's configured checkout filters,
including Git LFS, still apply. Running without `--restore` only reports missing
files; repeated `--project PATH` options limit recovery to selected projects.
The local sync above recreates the build links, Trusty root copy and Qualcomm
chipset namespace links afterward. These Repo exports live outside their source
projects and are not restored by Git's indexed-file recovery.
Sparse rules are left unchanged; if another sync excludes files again, rerun
recovery after that sync. Missing projects still need `repo sync` first.

### Repair the Trusty root copy

PixelOS's upstream manifest copies `trusty/vendor/google/aosp/lk_inc.mk` to
`lk_inc.mk` at the Android checkout root. This is a Repo checkout/copy step;
the separate Coral device/vendor repositories do not supply that file.
If Repo prints `Cannot copy file`, restore the source and rerun its local copy:
If sync instead reports local edits inside KernelSU, complete the shared-kernel
migration below before retrying this copy step.

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

### Repair Qualcomm namespace links

Errors such as `libgralloc.qti` or `color_sampling_test` being defined in several
CAF chipset trees can occur when Repo's namespace links are absent. PixelOS
exports `hardware/qcom-caf/common/os_pickup_qssi.bp` as each chipset's root
`Android.bp`, giving those otherwise duplicate modules separate namespaces.
Restore the common source and recreate its exports:

```bash
cd ~/pixelos &&
git -C .repo/local_manifests pull --ff-only &&
python3 .repo/local_manifests/tools/restore_checkout.py \
    --project hardware/qcom-caf/common --restore &&
repo sync -l -j1 --fail-fast hardware/qcom-caf/common &&
PIXEL_BUILD_JOBS=8 bash .repo/local_manifests/build.sh
```

The build helper checks every Qualcomm namespace export selected by the active
manifest before plugin preparation or compilation. It reports missing or
mismatched files without changing existing files. It also verifies that
`hardware/qcom-caf/common/Android.bp` retains globally visible shared audio
defaults. Keep ServerHive's RBE enabled.

### Undo local namespace workarounds before rebuilding

Both plugins require `soong_namespace` to precede the named license and other
modules in their generated `Android.bp`. The templates now enforce that order;
SPDX comments may still precede the namespace. Editing only generated files is
temporary because plugin preparation rewrites them.

If ServerHive added namespaces inside CAF media/display files or renamed chipset
directories to `.disabled`, use this recovery before rebuilding. A `.disabled`
suffix does not exclude the contained `Android.bp` files from source discovery.
The helper saves the six affected CAF files, both plugin templates and generated
root Blueprints in an archive outside the checkout, alongside tracked/staged
patches and the original revisions. It restores only those tracked files and
reinstates renamed chipset paths. Other files and the provider's RBE changes are
left intact. If both an original and `.disabled` directory exist, it stops before
changing anything rather than overwriting either directory.

```bash
cd ~/pixelos &&
git -C .repo/local_manifests pull --ff-only &&
python3 .repo/local_manifests/tools/recover_namespace_edits.py &&
repo sync -c -j2 --fail-fast \
    vendor/hecker/floral/faceid vendor/hecker/floral/motionsense &&
python3 .repo/local_manifests/tools/restore_checkout.py \
    --project hardware/qcom-caf/common --restore &&
repo sync -l -j1 --fail-fast hardware/qcom-caf/common &&
PIXEL_BUILD_JOBS=8 bash .repo/local_manifests/build.sh
```

Keep the printed backup folder until the rebuilt ROM has passed device testing.
This updates only the plugins and regenerates the existing CAF exports; it does
not reset the ROM checkout or clear the full build output.

### Repair shared Qualcomm audio defaults after namespace recovery

If Soong finds `android_hardware_qtiaudio_config_defaults` only inside namespace
`hardware/qcom-caf/common`, an additional local namespace has hidden the shared
defaults. Upstream defines these modules without a namespace in
`hardware/qcom-caf/common/Android.bp`; chipset namespaces can resolve them through
the implicit global scope. An extra namespace was also reported in
`sm8450/audio/graphservices/gsl/Android.bp`, where upstream inherits its chipset
scope. The recovery helper now backs up and restores both files as well as the
four earlier CAF workarounds. The build check rejects a scoped common Blueprint
before plugin preparation or compilation.

After the earlier plugin update has completed, use this shorter recovery:

```bash
cd ~/pixelos &&
git -C .repo/local_manifests pull --ff-only &&
python3 .repo/local_manifests/tools/recover_namespace_edits.py &&
repo sync -l -j1 --fail-fast hardware/qcom-caf/common &&
PIXEL_BUILD_JOBS=8 bash .repo/local_manifests/build.sh
```

Keep the new printed backup folder. The helper restores only the listed files;
it does not reset CAF repositories, discard other files, or alter RBE settings.

### Recover added namespaces across CAF projects

An extra namespace in a graphservice child such as `gsl` or `ar_util` hides sibling
libraries (`libar-gpr`, `libar-acdb`, `liblx-ar_util`, `liblx-osal`) that the
upstream chipset scope normally resolves. If namespace workarounds were added in
several CAF trees, discover and recover all eligible additions together:

```bash
cd ~/pixelos &&
git -C .repo/local_manifests pull --ff-only &&
python3 .repo/local_manifests/tools/recover_caf_namespaces.py --apply &&
PIXEL_BUILD_JOBS=8 bash .repo/local_manifests/build.sh
```

The helper uses the active Repo manifest and each checked-out CAF project's
`HEAD`. It removes namespace declarations only from tracked Blueprints whose
`HEAD` has none, preserving other working and staged edits. It also recovers new
files containing only namespace declarations and comments. Namespaces already
in `HEAD` remain in place; new files with module definitions require review.
The Repo-managed chipset-root exports are retained. Backups outside the source
tree contain every affected working/index file, scoped patches, original
revisions, and file modes. Keep the printed backup directory for recovery.

Omit `--apply` to print the eligible files without modifying anything. CI checks
this recovery against pinned SM8750 graphservice Blueprints, alongside fixture
tests for staged changes, legitimate upstream scopes, comment/string handling,
skip-worktree files, and concurrent edits.

### Pick up the shared kernel fixes

The manifest pins an exact kernel commit, so updating the shared kernel's branch
does not advance a PixelOS checkout until this manifest is updated and synced.
KernelSU is a separate Git repository: changes inside it are not included in a
parent-kernel diff or stash. Repo may stop project cleanup with
`KernelSU: Cannot remove project: uncommitted changes are present` even while
syncing other paths.

Before syncing, archive KernelSU's files outside the source tree, record its
tracked/staged changes, and stash its tracked and untracked edits. Save the
parent kernel's known generated compatibility edits separately. Then sync the
kernel first, restore remaining missing checkout files, and verify the Trusty
copy with the kernel included in the local sync:

```bash
cd ~/pixelos &&
pixel_kernel_backup="$(mktemp -d "$HOME/pixelos-kernel-update-XXXXXXXX")" &&
pixel_ksu_dir="kernel/google/msm-4.14/KernelSU" &&
if [[ -e "$pixel_ksu_dir/.git" ]]; then
    git -C "$pixel_ksu_dir" rev-parse HEAD \
        > "$pixel_kernel_backup/KernelSU-head.txt" &&
    git -C "$pixel_ksu_dir" diff --binary HEAD \
        > "$pixel_kernel_backup/KernelSU-tracked.patch" &&
    git -C "$pixel_ksu_dir" diff --binary --cached \
        > "$pixel_kernel_backup/KernelSU-staged.patch" &&
    tar -czf "$pixel_kernel_backup/KernelSU-files.tar.gz" \
        --exclude=.git -C "$pixel_ksu_dir" . &&
    git -C "$pixel_ksu_dir" stash push -u \
        -m "PixelOS kernel update: $pixel_kernel_backup"
fi &&
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
test "$(git -C kernel/google/msm-4.14/KernelSU rev-parse HEAD)" = \
    "ce120bd9f4ed262302d4776589a940412949d365" &&
python3 .repo/local_manifests/tools/restore_checkout.py --restore &&
repo sync -l -j1 --fail-fast \
    build/make trusty/vendor/google/aosp hardware/qcom-caf/common kernel/google/msm-4.14 &&
cmp -- trusty/vendor/google/aosp/lk_inc.mk lk_inc.mk &&
echo "Trusty copy verified" &&
rm -rf -- out/target/product/coral/obj/KERNEL_OBJ &&
PIXEL_BUILD_JOBS=8 bash .repo/local_manifests/build.sh
```

Run recovery and sync only after any current build has finished. Keep the saved
archive and patches for review; the build uses the committed driver and
compatibility backports. The archive also retains untracked and ignored files
if Repo cleans up the old submodule checkout. Source recovery writes only
missing indexed files and preserves existing source edits and build outputs.
Keep the provider's RBE environment and host integration patches on ServerHive.

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
stale-input rejection. It also parses both prepared product and board Make
entries before Android defines its `my-dir` helper, as in early product
configuration, and verifies Qualcomm namespace exports against pinned upstream
manifest/common sources. It uses small checkouts; it **does not compile Android**.
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
