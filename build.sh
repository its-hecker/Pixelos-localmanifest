#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run from the Android source root, after repo sync.
# Android's envsetup does not support nounset, so do not enable set -u here.
set -eo pipefail
if [[ ! -d .repo ]]; then
    echo "Run this script from the PixelOS Android source root containing .repo." >&2
    exit 1
fi
if [[ ! -f build/envsetup.sh ]]; then
    echo "Missing build/envsetup.sh in this Android checkout." >&2
    echo "Run: python3 .repo/local_manifests/tools/restore_checkout.py --restore" >&2
    echo "Then: repo sync -l -j1 --fail-fast build/make" >&2
    exit 1
fi
floral_setup_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
git -C vendor/google/coral lfs pull
python3 "$floral_setup_dir/tools/prepare.py" "$@"
python3 "$floral_setup_dir/tools/validate.py" --rom-root "$PWD"
source build/envsetup.sh
breakfast coral "${PIXEL_BUILD_VARIANT:-userdebug}"
m -j"${PIXEL_BUILD_JOBS:-$(nproc)}" pixelos
