// SPDX-License-Identifier: Apache-2.0
package org.hecker.suite;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.view.MenuItem;
import android.widget.LinearLayout;

public final class SuiteActivity extends Activity {
    private SuiteAnimation animation;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        LinearLayout page = Ui.page(this, R.string.suite_title);
        LinearLayout hero = Ui.card(this);
        animation = new SuiteAnimation(this, hero);
        hero.addView(Ui.text(this, getString(R.string.suite_intro), 24, true));
        page.addView(hero);
        Ui.actionCard(this, page, R.string.app_lock_title, R.string.app_lock_summary,
                v -> startActivity(new Intent(this, AppLockActivity.class)));
        Ui.actionCard(this, page, R.string.ir_title, R.string.ir_summary,
                v -> startActivity(new Intent(this, InfraredCameraActivity.class)));
        page.addView(Ui.text(this, getString(R.string.credit), 13, false));
        Ui.scroll(this, page);
    }

    @Override protected void onStart() {
        super.onStart();
        if (animation != null) animation.show(R.raw.suite_scan, true);
    }
    @Override protected void onStop() {
        if (animation != null) animation.stop();
        super.onStop();
    }
    @Override public boolean onOptionsItemSelected(MenuItem item) {
        if (item.getItemId() == android.R.id.home) { finish(); return true; }
        return super.onOptionsItemSelected(item);
    }
}
