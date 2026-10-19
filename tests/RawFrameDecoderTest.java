// SPDX-License-Identifier: Apache-2.0
package org.hecker.suite;

import java.nio.ByteBuffer;
import java.util.Arrays;

public final class RawFrameDecoderTest {
    private static int tests;
    private static void equal(int actual, int expected) {
        tests++;
        if (actual != expected) throw new AssertionError(actual + " != " + expected);
    }
    private static void rejects(Runnable operation) {
        tests++;
        try { operation.run(); throw new AssertionError("Accepted malformed plane"); }
        catch (IllegalArgumentException expected) {}
    }
    private static int gray(int value) { return 0xff000000 | value * 0x010101; }

    public static void main(String[] arguments) {
        int[] out = new int[8];
        // RAW10 low bits are packed into the fifth byte, in pixel order.
        RawFrameDecoder.decode(ByteBuffer.wrap(new byte[] {0, 0x55, (byte) 0xaa, (byte) 0xff,
                (byte) 0xe4}), 4, 1, 5, 0, RawFrameDecoder.RAW10, 1023, null, out);
        equal(out[0], gray(0)); equal(out[1], gray(341 * 255 / 1023));
        equal(out[2], gray(682 * 255 / 1023)); equal(out[3], gray(255));
        // RAW12 nibble packing: first pixel low nibble, then second pixel high nibble.
        RawFrameDecoder.decode(ByteBuffer.wrap(new byte[] {(byte) 0xab, (byte) 0xde, (byte) 0xfc}),
                2, 1, 3, 0, RawFrameDecoder.RAW12, 4095, null, out);
        equal(out[0], gray(0xabc * 255 / 4095)); equal(out[1], gray(0xdef * 255 / 4095));
        // Little-endian RAW16, with both row padding and sensor black level applied.
        RawFrameDecoder.decode(ByteBuffer.wrap(new byte[] {64, 0, (byte) 0xff, 3, 99, 99,
                64, 0, 64, 0}), 2, 2, 6, 2, RawFrameDecoder.RAW_SENSOR,
                1023, new int[] {64,64,64,64}, out);
        equal(out[0], gray(0)); equal(out[1], gray(255)); equal(out[2], gray(0));
        // Respect ByteBuffer position and luma pixel stride; chroma is never substituted.
        ByteBuffer positioned = ByteBuffer.wrap(new byte[] {99,10,99,20,99,30,99,40});
        positioned.position(1);
        RawFrameDecoder.decode(positioned, 2, 2, 4, 2, RawFrameDecoder.YUV_420_888, 255, null, out);
        equal(out[0], gray(10)); equal(out[1], gray(20));
        equal(out[2], gray(30)); equal(out[3], gray(40));
        RawFrameDecoder.decode(ByteBuffer.wrap(new byte[] {0,(byte) 255}), 2, 1, 2, 1,
                RawFrameDecoder.Y8, 255, null, out);
        equal(out[1], gray(255));
        rejects(() -> RawFrameDecoder.decode(ByteBuffer.allocate(4), 4, 1, 5, 0,
                RawFrameDecoder.RAW10, 1023, null, out));
        rejects(() -> RawFrameDecoder.decode(ByteBuffer.allocate(8), 2, 2, 2, 2,
                RawFrameDecoder.RAW_SENSOR, 1023, null, out));
        rejects(() -> RawFrameDecoder.decode(ByteBuffer.allocate(8), 2, 2, 4, 0,
                RawFrameDecoder.RAW_SENSOR, 1023, null, out));
        rejects(() -> RawFrameDecoder.decode(ByteBuffer.allocate(8), 2, 2, 4, 1,
                256, 255, null, out));
        System.out.println("Infrared plane decoding: " + tests + " checks passed");
    }
}
