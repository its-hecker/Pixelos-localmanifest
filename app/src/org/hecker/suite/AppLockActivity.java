// SPDX-License-Identifier: Apache-2.0
package org.hecker.suite;

import android.app.Activity;
import android.app.AlertDialog;
import android.app.KeyguardManager;
import android.app.PendingIntent;
import android.content.Intent;
import android.content.pm.ApplicationInfo;
import android.hardware.biometrics.BiometricManager;
import android.hardware.biometrics.BiometricPrompt;
import android.os.Bundle;
import android.os.CancellationSignal;
import android.provider.Settings;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.MenuItem;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;
import java.text.Collator;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class AppLockActivity extends Activity {
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private final List<ApplicationInfo> apps = new ArrayList<>();
    private NativeAppLock nativeLock;
    private LinearLayout list;
    private EditText search;
    private TextView summary;
    private SuiteAnimation animation;
    private CancellationSignal cancellation;
    private boolean authenticated;
    private boolean started;
    private int generation;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        getWindow().setHideOverlayWindows(true);
        LinearLayout page = Ui.page(this, R.string.app_lock_title);
        LinearLayout hero = Ui.card(this);
        animation = new SuiteAnimation(this, hero);
        summary = Ui.text(this, getString(R.string.authenticate_subtitle), 18, true);
        hero.addView(summary);
        hero.addView(Ui.text(this, getString(R.string.app_lock_native_behavior), 14, false));
        page.addView(hero);
        search = new EditText(this);
        search.setHint(R.string.search_apps);
        search.setSingleLine(true);
        search.setEnabled(false);
        page.addView(search);
        list = new LinearLayout(this);
        list.setOrientation(LinearLayout.VERTICAL);
        page.addView(list);
        Ui.scroll(this, page);
        search.addTextChangedListener(new TextWatcher() {
            public void beforeTextChanged(CharSequence s, int st, int c, int a) {}
            public void onTextChanged(CharSequence s, int st, int b, int c) {
                if (authenticated) render();
            }
            public void afterTextChanged(Editable e) {}
        });
        try { nativeLock = new NativeAppLock(getPackageManager()); }
        catch (ReflectiveOperationException error) {
            summary.setText(R.string.app_lock_unavailable);
        }
    }

    @Override protected void onStart() {
        super.onStart();
        started = true;
        authenticated = false;
        list.removeAllViews();
        search.setEnabled(false);
        if (nativeLock == null) return;
        KeyguardManager keyguard = getSystemService(KeyguardManager.class);
        if (!keyguard.isDeviceSecure()) {
            new AlertDialog.Builder(this).setTitle(R.string.screen_lock_needed)
                    .setMessage(R.string.screen_lock_needed_body)
                    .setPositiveButton(R.string.set_screen_lock, (d, w) ->
                            startActivity(new Intent(Settings.ACTION_SECURITY_SETTINGS)))
                    .setNegativeButton(R.string.cancel, (d, w) -> finish())
                    .setOnCancelListener(d -> finish()).show();
            return;
        }
        authenticate();
    }

    private void authenticate() {
        final int request = ++generation;
        animation.show(R.raw.suite_scan, true);
        summary.setText(R.string.authenticate_subtitle);
        cancellation = new CancellationSignal();
        new BiometricPrompt.Builder(this)
                .setTitle(getString(R.string.authenticate_title))
                .setSubtitle(getString(R.string.authenticate_subtitle))
                .setAllowedAuthenticators(BiometricManager.Authenticators.BIOMETRIC_STRONG
                        | BiometricManager.Authenticators.DEVICE_CREDENTIAL)
                .setConfirmationRequired(false).build()
                .authenticate(cancellation, getMainExecutor(), new BiometricPrompt.AuthenticationCallback() {
                    @Override public void onAuthenticationSucceeded(BiometricPrompt.AuthenticationResult r) {
                        if (!started || request != generation) return;
                        authenticated = true;
                        animation.show(R.raw.suite_success, false);
                        search.setEnabled(true);
                        loadApps(request);
                    }
                    @Override public void onAuthenticationFailed() {
                        if (started && request == generation) animation.show(R.raw.suite_failure, false);
                    }
                    @Override public void onAuthenticationError(int code, CharSequence message) {
                        if (!started || request != generation) return;
                        Toast.makeText(AppLockActivity.this, message, Toast.LENGTH_SHORT).show();
                        finish();
                    }
                });
    }

    private void loadApps(int request) {
        summary.setText(R.string.app_lock_loading);
        worker.execute(() -> {
            try {
                List<ApplicationInfo> loaded = nativeLock.apps();
                Collator collator = Collator.getInstance();
                loaded.sort((a, b) -> collator.compare(a.loadLabel(getPackageManager()).toString(),
                        b.loadLabel(getPackageManager()).toString()));
                runOnUiThread(() -> {
                    if (!started || !authenticated || request != generation) return;
                    apps.clear(); apps.addAll(loaded); render();
                });
            } catch (ReflectiveOperationException | SecurityException error) {
                runOnUiThread(() -> {
                    if (started && request == generation) summary.setText(R.string.app_lock_unavailable);
                });
            }
        });
    }

    private void render() {
        list.removeAllViews();
        String query = search.getText().toString().trim().toLowerCase(Locale.ROOT);
        int count = 0;
        for (ApplicationInfo info : apps) {
            final boolean locked;
            try { locked = nativeLock.enabled(info); }
            catch (IllegalAccessException error) { continue; }
            if (locked) count++;
            String label = info.loadLabel(getPackageManager()).toString();
            if (!(label + " " + info.packageName).toLowerCase(Locale.ROOT).contains(query)) continue;
            LinearLayout row = Ui.card(this);
            row.setOrientation(LinearLayout.HORIZONTAL);
            row.setGravity(android.view.Gravity.CENTER_VERTICAL);
            ImageView icon = new ImageView(this);
            icon.setImageDrawable(info.loadIcon(getPackageManager()));
            icon.setImportantForAccessibility(android.view.View.IMPORTANT_FOR_ACCESSIBILITY_NO);
            row.addView(icon, new LinearLayout.LayoutParams(Ui.dp(this, 40), Ui.dp(this, 40)));
            LinearLayout labels = new LinearLayout(this);
            labels.setOrientation(LinearLayout.VERTICAL);
            labels.setPadding(Ui.dp(this, 12), 0, Ui.dp(this, 12), 0);
            labels.addView(Ui.text(this, label, 17, true));
            labels.addView(Ui.text(this, info.packageName, 12, false));
            row.addView(labels, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
            Switch toggle = new Switch(this);
            toggle.setChecked(locked);
            toggle.setContentDescription(label);
            // The native system flow authenticates and performs the change. Never optimistically
            // claim that protection changed just because this switch was touched.
            toggle.setOnClickListener(v -> { toggle.setChecked(locked); change(info, !locked); });
            row.addView(toggle);
            row.setOnClickListener(v -> change(info, !locked));
            list.addView(row);
        }
        summary.setText(getString(R.string.app_lock_count, count, apps.size()));
        if (list.getChildCount() == 0) list.addView(Ui.text(this, getString(R.string.app_lock_empty), 16, false));
    }

    private void change(ApplicationInfo info, boolean enabled) {
        if (!authenticated || !started) return;
        try {
            PendingIntent intent = nativeLock.change(info.packageName, enabled);
            if (intent == null) {
                Toast.makeText(this, R.string.app_lock_change_unavailable, Toast.LENGTH_SHORT).show();
                loadApps(generation);
            } else {
                // Sender BAL permission is granted only for this explicit, foreground user action.
                android.app.ActivityOptions options = android.app.ActivityOptions.makeBasic();
                options.setPendingIntentBackgroundActivityStartMode(
                        android.app.ActivityOptions.MODE_BACKGROUND_ACTIVITY_START_ALLOWED);
                intent.send(this, 0, null, null, null, null, options.toBundle());
            }
        } catch (ReflectiveOperationException | PendingIntent.CanceledException | SecurityException error) {
            Toast.makeText(this, R.string.app_lock_change_unavailable, Toast.LENGTH_SHORT).show();
        }
    }

    @Override protected void onStop() {
        started = false;
        authenticated = false;
        generation++;
        if (cancellation != null) cancellation.cancel();
        animation.stop();
        list.removeAllViews();
        apps.clear();
        super.onStop();
    }
    @Override protected void onDestroy() { worker.shutdownNow(); super.onDestroy(); }
    @Override public boolean onOptionsItemSelected(MenuItem item) {
        if (item.getItemId() == android.R.id.home) { finish(); return true; }
        return super.onOptionsItemSelected(item);
    }
}
