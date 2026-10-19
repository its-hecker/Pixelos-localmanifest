# SPDX-License-Identifier: Apache-2.0
# The release-config discovery pass runs before Android defines my-dir.
HECKER_SUITE_PATH := $(patsubst %/,%,$(dir $(lastword $(MAKEFILE_LIST))))
PRODUCT_PACKAGES += HeckerSuite
PRODUCT_RELEASE_CONFIG_MAPS += $(HECKER_SUITE_PATH)/release/release_config_map.textproto

# No Face HAL, camera-provider, firmware, kernel or SELinux replacement is needed.
# Use custom_coral-hecker_suite-userdebug for the experimental release flags.
