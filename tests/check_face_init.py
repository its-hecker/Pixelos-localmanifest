# SPDX-License-Identifier: Apache-2.0
"""Reproduce the FaceHandler race with the actual pinned Java registration method."""

import argparse
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import face_init


HARNESS = r'''
import java.util.HashMap;
import java.util.Map;
import java.util.function.Supplier;

public class FaceRegistrationRegression {
    static class UserHandle { static final int USER_NULL = -10000; static final int USER_SYSTEM = 0; }
    static class ActivityManager { static int getCurrentUser() { return 0; } }
    static class Binder { }
    static class BiometricFaceConstants { static final int FEATURE_REQUIRE_ATTENTION = 1; }
    static class Slog { static void d(String tag, String message) { } }
    static class Context { String getOpPackageName() { return "android"; } }
    static class CommonProps { int sensorId = 0; }
    static class SensorProps { CommonProps commonProps = new CommonProps(); }
    static abstract class SynchronousUserSwitchObserver { public abstract void onUserSwitching(int id); }
    static class AidlSession { int getUserId() { return UserHandle.USER_NULL; } }
    static class Sensor {
        FaceProvider provider;
        int sensorId;
        Runnable connectedCallback;
        boolean connected;
        boolean initialized;
        int activeUser = UserHandle.USER_NULL;
        void init(Object dispatcher, FaceProvider provider) { initialized = true; }
        Supplier<AidlSession> getLazySession() {
            return () -> {
                if (!connected) {
                    connected = true;
                    // A real FaceHandler can consume the posted cleanup while the
                    // provider thread is still waiting for lazy HAL initialization.
                    connectedCallback.run();
                }
                return new AidlSession();
            };
        }
        void scheduleFaceUpdateActiveUserClient(int id) {
            if (!initialized) throw new AssertionError("Sensor scheduler is not initialized");
            getLazySession().get();
            activeUser = id;
        }
    }
    static class HidlToAidlSensorAdapter extends Sensor {
        HidlToAidlSensorAdapter(FaceProvider provider, Object context, Object handler,
                SensorProps prop, Object dispatcher, Object biometricContext,
                boolean reset, Runnable callback) {
            this.provider = provider;
            sensorId = prop.commonProps.sensorId;
            connectedCallback = callback;
        }
    }
    static class SensorList {
        Map<Integer, Sensor> sensors = new HashMap<>();
        SynchronousUserSwitchObserver observer;
        Sensor get(int id) { return sensors.get(id); }
        void addSensor(int id, Sensor sensor, int user, SynchronousUserSwitchObserver observer) {
            sensors.put(id, sensor);
            this.observer = observer;
            if (user == UserHandle.USER_NULL) observer.onUserSwitching(UserHandle.USER_SYSTEM);
        }
    }
    static class FaceProvider {
        Context mContext = new Context();
        Object mHandler = new Object();
        Object mLockoutResetDispatcher = new Object();
        Object mBiometricContext = new Object();
        SensorList mFaceSensors = new SensorList();
        int cleanups;
        int featureQueries;
        String getTag() { return "FaceProvider/defaultHIDL"; }
        void scheduleInternalCleanup(int id, int user, Object callback) {
            // Execute the same dereference at the fatal FaceProvider.java:757.
            mFaceSensors.get(id).scheduleFaceUpdateActiveUserClient(user);
            cleanups++;
        }
        void scheduleGetFeature(int id, Binder token, int user, int feature,
                Object callback, String packageName) {
            if (mFaceSensors.get(id) == null) throw new AssertionError("Feature queried before registration");
            featureQueries++;
        }
@@METHOD@@
    }
    public static void main(String[] args) {
        FaceProvider provider = new FaceProvider();
        if (args[0].equals("original")) {
            try {
                provider.addHidlSensors(new SensorProps(), true);
            } catch (NullPointerException expected) {
                if (provider.mFaceSensors.get(0) != null) throw new AssertionError("Unexpected failure");
                System.out.println("Reproduced cleanup before sensor registration");
                return;
            }
            throw new AssertionError("Original source no longer reproduces the race");
        }
        provider.addHidlSensors(new SensorProps(), true);
        Sensor sensor = provider.mFaceSensors.get(0);
        if (sensor == null || !sensor.connected || sensor.activeUser != 0 || provider.cleanups < 1
                || provider.featureQueries < 1) throw new AssertionError("Startup cleanup was lost");
        int previousCleanups = provider.cleanups;
        sensor.connected = false;
        sensor.getLazySession().get();
        if (provider.cleanups <= previousCleanups) throw new AssertionError("Reconnect cleanup was lost");
        provider.mFaceSensors.observer.onUserSwitching(10);
        if (sensor.activeUser != 10) throw new AssertionError("User switch cleanup was lost");
        provider.mFaceSensors.observer.onUserSwitching(0);
        if (sensor.activeUser != 0) throw new AssertionError("Primary user cleanup was lost");
        System.out.println("PASS: registration precedes HAL cleanup; reconnect and user switches retained");
    }
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rom-root", type=Path, required=True)
    args = parser.parse_args()
    source = (args.rom_root / face_init.SOURCE).read_bytes()
    face_init.transform(source)
    face_init.validate_contract(args.rom_root)
    fixed = face_init.transform(source).decode()
    if fixed.count(face_init.FIXED_METHOD) != 1:
        raise ValueError("Fixed Java reference is ambiguous")
    # The source fixtures use the exact upstream method; the harness uses that
    # complete method with only surrounding Android types replaced by small stubs.
    original = face_init.ORIGINAL_METHOD
    patched = face_init.FIXED_METHOD
    if not shutil.which("java"):
        raise RuntimeError("Java 17 is required for the Face startup race regression")
    compiler = ["javac"] if shutil.which("javac") else [
        "java", "-m", "jdk.compiler/com.sun.tools.javac.Main"]
    with tempfile.TemporaryDirectory(prefix="face-init-java-") as directory:
        root = Path(directory)
        for name, method in (("original", original), ("fixed", patched)):
            test_root = root / name
            test_root.mkdir()
            java = test_root / "FaceRegistrationRegression.java"
            java.write_text(HARNESS.replace("@@METHOD@@", method))
            subprocess.run([*compiler, str(java)], check=True)
            subprocess.run(["java", "-cp", str(test_root), "FaceRegistrationRegression", name], check=True)


if __name__ == "__main__":
    main()
