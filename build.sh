#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run from the Android source root, after repo sync.
# Android's envsetup does not support nounset, so do not enable set -u here.
set -eo pipefail
if [[ ! -f build/envsetup.sh || ! -d .repo ]]; then
    echo "Run this script from a synced PixelOS Android source root." >&2
    exit 1
fi
floral_setup_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
git -C vendor/google/coral lfs pull
python3 "$floral_setup_dir/tools/prepare.py" "$@"
python3 "$floral_setup_dir/tools/validate.py" --rom-root "$PWD"
source build/envsetup.sh
breakfast coral "${PIXEL_BUILD_VARIANT:-userdebug}"
m -j"${PIXEL_BUILD_JOBS:-$(nproc)}" pixelos
