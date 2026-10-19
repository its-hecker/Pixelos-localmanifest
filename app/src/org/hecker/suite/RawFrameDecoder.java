// SPDX-License-Identifier: Apache-2.0
package org.hecker.suite;

import java.nio.ByteBuffer;

/** Decodes the actual monochrome plane. No RGB-camera substitution or synthetic frames. */
final class RawFrameDecoder {
    static final int RAW_SENSOR = 32;
    static final int YUV_420_888 = 35;
    static final int RAW10 = 37;
    static final int RAW12 = 38;
    static final int Y8 = 0x20203859;

    private RawFrameDecoder() {}

    static boolean supports(int format) {
        return format == RAW_SENSOR || format == RAW10 || format == RAW12
                || format == Y8 || format == YUV_420_888;
    }

    static void decode(ByteBuffer bytes, int width, int height, int rowStride, int pixelStride,
            int format, int whiteLevel, int[] blackLevels, int[] pixels) {
        if (!supports(format) || width <= 0 || height <= 0 || rowStride <= 0
                || (long) width * height > pixels.length) {
            throw new IllegalArgumentException("Invalid infrared plane");
        }
        int rowBytes;
        switch (format) {
            case RAW10: rowBytes = ((width + 3) / 4) * 5; break;
            case RAW12: rowBytes = ((width + 1) / 2) * 3; break;
            case RAW_SENSOR:
                if (pixelStride < 2) throw new IllegalArgumentException("Invalid RAW16 stride");
                rowBytes = Math.addExact(Math.multiplyExact(width - 1, pixelStride), 2); break;
            default:
                if (pixelStride < 1) throw new IllegalArgumentException("Invalid luma stride");
                rowBytes = Math.addExact(Math.multiplyExact(width - 1, pixelStride), 1);
        }
        if (rowStride < rowBytes || (long) (height - 1) * rowStride + rowBytes > bytes.remaining()) {
            throw new IllegalArgumentException("Truncated infrared plane");
        }
        final int base = bytes.position();
        final int fallbackWhite = format == RAW10 ? 1023 : format == RAW12 ? 4095
                : format == RAW_SENSOR ? 65535 : 255;
        final int white = whiteLevel > 0 ? Math.min(whiteLevel, fallbackWhite) : fallbackWhite;
        for (int y = 0; y < height; y++) {
            int row = base + y * rowStride;
            for (int x = 0; x < width; x++) {
                final int value;
                if (format == RAW10) {
                    int group = row + (x / 4) * 5;
                    value = (u8(bytes, group + x % 4) << 2)
                            | ((u8(bytes, group + 4) >> (2 * (x % 4))) & 3);
                } else if (format == RAW12) {
                    int group = row + (x / 2) * 3;
                    value = (u8(bytes, group + x % 2) << 4)
                            | ((u8(bytes, group + 2) >> (4 * (x % 2))) & 15);
                } else if (format == RAW_SENSOR) {
                    int offset = row + x * pixelStride;
                    value = u8(bytes, offset) | (u8(bytes, offset + 1) << 8);
                } else {
                    value = u8(bytes, row + x * pixelStride);
                }
                int black = blackLevels != null && blackLevels.length == 4
                        ? blackLevels[(y & 1) * 2 + (x & 1)] : 0;
                int gray = Math.max(0, Math.min(255,
                        (value - black) * 255 / Math.max(1, white - black)));
                pixels[y * width + x] = 0xff000000 | (gray << 16) | (gray << 8) | gray;
            }
        }
    }

    private static int u8(ByteBuffer bytes, int offset) { return bytes.get(offset) & 0xff; }
}
