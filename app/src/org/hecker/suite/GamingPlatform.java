// SPDX-License-Identifier: Apache-2.0
package org.hecker.suite;

import android.app.ActivityManager;
import android.app.ActivityOptions;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ActivityInfo;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.graphics.Rect;
import android.hardware.display.DisplayManager;
import android.os.Process;
import android.provider.Settings;
import android.view.WindowManager;
import java.util.HashSet;
import java.util.Set;

/** Hidden calls are isolated; the prepare step checks their real framework declarations. */
final class GamingPlatform {
    static boolean ownDisplayTask(ActivityManager.RunningTaskInfo task) {
        try {
            return task.getClass().getField("displayId").getInt(task) == 0
                    && task.getClass().getField("userId").getInt(task) == Process.myUid() / 100000;
        } catch (ReflectiveOperationException e) { return false; }
    }
    static boolean freeform(ActivityManager.RunningTaskInfo task) {
        try { return (boolean) task.getClass().getMethod("isFreeform").invoke(task); }
        catch (ReflectiveOperationException e) { return false; }
    }
    static boolean supportsPopup(Context c, Intent launch) {
        if (!c.getPackageManager().hasSystemFeature("android.software.freeform_window_management")) return false;
        try {
            ActivityInfo info = c.getPackageManager().getActivityInfo(launch.getComponent(), 0);
            int mode = ActivityInfo.class.getField("resizeMode").getInt(info);
            return (boolean) ActivityInfo.class.getMethod("isResizeableMode", int.class).invoke(null, mode);
        } catch (ReflectiveOperationException | PackageManager.NameNotFoundException | NullPointerException e) {
            return false;
        }
    }
    static void popup(Context c, Intent launch) throws ReflectiveOperationException {
        if (!supportsPopup(c, launch)) throw new IllegalArgumentException("This app does not support floating windows");
        Rect screen = c.getSystemService(WindowManager.class).getCurrentWindowMetrics().getBounds();
        int width = Math.min(screen.width() * (screen.width() > screen.height() ? 46 : 88) / 100,
                screen.height() * 80 / 100);
        int height = Math.min(screen.height() * 86 / 100, width * 16 / 10);
        int left = screen.left + (screen.width() - width) / 2;
        int top = screen.top + (screen.height() - height) / 2;
        ActivityOptions options = ActivityOptions.makeBasic();
        ActivityOptions.class.getMethod("setLaunchWindowingMode", int.class).invoke(options, 5);
        ActivityOptions.class.getMethod("setTaskAlwaysOnTop", boolean.class).invoke(options, true);
        options.setLaunchBounds(new Rect(left, top, left + width, top + height));
        // NEW_TASK keeps the shortcut out of the game's activity stack. No embedded ActivityView.
        launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        c.startActivity(launch, options.toBundle());
    }
    static void brightness(Context c, float value) throws ReflectiveOperationException {
        DisplayManager.class.getMethod("setTemporaryBrightness", int.class, float.class)
                .invoke(c.getSystemService(DisplayManager.class), 0, value);
    }
    static int clean(Context c, String game) {
        ActivityManager am = c.getSystemService(ActivityManager.class);
        Set<Integer> protectedUids = new HashSet<>();
        Set<String> protectedPackages = new HashSet<>(GamingPrefs.shortcuts(c));
        protectedPackages.add(game); protectedPackages.add(c.getPackageName());
        Intent home = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME);
        android.content.pm.ResolveInfo launcher = c.getPackageManager().resolveActivity(home, 0);
        if (launcher != null && launcher.activityInfo != null) protectedPackages.add(launcher.activityInfo.packageName);
        String ime = Settings.Secure.getString(c.getContentResolver(), Settings.Secure.DEFAULT_INPUT_METHOD);
        if (ime != null && ime.contains("/")) protectedPackages.add(ime.substring(0, ime.indexOf('/')));
        for (String pkg : protectedPackages) {
            try { protectedUids.add(c.getPackageManager().getApplicationInfo(pkg, 0).uid); }
            catch (PackageManager.NameNotFoundException ignored) { }
        }
        Set<String> candidates = new HashSet<>();
        java.util.List<ActivityManager.RunningAppProcessInfo> processes = am.getRunningAppProcesses();
        if (processes == null) return 0;
        Set<Integer> systemUids = new HashSet<>();
        // Protect the complete UID if any sibling process owns an active service.
        // killBackgroundProcesses acts on a package, rather than one selected PID.
        for (ActivityManager.RunningAppProcessInfo process : processes) {
            if (process.importance < ActivityManager.RunningAppProcessInfo.IMPORTANCE_CACHED) protectedUids.add(process.uid);
            if (process.pkgList == null) { protectedUids.add(process.uid); continue; }
            boolean system = false;
            for (String pkg : process.pkgList) {
                try {
                    ApplicationInfo info = c.getPackageManager().getApplicationInfo(pkg, 0);
                    system |= (info.flags & (ApplicationInfo.FLAG_SYSTEM | ApplicationInfo.FLAG_PERSISTENT)) != 0;
                } catch (PackageManager.NameNotFoundException e) { system = true; }
            }
            if (system) systemUids.add(process.uid);
        }
        for (ActivityManager.RunningAppProcessInfo process : processes) {
            if (process.pkgList == null) continue;
            if (GamingPolicy.canClean(process.uid, Process.myUid(), process.importance, systemUids.contains(process.uid), protectedUids)) {
                for (String pkg : process.pkgList) if (!protectedPackages.contains(pkg)) candidates.add(pkg);
            }
        }
        for (String pkg : candidates) am.killBackgroundProcesses(pkg);
        return candidates.size();
    }
    private GamingPlatform() {}
}
