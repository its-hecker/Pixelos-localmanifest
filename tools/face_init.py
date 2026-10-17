# SPDX-License-Identifier: Apache-2.0
"""Register each new HIDL Face sensor before connecting its lazy HAL session."""

import hashlib
import os
from pathlib import Path
import stat
import tempfile


FACE_ROOT = Path("frameworks/base/services/core/java/com/android/server/biometrics/sensors/face")
SOURCE = FACE_ROOT / "aidl/FaceProvider.java"
HIDL_SOURCE = FACE_ROOT / "hidl/HidlToAidlSensorAdapter.java"
SENSOR_LIST = FACE_ROOT.parent / "SensorList.java"

# PixelOS seventeen at 81b912ee97d9d4673ed4696bde30f14841b26c99.
# Only this complete, reviewed method (or its already fixed form) is accepted.
ORIGINAL_METHOD = """    private void addHidlSensors(SensorProps prop, boolean resetLockoutRequiresChallenge) {
        final int sensorId = prop.commonProps.sensorId;
        final Sensor sensor = new HidlToAidlSensorAdapter(this, mContext, mHandler, prop,
                mLockoutResetDispatcher, mBiometricContext, resetLockoutRequiresChallenge,
                () -> {
                    //TODO: update to make this testable
                    scheduleInternalCleanup(sensorId, ActivityManager.getCurrentUser(),
                            null /* callback */);
                    scheduleGetFeature(sensorId, new Binder(), ActivityManager.getCurrentUser(),
                            BiometricFaceConstants.FEATURE_REQUIRE_ATTENTION, null,
                            mContext.getOpPackageName());
                });
        sensor.init(mLockoutResetDispatcher, this);
        final int userId = sensor.getLazySession().get() == null ? UserHandle.USER_NULL :
                sensor.getLazySession().get().getUserId();
        mFaceSensors.addSensor(sensorId, sensor, userId,
                new SynchronousUserSwitchObserver() {
                    @Override
                    public void onUserSwitching(int newUserId) {
                        scheduleInternalCleanup(sensorId, newUserId, null /* callback */);
                        scheduleGetFeature(sensorId, new Binder(), newUserId,
                                BiometricFaceConstants.FEATURE_REQUIRE_ATTENTION,
                                null, mContext.getOpPackageName());
                    }
                });
        Slog.d(getTag(), "Added: " + mFaceSensors.get(sensorId));
    }
"""
LAZY_USER = """        final int userId = sensor.getLazySession().get() == null ? UserHandle.USER_NULL :
                sensor.getLazySession().get().getUserId();
"""
FIXED_USER = """        // A new HIDL sensor has no active user yet. Connecting its lazy session here
        // can post cleanup to FaceHandler before addSensor publishes the sensor.
        final int userId = UserHandle.USER_NULL;
"""
FIXED_METHOD = ORIGINAL_METHOD.replace(LAZY_USER, FIXED_USER, 1)


def transform(content):
    newline = b"\r\n" if b"\r\n" in content else b"\n"
    original = ORIGINAL_METHOD.replace("\n", newline.decode()).encode()
    fixed = FIXED_METHOD.replace("\n", newline.decode()).encode()
    if content.count(fixed) == 1 and content.count(original) == 0:
        return content
    if content.count(original) != 1 or content.count(fixed) != 0:
        raise ValueError("Review changed FaceProvider.addHidlSensors before applying the startup fix")
    return content.replace(original, fixed, 1)


def validate_contract(rom):
    hidl = (rom / HIDL_SOURCE).read_text()
    sensors = (rom / SENSOR_LIST).read_text()
    if "private int mCurrentUserId = UserHandle.USER_NULL;" not in hidl:
        raise ValueError("Review the HIDL sensor's initial user before applying the startup fix")
    if "mSensors.put(sensorId, sensor);\n        registerUserSwitchObserver" not in sensors:
        raise ValueError("Review SensorList registration order before applying the startup fix")


def configure(rom, write=False):
    path = rom / SOURCE
    if path.is_symlink():
        raise ValueError("Refusing to replace a symlinked FaceProvider: " + str(path))
    original = path.read_bytes()
    replacement = transform(original)
    validate_contract(rom)
    if replacement == original:
        return "already configured"
    if not write:
        return "patch available"
    backup = rom / "out/pixelos-face-init" / (
        hashlib.sha256(original).hexdigest() + ".FaceProvider.java.original")
    backup.parent.mkdir(parents=True, exist_ok=True)
    try:
        with backup.open("xb") as handle:
            handle.write(original)
    except FileExistsError:
        if backup.read_bytes() != original:
            raise ValueError("FaceProvider backup differs from the original source: " + str(backup))
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".face-init-", delete=False) as handle:
            temporary = Path(handle.name)
            handle.write(replacement)
        temporary.chmod(stat.S_IMODE(path.stat().st_mode))
        if path.read_bytes() != original:
            raise ValueError("FaceProvider changed during preparation; retry after reviewing the edit")
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return "configured; original saved at " + str(backup)
