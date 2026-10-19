// SPDX-License-Identifier: Apache-2.0
package org.hecker.suite;

import android.app.PendingIntent;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import java.lang.reflect.Field;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.util.ArrayList;
import java.util.List;

/** Adapter for Android 17's native, flag-gated App Lock. Never grants unlocks itself. */
final class NativeAppLock {
    private static final long GET_APP_LOCK_INFO = 1L << 35;
    private final PackageManager pm;
    private final Method requestChange;
    private final Field supported;
    private final Field enabled;

    NativeAppLock(PackageManager pm) throws ReflectiveOperationException {
        this.pm = pm;
        requestChange = PackageManager.class.getMethod("getEnableAppLockIntentForPackage",
                String.class, boolean.class);
        supported = ApplicationInfo.class.getField("isAppLockSupported");
        enabled = ApplicationInfo.class.getField("isAppLockEnabled");
    }

    List<ApplicationInfo> apps() throws IllegalAccessException {
        List<ApplicationInfo> result = new ArrayList<>();
        for (ApplicationInfo info : pm.getInstalledApplications(
                PackageManager.ApplicationInfoFlags.of(GET_APP_LOCK_INFO))) {
            if (supported.getBoolean(info) && !"org.hecker.suite".equals(info.packageName)) {
                result.add(info);
            }
        }
        return result;
    }

    boolean enabled(ApplicationInfo info) throws IllegalAccessException {
        return enabled.getBoolean(info);
    }

    PendingIntent change(String packageName, boolean lock) throws ReflectiveOperationException {
        try {
            return (PendingIntent) requestChange.invoke(pm, packageName, lock);
        } catch (InvocationTargetException error) {
            if (error.getCause() instanceof SecurityException) {
                throw (SecurityException) error.getCause();
            }
            throw error;
        }
    }
}
