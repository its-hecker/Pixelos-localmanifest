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
python3 "$floral_setup_dir/tools/signing.py" check
git -C vendor/google/coral lfs pull
python3 "$floral_setup_dir/tools/prepare.py" "$@"
python3 "$floral_setup_dir/tools/validate.py" --rom-root "$PWD"
source build/envsetup.sh
breakfast coral "${PIXEL_BUILD_VARIANT:-userdebug}"
floral_active_certificate="$(get_build_var PRODUCT_DEFAULT_DEV_CERTIFICATE)"
floral_active_overrides="$(get_build_var PRODUCT_CERTIFICATE_OVERRIDES)"
python3 "$floral_setup_dir/tools/signing.py" check \
    --active-cert "$floral_active_certificate" --active-overrides "$floral_active_overrides"
m -j"${PIXEL_BUILD_JOBS:-$(nproc)}" pixelos
