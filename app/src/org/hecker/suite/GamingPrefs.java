// SPDX-License-Identifier: Apache-2.0
package org.hecker.suite;

import android.content.Context;
import android.content.SharedPreferences;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

final class GamingPrefs {
    static final String FILE = "gaming";
    static SharedPreferences get(Context c) { return c.getSharedPreferences(FILE, Context.MODE_PRIVATE); }
    static boolean enabled(Context c) { return get(c).getBoolean("enabled", false); }
    static Set<String> added(Context c) { return new HashSet<>(get(c).getStringSet("added", Set.of())); }
    static Set<String> excluded(Context c) { return new HashSet<>(get(c).getStringSet("excluded", Set.of())); }
    static List<String> shortcuts(Context c) {
        List<String> result = new ArrayList<>();
        for (String value : get(c).getString("shortcuts", "").split(",")) {
            if (!value.isEmpty() && !result.contains(value)) result.add(value);
        }
        return result;
    }
    static void toggleShortcut(Context c, String pkg) {
        List<String> values = shortcuts(c);
        if (!values.remove(pkg) && values.size() < 5) values.add(pkg);
        get(c).edit().putString("shortcuts", String.join(",", values)).apply();
    }
    static void include(Context c, String pkg, boolean include) {
        Set<String> added = added(c), excluded = excluded(c);
        if (include) { added.add(pkg); excluded.remove(pkg); }
        else { added.remove(pkg); excluded.add(pkg); }
        get(c).edit().putStringSet("added", added).putStringSet("excluded", excluded).apply();
    }
    private GamingPrefs() {}
}
