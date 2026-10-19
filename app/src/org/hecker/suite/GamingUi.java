// SPDX-License-Identifier: Apache-2.0
package org.hecker.suite;

import android.content.Context;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.Path;
import android.graphics.Shader;
import android.graphics.Typeface;
import android.graphics.drawable.Drawable;
import android.graphics.drawable.GradientDrawable;
import android.view.View;
import android.view.ViewGroup;
import android.widget.LinearLayout;
import android.widget.TextView;
import java.util.ArrayDeque;

final class GamingUi {
    static final int BG = 0xff080e14, CARD = 0xff121c27, TEXT = 0xfff3f6fb, MUTED = 0xff99a8ba;
    static int accent(Context c) { return GamingPrefs.get(c).getInt("accent", 0xff35eee3); }
    static int dp(Context c, float v) { return Math.round(v * c.getResources().getDisplayMetrics().density); }
    static GradientDrawable background(Context c, int color, int radius, boolean outline) {
        GradientDrawable d = new GradientDrawable(); d.setColor(color); d.setCornerRadius(dp(c, radius));
        if (outline) d.setStroke(dp(c, 1), Color.argb(90, Color.red(accent(c)), Color.green(accent(c)), Color.blue(accent(c))));
        return d;
    }
    static LinearLayout column(Context c) { LinearLayout v = new LinearLayout(c); v.setOrientation(LinearLayout.VERTICAL); return v; }
    static LinearLayout row(Context c) { LinearLayout v = new LinearLayout(c); v.setGravity(android.view.Gravity.CENTER_VERTICAL); return v; }
    static TextView text(Context c, CharSequence value, int sp, int color, boolean bold) {
        TextView v = new TextView(c); v.setText(value); v.setTextSize(sp); v.setTextColor(color);
        v.setFontFeatureSettings("tnum");
        v.setTypeface(Typeface.create("sans-serif", bold ? Typeface.BOLD : Typeface.NORMAL));
        return v;
    }
    static TextView button(Context c, CharSequence value, boolean selected, Runnable action) {
        TextView v = text(c, value, 14, selected ? BG : TEXT, true);
        v.setGravity(android.view.Gravity.CENTER); int p = dp(c, 12); v.setPadding(p,p,p,p);
        v.setBackground(background(c, selected ? accent(c) : CARD, 16, !selected));
        v.setMinHeight(dp(c, 48)); v.setFocusable(true); v.setOnClickListener(w -> action.run());
        return v;
    }
    static LinearLayout card(Context c) {
        LinearLayout v = column(c); int pad = dp(c, 16); v.setPadding(pad,pad,pad,pad);
        v.setBackground(background(c,CARD,22,true));
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(-1,-2); p.bottomMargin=dp(c,12); v.setLayoutParams(p);
        return v;
    }
    static void gap(LinearLayout parent, int dp) {
        View v = new View(parent.getContext()); parent.addView(v,new LinearLayout.LayoutParams(1,dp(parent.getContext(),dp)));
    }
    static void weighted(LinearLayout row, View child) { row.addView(child,new LinearLayout.LayoutParams(0,-2,1)); }

