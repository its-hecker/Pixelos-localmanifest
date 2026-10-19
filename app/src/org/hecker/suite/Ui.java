// SPDX-License-Identifier: Apache-2.0
package org.hecker.suite;

import android.app.Activity;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.util.TypedValue;
import android.view.View;
import android.view.ViewGroup;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

final class Ui {
    private Ui() {}

    static int dp(Activity activity, int value) {
        return Math.round(value * activity.getResources().getDisplayMetrics().density);
    }

    static LinearLayout page(Activity activity, int title) {
        activity.setTitle(title);
        if (activity.getActionBar() != null) {
            activity.getActionBar().setDisplayHomeAsUpEnabled(true);
        }
        LinearLayout page = new LinearLayout(activity);
        page.setOrientation(LinearLayout.VERTICAL);
        int padding = dp(activity, 20);
        page.setPadding(padding, padding, padding, padding);
        // Android 17 enforces edge-to-edge. Consume system bars around the content.
        page.setOnApplyWindowInsetsListener((view, insets) -> {
            android.graphics.Insets bars = insets.getInsets(
                    android.view.WindowInsets.Type.systemBars()
                    | android.view.WindowInsets.Type.displayCutout());
            view.setPadding(padding + bars.left, padding,
                    padding + bars.right, padding + bars.bottom);
            return insets;
        });
        return page;
    }

    static void scroll(Activity activity, LinearLayout page) {
        ScrollView scroll = new ScrollView(activity);
        scroll.setFillViewport(true);
        scroll.addView(page);
        activity.setContentView(scroll);
    }

    static TextView text(Activity activity, CharSequence text, int sp, boolean bold) {
        TextView view = new TextView(activity);
        view.setText(text);
        view.setTextSize(sp);
        if (bold) view.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        view.setPadding(0, dp(activity, 6), 0, dp(activity, 6));
        return view;
    }

    static LinearLayout card(Activity activity) {
        LinearLayout card = new LinearLayout(activity);
        card.setOrientation(LinearLayout.VERTICAL);
        int pad = dp(activity, 18);
        card.setPadding(pad, pad, pad, pad);
        GradientDrawable background = new GradientDrawable();
        TypedValue value = new TypedValue();
        activity.getTheme().resolveAttribute(android.R.attr.colorBackgroundFloating, value, true);
        background.setColor(value.data);
        background.setCornerRadius(dp(activity, 24));
        card.setBackground(background);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.bottomMargin = dp(activity, 16);
        card.setLayoutParams(lp);
        return card;
    }

    static void actionCard(Activity activity, LinearLayout page, int title, int summary,
            View.OnClickListener action) {
        LinearLayout card = card(activity);
        card.addView(text(activity, activity.getString(title), 22, true));
        card.addView(text(activity, activity.getString(summary), 15, false));
        TypedValue selectable = new TypedValue();
        activity.getTheme().resolveAttribute(android.R.attr.selectableItemBackground,
                selectable, true);
        card.setForeground(activity.getDrawable(selectable.resourceId));
        card.setFocusable(true);
        card.setClickable(true);
        card.setOnClickListener(action);
        page.addView(card);
    }
}
