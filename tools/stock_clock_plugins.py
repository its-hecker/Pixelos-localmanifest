# SPDX-License-Identifier: Apache-2.0
"""Trust only PixelOS's bundled stock clock providers in SystemUI."""

import re
from pathlib import Path


SYSTEMUI = Path("frameworks/base/packages/SystemUI")
MODULE = SYSTEMUI / "src/com/android/systemui/plugins/PluginsModule.kt"
REGISTRY = SYSTEMUI / "customization/src/com/android/systemui/shared/clocks/ClockRegistry.kt"
PACKAGES = tuple("com.android.systemui.clocks." + name for name in (
    "bignum", "calligraphy", "flex", "growth", "handwritten", "inflate",
    "metro", "numoverlap", "weather",
))
ORIGINAL = "            val privilegedPlugins = context.resources.getStringArray(R.array.config_pluginAllowlist)"
PATCHED = ORIGINAL + " +\n" + "\n".join([
    "                arrayOf(",
    "                    // Trust the bundled stock clocks independently of debug properties.",
    *(f'                    "{package}",' for package in PACKAGES),
    "                )",
])


def prepare(rom, write=False):
    """Validate first; preserve all existing allowlist entries and unrelated edits."""
    registry = (rom / REGISTRY).read_text()
    known = set(re.findall(r'"(com\.android\.systemui\.clocks\.[^"]+)"\s+to\b', registry))
    if known != set(PACKAGES):
        raise ValueError("Stock ClockRegistry providers changed; review the clock allowlist fix")
    path = rom / MODULE
    source = path.read_text()
    if source.count(ORIGINAL) != 1:
        raise ValueError("Expected exactly one SystemUI stock clock plugin policy")
    if source.count(PATCHED) == 1:
        return False
    # Match the whole statement: never overwrite a different local policy extension.
    statement = ORIGINAL + "\n            return PackageConfig(*privilegedPlugins)"
    if source.count(statement) != 1:
        raise ValueError("SystemUI plugin policy changed; review before applying stock clock fix")
    if write:
        path.write_text(source.replace(statement, PATCHED + "\n            return PackageConfig(*privilegedPlugins)", 1))
    return True
