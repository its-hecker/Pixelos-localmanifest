# SPDX-License-Identifier: Apache-2.0
"""Connect PixelOS's Display tap-to-sleep toggle to scene SystemUI input."""

import argparse
import json
from pathlib import Path


PATCHES = Path(__file__).with_name("tap-to-sleep-patches.json")


def plan(rom, revert=False):
    changes = {}
    for relative, edits in json.loads(PATCHES.read_text()).items():
        path = rom / relative
        original = path.read_text()
        content = original
        for edit in reversed(edits) if revert else edits:
            old, new = edit["old"], edit["new"]
            if content.count(new) == 1 and old not in content.replace(new, "", 1):
                if revert:
                    content = content.replace(new, old, 1)
                continue
            if content.count(old) != 1 or new in content:
                raise ValueError(f"Unfamiliar tap-to-sleep source in {relative}; no files written")
            if not revert:
                content = content.replace(old, new, 1)
        if content != original:
            changes[path] = content
    return changes


def prepare(rom, write=False, revert=False):
    changes = plan(rom, revert=revert)  # Validate every input before writing any file.
    if write:
        for path, content in changes.items():
            path.write_text(content)
    return len(changes)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom-root", type=Path, default=Path.cwd())
    parser.add_argument("--apply", action="store_true", help="Apply after validating all inputs")
    parser.add_argument("--revert", action="store_true", help="Remove only these reviewed source edits")
    args = parser.parse_args()
    try:
        count = prepare(args.rom_root.resolve(), write=args.apply or args.revert, revert=args.revert)
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + "\n")
    print(f"Tap-to-sleep source preparation: {count} changed files" + (" (check only)" if not (args.apply or args.revert) else ""))


if __name__ == "__main__":
    main()
