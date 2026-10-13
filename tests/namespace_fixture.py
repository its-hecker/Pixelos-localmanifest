# SPDX-License-Identifier: Apache-2.0
"""Stage the namespace export shape used by PixelOS's upstream manifest."""

import os
from pathlib import Path
import xml.etree.ElementTree as ET

CHIPSETS = ["msm8953", "sdm660", "sm8150", "sm8250", "sm8350", "sm8450",
            "sm8450-6.6", "sm8550", "sm8650", "sm8750"]
CONTENT = ('soong_namespace {\n    imports: [\n'
           '        "vendor/qcom/opensource/commonsys-intf/display",\n'
           '        "vendor/qcom/opensource/display",\n    ],\n}\n')
SHARED = 'cc_defaults {\n    name: "android_hardware_qtiaudio_config_defaults",\n}\n'


def stage(rom):
    source = rom / "hardware/qcom-caf/common/os_pickup_qssi.bp"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(CONTENT)
    (source.parent / "Android.bp").write_text(SHARED)
    manifest = ET.Element("manifest")
    project = ET.SubElement(manifest, "project", path="hardware/qcom-caf/common")
    for chipset in CHIPSETS:
        relative = Path("hardware/qcom-caf") / chipset / "Android.bp"
        destination = rom / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.symlink_to(os.path.relpath(source, destination.parent))
        ET.SubElement(project, "linkfile", src="os_pickup_qssi.bp", dest=str(relative))
    return source, manifest
