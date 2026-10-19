// SPDX-License-Identifier: Apache-2.0
package org.hecker.suite;

import android.Manifest;
import android.app.Activity;
import android.content.BroadcastReceiver;
import android.content.ContentValues;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.ImageFormat;
import android.graphics.Matrix;
import android.hardware.camera2.CameraAccessException;
import android.hardware.camera2.CameraCaptureSession;
import android.hardware.camera2.CameraCharacteristics;
import android.hardware.camera2.CameraDevice;
import android.hardware.camera2.CameraManager;
import android.hardware.camera2.CaptureRequest;
import android.hardware.camera2.params.BlackLevelPattern;
import android.hardware.camera2.params.OutputConfiguration;
import android.hardware.camera2.params.SessionConfiguration;
import android.media.Image;
import android.media.ImageReader;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.SystemClock;
import android.provider.MediaStore;
import android.view.MenuItem;
import android.view.Surface;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;
import java.io.IOException;
import java.io.OutputStream;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicBoolean;

public final class InfraredCameraActivity extends Activity {
    private final HandlerThread imageThread = new HandlerThread("HeckerInfraredFrames");
    private final AtomicBoolean framePending = new AtomicBoolean();
    private Handler imageHandler;
    private CameraManager manager;
    private CameraDevice camera;
    private CameraCaptureSession session;
    private ImageReader reader;
    private List<InfraredCameras.Sensor> sensors = new ArrayList<>();
    private InfraredPreview preview;
    private TextView status;
    private Button save;
    private Button next;
    private Bitmap latest;
    private boolean resumed;
    private int generation;
    private int sensorIndex;
    private int streamIndex;
    private int rotation;
    private long lastFrame;
    private boolean photoSaving;

