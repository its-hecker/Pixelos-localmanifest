// SPDX-License-Identifier: Apache-2.0
package org.hecker.suite;

import android.content.Context;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.content.pm.PackageManager;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Set;

final class GamingCatalog {
    static final class App {
        final ApplicationInfo info;
        final String label;
        final boolean game;
        App(ApplicationInfo info, String label, boolean game) {
            this.info = info; this.label = label; this.game = game;
        }
    }
    static List<App> load(Context c, boolean gamesOnly) {
        PackageManager pm = c.getPackageManager();
        Set<String> added = GamingPrefs.added(c), excluded = GamingPrefs.excluded(c);
        boolean automatic = GamingPrefs.get(c).getBoolean("automatic", true);
        List<App> result = new ArrayList<>();
        for (ApplicationInfo app : pm.getInstalledApplications(PackageManager.ApplicationInfoFlags.of(0))) {
            if (!app.enabled || app.packageName.equals(c.getPackageName())
                    || pm.getLaunchIntentForPackage(app.packageName) == null) continue;
            boolean tagged = app.category == ApplicationInfo.CATEGORY_GAME
                    || (app.flags & ApplicationInfo.FLAG_IS_GAME) != 0;
            boolean game = GamingPolicy.isGame(app.packageName, tagged, automatic, added, excluded);
            if (!gamesOnly || game) result.add(new App(app, app.loadLabel(pm).toString(), game));
        }
        result.sort(Comparator.comparing(a -> a.label, String.CASE_INSENSITIVE_ORDER));
        return result;
    }
    static String label(Context c, String pkg) {
        try { return c.getPackageManager().getApplicationInfo(pkg, 0).loadLabel(c.getPackageManager()).toString(); }
        catch (PackageManager.NameNotFoundException e) { return pkg; }
    }
    static Intent launch(Context c, String pkg) {
        Intent intent = c.getPackageManager().getLaunchIntentForPackage(pkg);
        if (intent != null) intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        return intent;
    }
    private GamingCatalog() {}
}
