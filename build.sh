#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Run from the Android source root, after repo sync.
# Android's envsetup does not support nounset, so do not enable set -u here.
set -eo pipefail
case "${PIXEL_BUILD_VARIANT:-userdebug}" in
    userdebug|eng) ;;
    *) echo "The validated Coral configuration requires a userdebug or eng build." >&2; exit 1 ;;
esac
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
# Separate release flags keep native App Lock out of the stable cp2a build.
lunch "custom_coral-hecker_suite-${PIXEL_BUILD_VARIANT:-userdebug}"
floral_product_out="$(get_build_var PRODUCT_OUT)"
floral_stale_camera=false
for floral_partition in system system_ext product vendor; do
    for floral_app_type in app priv-app; do
        for floral_stock_camera in Aperture Camera2; do
            if [[ -d "$floral_product_out/$floral_partition/$floral_app_type/$floral_stock_camera" ]]; then
                floral_stale_camera=true
            fi
        done
    done
done
if [[ "$floral_stale_camera" == true ]]; then
    echo "Removing previous stock camera installations from build outputs (installclean)."
    m installclean
fi
m -j"${PIXEL_BUILD_JOBS:-$(nproc)}" pixelos
python3 "$floral_setup_dir/tools/check_built_output.py" "$floral_product_out"
