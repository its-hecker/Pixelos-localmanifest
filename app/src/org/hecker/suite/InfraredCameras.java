// SPDX-License-Identifier: Apache-2.0
package org.hecker.suite;

import android.graphics.ImageFormat;
import android.hardware.camera2.CameraAccessException;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraManager;
import android.hardware.camera2.params.StreamConfigurationMap;
import android.os.Build;
import android.util.Size;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

final class InfraredCameras {
    private InfraredCameras() {}

    static final class Sensor {
        final String id;
        final String openId;
        final CameraCharacteristics characteristics;
        final List<Stream> streams;
        Sensor(String id, String openId, CameraCharacteristics characteristics, List<Stream> streams) {
            this.id = id; this.openId = openId; this.characteristics = characteristics;
            this.streams = streams;
        }
        boolean physical() { return !id.equals(openId); }
    }

    static final class Stream {
        final int format;
        final Size size;
        Stream(int format, Size size) { this.format = format; this.size = size; }
    }

    static boolean floral() {
        return "coral".equals(Build.DEVICE) || "flame".equals(Build.DEVICE);
    }

    static List<Sensor> discover(CameraManager manager) throws CameraAccessException {
        Map<String, Sensor> sensors = new LinkedHashMap<>();
        String[] exposed = manager.getCameraIdList();
        for (String parent : exposed) {
            CameraCharacteristics characteristics = manager.getCameraCharacteristics(parent);
            add(manager, sensors, parent, parent, characteristics);
            for (String physical : characteristics.getPhysicalCameraIds()) {
                try {
                    add(manager, sensors, physical, parent, manager.getCameraCharacteristics(physical));
                } catch (CameraAccessException | IllegalArgumentException ignored) {
                    // A physical ID can exist in metadata without an accessible stream.
                }
            }
        }
        // Google's Pixel 4 CameraX source identifies 6/7 as the front NIR sensors.
        // Some Coral HALs expose these only through direct Camera2 discovery.
        if (floral()) {
            for (String id : new String[] {"6", "7"}) {
                if (sensors.containsKey(id)) continue;
                try { add(manager, sensors, id, id, manager.getCameraCharacteristics(id)); }
                catch (CameraAccessException | IllegalArgumentException ignored) {}
            }
        }
        return new ArrayList<>(sensors.values());
    }

    private static void add(CameraManager manager, Map<String, Sensor> result, String id,
            String openId, CameraCharacteristics characteristics) {
        Integer facing = characteristics.get(CameraCharacteristics.LENS_FACING);
        Integer filter = characteristics.get(CameraCharacteristics.SENSOR_INFO_COLOR_FILTER_ARRANGEMENT);
        boolean knownPixelIr = floral() && ("6".equals(id) || "7".equals(id));
        boolean monochrome = filter != null && (filter == 5 || filter == 6); // MONO / NIR
        if (facing == null || facing != CameraCharacteristics.LENS_FACING_FRONT
                || !(monochrome || knownPixelIr)) return;
        StreamConfigurationMap map = characteristics.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP);
        if (map == null) return;
        List<Stream> streams = new ArrayList<>();
        for (int format : new int[] {ImageFormat.Y8, ImageFormat.YUV_420_888,
                ImageFormat.RAW_SENSOR, ImageFormat.RAW10, ImageFormat.RAW12}) {
            Size[] sizes = map.getOutputSizes(format);
            if (sizes == null || sizes.length == 0) continue;
            // Smallest sensor-provided size, keeping raw frame conversion bounded.
            Size smallest = Arrays.stream(sizes).filter(s -> s.getWidth() >= 160 && s.getHeight() >= 120
                    && (long) s.getWidth() * s.getHeight() <= 2_100_000)
                    .min((a, b) -> Long.compare((long) a.getWidth() * a.getHeight(),
                            (long) b.getWidth() * b.getHeight())).orElse(null);
            if (smallest != null) streams.add(new Stream(format, smallest));
        }
        if (streams.isEmpty()) return;
        Sensor prior = result.get(id);
        // Prefer an enumerated directly-openable sensor over a logical routing path.
        if (prior == null || id.equals(openId)) result.put(id, new Sensor(id, openId, characteristics, streams));
    }
}
