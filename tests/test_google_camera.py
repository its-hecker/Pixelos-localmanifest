# SPDX-License-Identifier: Apache-2.0
"""Verify immutable Camera fetching and reject incomplete installed split sets."""

import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from google_camera import CAMERA, fetch_chunk, verify_installed


class CameraPayloadTests(unittest.TestCase):
    def test_download_hash_and_size_failures_preserve_the_existing_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chunk"
            path.write_bytes(b"original cache")
            expected = {"size": 4, "sha256": hashlib.sha256(b"good").hexdigest()}
            for bad in (b"bad!", b"short", b"x"):
                with self.subTest(bad=bad), patch("urllib.request.urlopen", return_value=io.BytesIO(bad)):
                    with self.assertRaises(ValueError):
                        fetch_chunk("https://example.invalid/pinned", path, expected)
                    self.assertEqual(path.read_bytes(), b"original cache")
                    self.assertEqual(list(path.parent.iterdir()), [path])
            with patch("urllib.request.urlopen", return_value=io.BytesIO(b"good")):
                fetch_chunk("https://example.invalid/pinned", path, expected)
            self.assertEqual(path.read_bytes(), b"good")

    def test_installed_package_requires_every_original_split_and_no_stock_camera(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            camera = root / CAMERA
            (camera / "prebuilt").mkdir(parents=True)
            files = {name: {"size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                     for name, data in (("base.apk", b"base"), ("split_startup.apk", b"startup"))}
            (camera / "source.json").write_text(json.dumps({"files": files}))
            (camera / "prebuilt/payload.json").write_text(json.dumps({"files": list(files)}))
            output = root / "output"
            installed = output / "product/app/GoogleCameraCoral"
            installed.mkdir(parents=True)
            (installed / "GoogleCameraCoral.apk").write_bytes(b"base")
            with self.assertRaisesRegex(ValueError, "split package"):
                verify_installed(root, output)
            (installed / "feature.apk").write_bytes(b"startup")
            verify_installed(root, output)
            for name in ("Aperture", "Camera2"):
                with self.subTest(stock_camera=name):
                    stale = output / "product/app" / name
                    stale.mkdir()
                    with self.assertRaisesRegex(ValueError, "Stale " + name):
                        verify_installed(root, output)
                    stale.rmdir()


if __name__ == "__main__":
    unittest.main()
