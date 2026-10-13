#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run from the Android source root, after repo sync.
# Android's envsetup does not support nounset, so do not enable set -u here.
set -eo pipefail
if [[ ! -d .repo ]]; then
    echo "Run this script from the PixelOS Android source root containing .repo." >&2
    exit 1
fi
if [[ ! -f build/envsetup.sh || ! -f build/make/core/envsetup.mk ]]; then
    echo "Missing Android environment files in this checkout." >&2
    echo "Run: python3 .repo/local_manifests/tools/restore_checkout.py --project build/make --restore" >&2
    echo "Then: repo sync -l -j1 --fail-fast build/make" >&2
    exit 1
fi
if [[ ! -f trusty/vendor/google/aosp/lk_inc.mk || ! -f lk_inc.mk ]] || \
        ! cmp -s -- trusty/vendor/google/aosp/lk_inc.mk lk_inc.mk; then
    echo "Missing or mismatched Trusty lk_inc.mk source/root copy." >&2
    echo "Run: python3 .repo/local_manifests/tools/restore_checkout.py --project trusty/vendor/google/aosp --restore" >&2
    echo "Then: repo sync -l -j1 --fail-fast trusty/vendor/google/aosp" >&2
    echo "Verify: cmp -- trusty/vendor/google/aosp/lk_inc.mk lk_inc.mk" >&2
    exit 1
fi
floral_setup_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python3 "$floral_setup_dir/tools/check_qcom_namespaces.py"
git -C vendor/google/coral lfs pull
python3 "$floral_setup_dir/tools/prepare.py" "$@"
python3 "$floral_setup_dir/tools/validate.py" --rom-root "$PWD"
source build/envsetup.sh
breakfast coral "${PIXEL_BUILD_VARIANT:-userdebug}"
m -j"${PIXEL_BUILD_JOBS:-$(nproc)}" pixelos
