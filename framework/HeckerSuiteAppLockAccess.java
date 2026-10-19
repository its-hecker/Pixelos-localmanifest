// SPDX-License-Identifier: Apache-2.0
package com.android.server.pm;

import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import android.os.Binder;
import android.os.UserHandle;

/** Narrow access to request the native authenticated configuration flow, never to unlock apps. */
final class HeckerSuiteAppLockAccess {
    static final String PERMISSION = "android.permission.HECKER_SUITE_APP_LOCK";
    static final String PACKAGE = "org.hecker.suite";

    private HeckerSuiteAppLockAccess() {}

    static boolean isSuite(Context context, int uid) {
        if (context.checkPermission(PERMISSION, Binder.getCallingPid(), uid)
                != PackageManager.PERMISSION_GRANTED) return false;
        try {
            PackageManager pm = context.getPackageManager();
            ApplicationInfo suite = pm.getApplicationInfoAsUser(PACKAGE, 0, UserHandle.getUserId(uid));
            return suite.uid == uid && suite.isPrivilegedApp()
                    && pm.checkSignatures("android", PACKAGE) == PackageManager.SIGNATURE_MATCH;
        } catch (PackageManager.NameNotFoundException error) {
            return false;
        }
    }
}