    private final BroadcastReceiver screenOff = new BroadcastReceiver() {
        @Override public void onReceive(Context context, Intent intent) {
            resumed = false;
            closeCamera();
        }
    };

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE
                | WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        getWindow().setHideOverlayWindows(true);
        manager = getSystemService(CameraManager.class);
        imageThread.start();
        imageHandler = new Handler(imageThread.getLooper());
        LinearLayout page = Ui.page(this, R.string.ir_title);
        preview = new InfraredPreview(this);
        page.addView(preview, new LinearLayout.LayoutParams(-1, Ui.dp(this, 330)));
        status = Ui.text(this, getString(R.string.ir_searching), 15, false);
        page.addView(status);
        page.addView(Ui.text(this, getString(R.string.ir_note), 14, false));
        LinearLayout buttons = new LinearLayout(this);
        next = new Button(this);
        next.setText(R.string.ir_switch);
        next.setEnabled(false);
        next.setOnClickListener(v -> {
            if (sensors.isEmpty()) return;
            sensorIndex = (sensorIndex + 1) % sensors.size();
            streamIndex = 0;
            openSensor();
        });
        buttons.addView(next, new LinearLayout.LayoutParams(0, -2, 1));
        save = new Button(this);
        save.setText(R.string.ir_save);
        save.setEnabled(false);
        save.setOnClickListener(v -> savePhoto());
        buttons.addView(save, new LinearLayout.LayoutParams(0, -2, 1));
        page.addView(buttons);
        Button retry = new Button(this);
        retry.setText(R.string.ir_retry);
        retry.setOnClickListener(v -> startPreview());
        page.addView(retry);
        Ui.scroll(this, page);
        registerReceiver(screenOff, new IntentFilter(Intent.ACTION_SCREEN_OFF), Context.RECEIVER_NOT_EXPORTED);
    }

    @Override protected void onResume() {
        super.onResume(); resumed = true; startPreview();
    }

    private void startPreview() {
        if (!resumed) return;
        if (!InfraredCameras.floral()) { status.setText(R.string.ir_not_floral); return; }
        if (checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED) {
            status.setText(R.string.ir_permission);
            requestPermissions(new String[] {Manifest.permission.CAMERA}, 1);
            return;
        }
        closeCamera();
        status.setText(R.string.ir_searching);
        try {
            sensors = InfraredCameras.discover(manager);
            next.setEnabled(sensors.size() > 1);
            if (sensors.isEmpty()) { status.setText(R.string.ir_unavailable); return; }
            sensorIndex = Math.min(sensorIndex, sensors.size() - 1);
            streamIndex = 0;
            openSensor();
        } catch (CameraAccessException | IllegalArgumentException | SecurityException error) {
            status.setText(R.string.ir_unavailable);
        }
    }

    private void openSensor() {
        closeCamera();
        if (!resumed || sensors.isEmpty()) return;
        final int request = generation;
        final InfraredCameras.Sensor sensor = sensors.get(sensorIndex);
        final InfraredCameras.Stream stream = sensor.streams.get(streamIndex);
        Integer orientation = sensor.characteristics.get(CameraCharacteristics.SENSOR_ORIENTATION);
        int displayDegrees = getDisplay() == null ? 0 : getDisplay().getRotation() * 90;
        rotation = ((orientation == null ? 0 : orientation) + displayDegrees) % 360;
        status.setText(R.string.ir_searching);
        try {
            manager.openCamera(sensor.openId, getMainExecutor(), new CameraDevice.StateCallback() {
                @Override public void onOpened(CameraDevice device) {
                    if (!resumed || request != generation) { device.close(); return; }
                    camera = device;
                    configure(sensor, stream, request);
                }
                @Override public void onDisconnected(CameraDevice device) {
                    device.close();
                    if (request == generation) { closeCamera(); status.setText(R.string.ir_busy); }
                }
                @Override public void onError(CameraDevice device, int error) {
                    device.close();
                    if (request == generation) {
                        closeCamera();
                        status.setText(error == ERROR_CAMERA_IN_USE || error == ERROR_MAX_CAMERAS_IN_USE
                                ? R.string.ir_busy : R.string.ir_error);
                    }
                }
            });
        } catch (CameraAccessException | SecurityException | IllegalArgumentException error) {
            status.setText(R.string.ir_error);
        }
    }

    private void configure(InfraredCameras.Sensor sensor, InfraredCameras.Stream stream, int request) {
        try {
            reader = ImageReader.newInstance(stream.size.getWidth(), stream.size.getHeight(), stream.format, 3);
            Integer white = sensor.characteristics.get(CameraCharacteristics.SENSOR_INFO_WHITE_LEVEL);
            int[] black = new int[4];
            BlackLevelPattern pattern = sensor.characteristics.get(CameraCharacteristics.SENSOR_BLACK_LEVEL_PATTERN);
            if (pattern != null && (stream.format == ImageFormat.RAW_SENSOR
                    || stream.format == ImageFormat.RAW10 || stream.format == ImageFormat.RAW12)) {
                pattern.copyTo(black, 0);
            }
            final int whiteLevel = stream.format == ImageFormat.Y8 || stream.format == ImageFormat.YUV_420_888
                    ? 255 : white == null ? 0 : white;
            reader.setOnImageAvailableListener(source -> receiveFrame(source, request, whiteLevel, black), imageHandler);
            OutputConfiguration output = new OutputConfiguration(reader.getSurface());
            if (sensor.physical()) output.setPhysicalCameraId(sensor.id);
            camera.createCaptureSession(new SessionConfiguration(SessionConfiguration.SESSION_REGULAR,
                    java.util.Collections.singletonList(output), getMainExecutor(), new CameraCaptureSession.StateCallback() {
                        @Override public void onConfigured(CameraCaptureSession configured) {
                            if (!resumed || request != generation || camera == null) { configured.close(); return; }
                            session = configured;
                            try {
                                CaptureRequest.Builder builder;
                                try { builder = camera.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW); }
                                catch (IllegalArgumentException e) {
                                    builder = camera.createCaptureRequest(CameraDevice.TEMPLATE_MANUAL);
                                }
                                builder.addTarget(reader.getSurface());
                                session.setRepeatingRequest(builder.build(), null, null);
                                status.setText(getString(R.string.ir_active, sensor.id,
                                        stream.size.getWidth(), stream.size.getHeight()));
                                getWindow().getDecorView().postDelayed(() -> {
                                    if (resumed && request == generation && latest == null) {
                                        tryNextStream(request);
                                    }
                                }, 5000);
                            } catch (CameraAccessException | IllegalStateException | IllegalArgumentException error) {
                                tryNextStream(request);
                            }
                        }
                        @Override public void onConfigureFailed(CameraCaptureSession configured) {
                            configured.close(); tryNextStream(request);
                        }
                    }));
        } catch (CameraAccessException | IllegalStateException | IllegalArgumentException error) {
            tryNextStream(request);
        }
    }

    private void tryNextStream(int request) {
        if (!resumed || request != generation) return;
        if (++streamIndex < sensors.get(sensorIndex).streams.size()) openSensor();
        else { closeCamera(); status.setText(R.string.ir_error); }
    }

    private void receiveFrame(ImageReader source, int request, int whiteLevel, int[] blackLevels) {
        Bitmap bitmap = null;
        boolean ownsPending = false;
        try (Image image = source.acquireLatestImage()) {
            if (image == null || SystemClock.elapsedRealtime() - lastFrame < 100
                    || !framePending.compareAndSet(false, true)) return;
            ownsPending = true;
            lastFrame = SystemClock.elapsedRealtime();
            Image.Plane plane = image.getPlanes()[0];
            int[] pixels = new int[image.getWidth() * image.getHeight()];
            RawFrameDecoder.decode(plane.getBuffer(), image.getWidth(), image.getHeight(),
                    plane.getRowStride(), plane.getPixelStride(), image.getFormat(), whiteLevel, blackLevels, pixels);
            bitmap = Bitmap.createBitmap(pixels, image.getWidth(), image.getHeight(), Bitmap.Config.ARGB_8888);
            final Bitmap frame = bitmap;
            runOnUiThread(() -> {
                try {
                    if (!resumed || request != generation) { frame.recycle(); return; }
                    latest = frame;
                    preview.frame(frame, rotation);
                    save.setEnabled(!photoSaving);
                    // A previous bitmap can still belong to the hardware display list.
                    // Let the renderer and GC release it after the next frame.
                } finally { framePending.set(false); }
            });
        } catch (IllegalArgumentException | IllegalStateException | ArithmeticException error) {
            if (bitmap != null) bitmap.recycle();
            if (ownsPending) framePending.set(false);
            runOnUiThread(() -> { if (request == generation) tryNextStream(request); });
        }
    }

    private void savePhoto() {
        if (!resumed || latest == null || photoSaving) return;
        Matrix transform = new Matrix();
        transform.postRotate(rotation);
        transform.postScale(-1f, 1f);
        final Bitmap photo = Bitmap.createBitmap(latest, 0, 0, latest.getWidth(), latest.getHeight(), transform, true);
        photoSaving = true;
        save.setEnabled(false);
        // A photo write is bounded and user initiated; it does not keep the camera open.
        new Thread(() -> {
            Uri uri = null;
            boolean success = false;
            try {
                ContentValues values = new ContentValues();
                values.put(MediaStore.Images.Media.DISPLAY_NAME, "IR_"
                        + new SimpleDateFormat("yyyyMMdd_HHmmss_SSS", Locale.ROOT).format(new Date()) + ".png");
                values.put(MediaStore.Images.Media.MIME_TYPE, "image/png");
                values.put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/HeckerSuite");
                values.put(MediaStore.Images.Media.IS_PENDING, 1);
                uri = getContentResolver().insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values);
                if (uri == null) throw new IOException("No media destination");
                try (OutputStream stream = getContentResolver().openOutputStream(uri)) {
                    if (stream == null || !photo.compress(Bitmap.CompressFormat.PNG, 100, stream)) {
                        throw new IOException("Photo write failed");
                    }
                }
                values.clear(); values.put(MediaStore.Images.Media.IS_PENDING, 0);
                if (getContentResolver().update(uri, values, null, null) != 1) {
                    throw new IOException("Could not publish photo");
                }
                success = true;
            } catch (IOException | RuntimeException error) {
                if (uri != null) {
                    try { getContentResolver().delete(uri, null, null); } catch (RuntimeException ignored) {}
                }
            } finally {
                photo.recycle();
                final boolean saved = success;
                runOnUiThread(() -> {
                    photoSaving = false;
                    if (isDestroyed()) return;
                    save.setEnabled(resumed && latest != null);
                    Toast.makeText(this, saved ? R.string.ir_saved : R.string.ir_save_failed, Toast.LENGTH_LONG).show();
                });
            }
        }, "HeckerInfraredPhoto").start();
    }

    private void closeCamera() {
        generation++;
        if (session != null) { session.close(); session = null; }
        if (camera != null) { camera.close(); camera = null; }
        if (reader != null) { reader.close(); reader = null; }
        if (save != null) save.setEnabled(false);
        if (preview != null) preview.clear();
        latest = null;
    }

    @Override protected void onPause() { resumed = false; closeCamera(); super.onPause(); }
    @Override protected void onDestroy() {
        unregisterReceiver(screenOff);
        closeCamera(); imageThread.quitSafely(); super.onDestroy();
    }
    @Override public void onRequestPermissionsResult(int code, String[] permissions, int[] results) {
        super.onRequestPermissionsResult(code, permissions, results);
        if (code == 1 && results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED) startPreview();
        else if (code == 1) status.setText(R.string.ir_permission);
    }
    @Override public boolean onOptionsItemSelected(MenuItem item) {
        if (item.getItemId() == android.R.id.home) { finish(); return true; }
        return super.onOptionsItemSelected(item);
    }
}
