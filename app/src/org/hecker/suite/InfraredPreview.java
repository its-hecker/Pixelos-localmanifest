// SPDX-License-Identifier: Apache-2.0
package org.hecker.suite;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.view.View;

final class InfraredPreview extends View {
    private final Paint paint = new Paint(Paint.FILTER_BITMAP_FLAG);
    private Bitmap frame;
    private int rotation;

    InfraredPreview(Context context) {
        super(context);
        setBackgroundColor(Color.BLACK);
        setContentDescription(context.getString(R.string.ir_preview));
    }

    void frame(Bitmap bitmap, int degrees) { frame = bitmap; rotation = degrees; invalidate(); }
    void clear() { frame = null; invalidate(); }

    @Override protected void onDraw(Canvas canvas) {
        super.onDraw(canvas);
        if (frame == null || frame.isRecycled()) return;
        boolean sideways = rotation % 180 != 0;
        float width = sideways ? frame.getHeight() : frame.getWidth();
        float height = sideways ? frame.getWidth() : frame.getHeight();
        float scale = Math.min(getWidth() / width, getHeight() / height);
        canvas.save();
        canvas.translate(getWidth() / 2f, getHeight() / 2f);
        canvas.scale(-scale, scale); // Natural mirror view for the front IR sensor.
        canvas.rotate(rotation);
        canvas.drawBitmap(frame, -frame.getWidth() / 2f, -frame.getHeight() / 2f, paint);
        canvas.restore();
    }
}
