// SPDX-License-Identifier: Apache-2.0
package com.android.server.pm;

import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;

public final class HeckerSuiteAccessTest {
    private static int checks;
    private static final class Packages extends PackageManager {
        final ApplicationInfo suite = new ApplicationInfo();
        int signature;
        boolean missing;
        int queriedUser = -1;
        public ApplicationInfo getApplicationInfoAsUser(String name, int flags, int user)
                throws NameNotFoundException {
            if (!"org.hecker.suite".equals(name)) throw new AssertionError("Wrong package");
            queriedUser = user;
            if (missing) throw new NameNotFoundException();
            return suite;
        }
        public int checkSignatures(String one, String two) {
            if (!"android".equals(one) || !"org.hecker.suite".equals(two)) {
                throw new AssertionError("Wrong signature identity");
            }
            return signature;
        }
    }
    private static final class Caller extends Context {
        final Packages packages = new Packages();
        int permission;
        public int checkPermission(String name, int pid, int uid) {
            if (!"android.permission.HECKER_SUITE_APP_LOCK".equals(name)) {
                throw new AssertionError("Wrong permission");
            }
            return permission;
        }
        public PackageManager getPackageManager() { return packages; }
    }
    private static void check(boolean condition) {
        checks++;
        if (!condition) throw new AssertionError("Access boundary regression");
    }
    public static void main(String[] args) {
        Caller caller = new Caller();
        caller.packages.suite.uid = 1012345;
        caller.packages.suite.privileged = true;
        check(HeckerSuiteAppLockAccess.isSuite(caller, 1012345));
        check(caller.packages.queriedUser == 10);
        check(!HeckerSuiteAppLockAccess.isSuite(caller, 1012346));
        caller.permission = -1;
        check(!HeckerSuiteAppLockAccess.isSuite(caller, 1012345));
        caller.permission = 0;
        caller.packages.signature = -1;
        check(!HeckerSuiteAppLockAccess.isSuite(caller, 1012345));
        caller.packages.signature = 0;
        caller.packages.suite.privileged = false;
        check(!HeckerSuiteAppLockAccess.isSuite(caller, 1012345));
        caller.packages.suite.privileged = true;
        caller.packages.missing = true;
        check(!HeckerSuiteAppLockAccess.isSuite(caller, 1012345));
        System.out.println("Suite caller authorization: " + checks + " checks passed");
    }
}
