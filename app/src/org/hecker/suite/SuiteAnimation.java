// SPDX-License-Identifier: Apache-2.0
package org.hecker.suite;

import android.animation.ValueAnimator;
import android.app.Activity;
import android.view.Gravity;
import android.view.ViewGroup;
import android.widget.LinearLayout;
import com.airbnb.lottie.LottieAnimationView;

/** Small, original Lottie assets; system authentication is never driven by animation state. */
final class SuiteAnimation {
    private final LottieAnimationView view;

    SuiteAnimation(Activity activity, LinearLayout parent) {
        view = new LottieAnimationView(activity);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, Ui.dp(activity, 156));
        params.gravity = Gravity.CENTER;
        view.setLayoutParams(params);
        view.setImportantForAccessibility(android.view.View.IMPORTANT_FOR_ACCESSIBILITY_NO);
        parent.addView(view);
        show(R.raw.suite_scan, true);
    }

    void show(int animation, boolean repeat) {
        view.cancelAnimation();
        view.setAnimation(animation);
        view.setRepeatCount(repeat ? ValueAnimator.INFINITE : 0);
        if (ValueAnimator.areAnimatorsEnabled()) view.playAnimation();
        else view.setProgress(1f);
    }

    void stop() { view.cancelAnimation(); }
}