    static final class Icon extends View {
        final String type; final Paint p = new Paint(Paint.ANTI_ALIAS_FLAG); int color;
        Icon(Context c,String type,int color) { super(c); this.type=type;this.color=color;setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO); }
        @Override protected void onDraw(Canvas canvas) {
            super.onDraw(canvas); int save=canvas.save(); canvas.scale(getWidth()/24f,getHeight()/24f);
            p.setColor(color);p.setStrokeWidth(1.8f);p.setStrokeCap(Paint.Cap.ROUND);p.setStrokeJoin(Paint.Join.ROUND);p.setStyle(Paint.Style.STROKE);
            switch(type) {
                case "wifi":
                    canvas.drawArc(1,4,23,22,220,100,false,p);canvas.drawArc(5,9,19,21,220,100,false,p);
                    canvas.drawArc(9,14,15,20,220,100,false,p);canvas.drawPoint(12,20,p);break;
                case "volume":
                    Path speaker=new Path();speaker.moveTo(3,9);speaker.lineTo(7,9);speaker.lineTo(12,5);speaker.lineTo(12,19);speaker.lineTo(7,15);speaker.lineTo(3,15);speaker.close();canvas.drawPath(speaker,p);
                    canvas.drawArc(11,7,20,17,-65,130,false,p);canvas.drawArc(9,3,25,21,-58,116,false,p);break;
                case "sun":
                    canvas.drawCircle(12,12,4,p);for(int i=0;i<8;i++){double a=Math.PI*i/4;canvas.drawLine(12+(float)Math.cos(a)*8,12+(float)Math.sin(a)*8,12+(float)Math.cos(a)*10,12+(float)Math.sin(a)*10,p);}break;
                case "temperature":
                    canvas.drawRoundRect(9,2,15,17,3,3,p);canvas.drawCircle(12,18,4,p);canvas.drawLine(12,7,12,18,p);break;
                case "screenshot":
                    for(int i=0;i<4;i++){canvas.save();canvas.rotate(90*i,12,12);canvas.drawLine(3,9,3,3,p);canvas.drawLine(3,3,9,3,p);canvas.restore();}break;
                case "record": canvas.drawCircle(12,12,8,p);p.setStyle(Paint.Style.FILL);canvas.drawCircle(12,12,4,p);break;
                case "focus": canvas.drawCircle(12,12,6,p);canvas.drawCircle(12,12,2,p);for(int i=0;i<4;i++){canvas.save();canvas.rotate(i*90,12,12);canvas.drawLine(12,2,12,6,p);canvas.restore();}break;
                case "lock": canvas.drawRoundRect(5,10,19,21,2,2,p);canvas.drawArc(8,2,16,14,180,180,false,p);canvas.drawLine(12,14,12,17,p);break;
                case "clean": canvas.drawLine(10,13,19,3,p);canvas.drawLine(5,12,14,19,p);canvas.drawLine(5,12,2,19,p);canvas.drawLine(2,19,9,23,p);canvas.drawLine(9,23,14,19,p);canvas.drawLine(7,15,4,20,p);break;
                case "play": Path play=new Path();play.moveTo(7,4);play.lineTo(20,12);play.lineTo(7,20);play.close();p.setStyle(Paint.Style.FILL);canvas.drawPath(play,p);break;
                case "back": canvas.drawLine(15,4,7,12,p);canvas.drawLine(7,12,15,20,p);break;
                case "close": canvas.drawLine(5,5,19,19,p);canvas.drawLine(19,5,5,19,p);break;
                case "plus": canvas.drawLine(4,12,20,12,p);canvas.drawLine(12,4,12,20,p);break;
                default:
                    canvas.drawRoundRect(2,6,22,19,5,5,p);canvas.drawLine(6,12,12,12,p);canvas.drawLine(9,9,9,15,p);canvas.drawPoint(17,11,p);canvas.drawPoint(19,14,p);
            }
            canvas.restoreToCount(save);
        }
    }
    static final class Chart extends View {
        private final ArrayDeque<Float> points=new ArrayDeque<>();
        private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
        Chart(Context c){super(c);setContentDescription(c.getString(R.string.gaming_fps_history));}
        void sample(float fps){points.addLast(fps);while(points.size()>32)points.removeFirst();invalidate();}
        void clear(){points.clear();invalidate();}
        @Override protected void onDraw(Canvas c){
            super.onDraw(c);if(points.size()<2)return;
            float max=30;for(float f:points)if(Float.isFinite(f))max=Math.max(max,f);
            Path path=new Path();int i=0;boolean open=false;
            for(float value:points){float x=i++*getWidth()/(float)(points.size()-1);
                if(!Float.isFinite(value)){open=false;continue;}float y=getHeight()-dp(getContext(),2)-value/max*(getHeight()-dp(getContext(),4));
                if(!open)path.moveTo(x,y);else path.lineTo(x,y);open=true;}
            paint.setColor(accent(getContext()));paint.setStrokeWidth(dp(getContext(),2));paint.setStyle(Paint.Style.STROKE);c.drawPath(path,paint);
        }
    }
    /** Original procedural art uses the installed app's own icon, never a fake game/banner download. */
    static final class Banner extends View {
        final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);final Drawable icon;final boolean hero;
        Banner(Context c,Drawable icon,boolean hero){super(c);this.icon=icon;this.hero=hero;setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);}
        @Override protected void onDraw(Canvas canvas){
            super.onDraw(canvas);float w=getWidth(),h=getHeight();
            paint.setShader(new LinearGradient(0,0,w,h,new int[]{0xff153c4c,0xff202045,0xff080e14},null,Shader.TileMode.CLAMP));canvas.drawRoundRect(0,0,w,h,dp(getContext(),18),dp(getContext(),18),paint);paint.setShader(null);
            paint.setColor(accent(getContext()));paint.setAlpha(65);paint.setStyle(Paint.Style.STROKE);paint.setStrokeWidth(dp(getContext(),1));
            for(int i=0;i<7;i++)canvas.drawLine(w*.2f+i*w*.13f,0,w*.03f+i*w*.14f,h,paint);
            canvas.drawOval(w*.38f,h*.07f,w*.96f,h*.88f,paint);canvas.drawOval(w*.32f,h*.18f,w,h*.75f,paint);
            paint.setStyle(Paint.Style.FILL);paint.setAlpha(255);
            if(icon!=null){int s=(int)Math.min(h*.53f,w*.3f);int left=(int)(w*.65f-s*.5f),top=(int)((h-s)*.45f);icon.setBounds(left,top,left+s,top+s);icon.draw(canvas);}
        }
    }
    private GamingUi(){}
}
