// SPDX-License-Identifier: Apache-2.0
package org.hecker.suite;

import android.content.Context;
import android.content.pm.PackageManager;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.graphics.Rect;
import android.hardware.display.DisplayManager;
import android.media.AudioManager;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.SeekBar;
import android.widget.TextView;
import java.util.List;

final class GamingOverlay {
    interface Actions {
        void panelChanged(boolean open);
        void clean();void screenshot();void record();void focus();void internet();
        void shortcut(String pkg);void chooseShortcuts();void toggleShortcut(String pkg);
        void brightness(float brightness);
    }
    private final Context c;
    private final WindowManager wm;
    private final Actions actions;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private View handle,panel,touchLock;
    private TextView hud,fpsText,tempText,batteryText,wifiText,recordText;
    private GamingUi.Chart chart;
    private WindowManager.LayoutParams hudParams;
    private String fps="—",temperature="—",battery="—",wifi="—";
    private boolean visible,open,captureHidden,compact;
    private List<GamingCatalog.App> picker;
    private final Runnable unlock=this::unlock;

    GamingOverlay(Context context,Actions actions){
        Context display=context.createDisplayContext(context.getSystemService(DisplayManager.class).getDisplay(0));
        c=display.createWindowContext(WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,null);
        wm=c.getSystemService(WindowManager.class);this.actions=actions;
    }
    boolean isOpen(){return open;}
    private int dp(float value){return GamingUi.dp(c,value);}
    private WindowManager.LayoutParams params(int width,int height,boolean focusable){
        WindowManager.LayoutParams p=new WindowManager.LayoutParams(width,height,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL|WindowManager.LayoutParams.FLAG_WATCH_OUTSIDE_TOUCH
                |(focusable?0:WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE),PixelFormat.TRANSLUCENT);
        p.setTitle("Hecker Gaming");p.gravity=Gravity.RIGHT|Gravity.CENTER_VERTICAL;
        return p;
    }
    void show(){
        if(visible)return;visible=true;
        try{buildHandle();if(GamingPrefs.get(c).getBoolean("fps",true))buildHud();}
        catch(RuntimeException e){hide();throw e;}
    }
    void hide(){
        visible=false;captureHidden=false;closePanel();unlock();remove(handle);remove(hud);handle=null;hud=null;
    }
    void restyle(){
        boolean wasVisible=visible,wasOpen=open;List<GamingCatalog.App> oldPicker=picker;
        hide();if(wasVisible){show();if(wasOpen){openPanel();if(oldPicker!=null)showShortcutPicker(oldPicker);}}
    }
    private void buildHandle(){
        View v=new View(c);v.setBackground(GamingUi.background(c,GamingUi.accent(c),8,false));
        v.setContentDescription(c.getString(R.string.gaming_open_dashboard));v.setFocusable(true);v.setOnClickListener(w->openPanel());
        v.setOnTouchListener(new View.OnTouchListener(){float down;
            public boolean onTouch(View view,MotionEvent e){if(e.getActionMasked()==MotionEvent.ACTION_DOWN){down=e.getRawX();return true;}
                if(e.getActionMasked()==MotionEvent.ACTION_MOVE&&Math.abs(e.getRawX()-down)>dp(12)){openPanel();return true;}
                if(e.getActionMasked()==MotionEvent.ACTION_UP){view.performClick();return true;}return true;}});
        WindowManager.LayoutParams p=params(dp(10),dp(66),false);p.x=dp(7);
        if(GamingPrefs.get(c).getBoolean("left",false))p.gravity=Gravity.LEFT|Gravity.CENTER_VERTICAL;
        wm.addView(v,p);handle=v;
    }
    private void buildHud(){
        hud=GamingUi.text(c,"",16,GamingUi.TEXT,true);hud.setPadding(dp(14),dp(10),dp(14),dp(10));
        hud.setBackground(GamingUi.background(c,0xee101b25,28,true));hud.setFocusable(true);
        hud.setContentDescription(c.getString(R.string.gaming_open_dashboard));
        Rect screen=wm.getMaximumWindowMetrics().getBounds();hudParams=params(-2,-2,false);hudParams.gravity=Gravity.LEFT|Gravity.TOP;
        hudParams.x=Math.round(GamingPrefs.get(c).getFloat("hud_x",.06f)*Math.max(0,screen.width()-dp(210)));
        hudParams.y=dp(32)+Math.round(GamingPrefs.get(c).getFloat("hud_y",.18f)*Math.max(0,screen.height()-dp(100)));
        hud.setOnClickListener(v->openPanel());
        hud.setOnTouchListener(new View.OnTouchListener(){float x,y;int px,py;boolean moved;
            public boolean onTouch(View view,MotionEvent e){
                if(e.getActionMasked()==MotionEvent.ACTION_DOWN){x=e.getRawX();y=e.getRawY();px=hudParams.x;py=hudParams.y;moved=false;return true;}
                if(e.getActionMasked()==MotionEvent.ACTION_MOVE&&e.getEventTime()-e.getDownTime()>250){
                    if(Math.abs(e.getRawX()-x)+Math.abs(e.getRawY()-y)>dp(8))moved=true;
                    if(moved){hudParams.x=Math.max(0,Math.min(screen.width()-view.getWidth(),px+(int)(e.getRawX()-x)));
                        hudParams.y=Math.max(dp(24),Math.min(screen.height()-view.getHeight()-dp(24),py+(int)(e.getRawY()-y)));wm.updateViewLayout(view,hudParams);}return true;
                }
                if(e.getActionMasked()==MotionEvent.ACTION_UP){if(!moved)view.performClick();else GamingPrefs.get(c).edit()
                    .putFloat("hud_x",hudParams.x/(float)Math.max(1,screen.width()-dp(210)))
                    .putFloat("hud_y",(hudParams.y-dp(32))/(float)Math.max(1,screen.height()-dp(100))).apply();return true;}
                return true;
            }});
        wm.addView(hud,hudParams);update(fps,temperature,battery,wifi);
    }
    void openPanel(){
        if(!visible||open||captureHidden)return;open=true;picker=null;
        LinearLayout shell=new LinearLayout(c){@Override public boolean dispatchKeyEvent(KeyEvent e){
            if(e.getKeyCode()==KeyEvent.KEYCODE_BACK){if(e.getAction()==KeyEvent.ACTION_UP)closePanel();return true;}return super.dispatchKeyEvent(e);}};
        int alpha=Math.round(GamingPrefs.get(c).getInt("opacity",94)*2.55f);
        shell.setBackground(GamingUi.background(c,Color.argb(alpha,12,22,32),24,true));shell.setPadding(dp(7),dp(10),dp(10),dp(10));shell.setFocusableInTouchMode(true);
        shell.setOnTouchListener((v,e)->{if(e.getActionMasked()==MotionEvent.ACTION_OUTSIDE){closePanel();return true;}return false;});
        LinearLayout rail=GamingUi.column(c);rail.setGravity(Gravity.TOP|Gravity.CENTER_HORIZONTAL);rail.setPadding(0,dp(4),dp(8),0);
        for(String pkg:GamingPrefs.shortcuts(c)){
            try{ImageView icon=new ImageView(c);icon.setImageDrawable(c.getPackageManager().getApplicationIcon(pkg));icon.setPadding(dp(6),dp(6),dp(6),dp(6));
                icon.setContentDescription(c.getString(R.string.gaming_open_popup,GamingCatalog.label(c,pkg)));icon.setFocusable(true);icon.setBackground(GamingUi.background(c,GamingUi.CARD,30,false));
                icon.setOnClickListener(v->{closePanel();actions.shortcut(pkg);});rail.addView(icon,new LinearLayout.LayoutParams(dp(46),dp(46)));GamingUi.gap(rail,8);
            }catch(PackageManager.NameNotFoundException ignored){}
        }
        View add=iconButton("plus",R.string.gaming_shortcuts,()->actions.chooseShortcuts());rail.addView(add,new LinearLayout.LayoutParams(dp(46),dp(46)));shell.addView(rail);
        ScrollView scroll=new ScrollView(c);LinearLayout main=GamingUi.column(c);scroll.addView(main);shell.addView(scroll,new LinearLayout.LayoutParams(0,-1,1));
        buildTools(main);
        Rect screen=wm.getMaximumWindowMetrics().getBounds();int width=Math.min(dp(410),screen.width()-dp(28));
        WindowManager.LayoutParams p=params(width,Math.max(dp(200),screen.height()-dp(32)),true);p.x=dp(12);
        if(GamingPrefs.get(c).getBoolean("left",false))p.gravity=Gravity.LEFT|Gravity.CENTER_VERTICAL;
        try{wm.addView(shell,p);panel=shell;shell.requestFocus();if(hud!=null)hud.setVisibility(View.GONE);actions.panelChanged(true);}
        catch(RuntimeException e){open=false;throw e;}
    }
    private View iconButton(String icon,int title,Runnable action){
        FrameLayout v=new FrameLayout(c);GamingUi.Icon image=new GamingUi.Icon(c,icon,GamingUi.accent(c));
        FrameLayout.LayoutParams ip=new FrameLayout.LayoutParams(dp(23),dp(23),Gravity.CENTER);v.addView(image,ip);
        v.setContentDescription(c.getString(title));v.setBackground(GamingUi.background(c,GamingUi.CARD,22,true));v.setFocusable(true);v.setOnClickListener(w->action.run());return v;
    }
    private void buildTools(LinearLayout main){
        compact=wm.getMaximumWindowMetrics().getBounds().height()<dp(480);
        LinearLayout heading=GamingUi.row(c);GamingUi.weighted(heading,GamingUi.text(c,c.getString(R.string.gaming_title),18,GamingUi.TEXT,true));
        heading.addView(iconButton("close",R.string.gaming_close_dashboard,this::closePanel),new LinearLayout.LayoutParams(dp(compact?32:36),dp(compact?32:36)));main.addView(heading);GamingUi.gap(main,6);
        LinearLayout status=GamingUi.row(c),wirelessChip=GamingUi.row(c);wirelessChip.setPadding(dp(7),dp(4),dp(7),dp(4));wirelessChip.setBackground(GamingUi.background(c,GamingUi.CARD,14,false));
        GamingUi.Icon wireless=new GamingUi.Icon(c,"wifi",GamingUi.accent(c));wirelessChip.addView(wireless,new LinearLayout.LayoutParams(dp(18),dp(18)));
        wifiText=GamingUi.text(c,wifi,12,GamingUi.TEXT,true);wifiText.setPadding(dp(5),0,dp(5),0);wirelessChip.addView(wifiText);wirelessChip.addView(GamingUi.text(c,"⌄",14,GamingUi.accent(c),true));
        wirelessChip.setContentDescription(c.getString(R.string.gaming_wifi));wirelessChip.setFocusable(true);wirelessChip.setOnClickListener(v->actions.internet());status.addView(wirelessChip);
        GamingUi.Icon thermometer=new GamingUi.Icon(c,"temperature",GamingUi.accent(c));LinearLayout.LayoutParams tp=new LinearLayout.LayoutParams(dp(17),dp(22));tp.leftMargin=dp(7);status.addView(thermometer,tp);
        LinearLayout thermal=GamingUi.column(c);thermal.setPadding(dp(4),0,dp(8),0);thermal.addView(GamingUi.text(c,c.getString(R.string.gaming_battery_temp),9,GamingUi.MUTED,false));
        tempText=GamingUi.text(c,temperature,12,GamingUi.TEXT,true);tempText.setContentDescription(c.getString(R.string.gaming_battery_temp));thermal.addView(tempText);status.addView(thermal);
        batteryText=GamingUi.text(c,battery,12,GamingUi.MUTED,false);GamingUi.weighted(status,batteryText);main.addView(status);GamingUi.gap(main,6);
        LinearLayout telemetry=GamingUi.card(c);telemetry.setPadding(dp(12),dp(compact?2:6),dp(12),dp(compact?4:8));fpsText=GamingUi.text(c,c.getString(R.string.gaming_fps,fps),compact?28:34,GamingUi.TEXT,true);telemetry.addView(fpsText);
        ((LinearLayout.LayoutParams)telemetry.getLayoutParams()).bottomMargin=dp(compact?6:12);
        chart=new GamingUi.Chart(c);telemetry.addView(chart,new LinearLayout.LayoutParams(-1,dp(compact?18:27)));main.addView(telemetry);
        int brightness=android.provider.Settings.System.getInt(c.getContentResolver(),android.provider.Settings.System.SCREEN_BRIGHTNESS,128);
        slider(main,"sun",R.string.gaming_brightness,255,brightness,value->actions.brightness(Math.max(.01f,value/255f)));
        AudioManager audio=c.getSystemService(AudioManager.class);slider(main,"volume",R.string.gaming_volume,audio.getStreamMaxVolume(AudioManager.STREAM_MUSIC),audio.getStreamVolume(AudioManager.STREAM_MUSIC),value->audio.setStreamVolume(AudioManager.STREAM_MUSIC,value,0));
        GamingUi.gap(main,4);LinearLayout clean=GamingUi.row(c);int cleanPad=dp(compact?7:10);clean.setPadding(dp(10),cleanPad,dp(10),cleanPad);clean.setGravity(Gravity.CENTER);clean.setBackground(GamingUi.background(c,GamingUi.accent(c),16,false));
        clean.addView(new GamingUi.Icon(c,"clean",GamingUi.BG),new LinearLayout.LayoutParams(dp(25),dp(25)));LinearLayout cleanCopy=GamingUi.column(c);cleanCopy.setPadding(dp(9),0,0,0);
        cleanCopy.addView(GamingUi.text(c,c.getString(R.string.gaming_clean),compact?14:16,GamingUi.BG,true));cleanCopy.addView(GamingUi.text(c,c.getString(R.string.gaming_clean_summary),compact?9:10,GamingUi.BG,false));clean.addView(cleanCopy);clean.setFocusable(true);clean.setOnClickListener(v->actions.clean());main.addView(clean);GamingUi.gap(main,6);
        LinearLayout first=GamingUi.row(c);tile(first,"screenshot",R.string.gaming_screenshot,false,actions::screenshot);
        recordText=tile(first,"record",GamingRecordingService.recording?R.string.gaming_stop_record:R.string.gaming_record,GamingRecordingService.recording,actions::record);main.addView(first);GamingUi.gap(main,6);
        LinearLayout second=GamingUi.row(c);tile(second,"focus",R.string.gaming_focus,GamingPrefs.get(c).getBoolean("focus",false)&&c.getSystemService(android.app.NotificationManager.class).isNotificationPolicyAccessGranted(),actions::focus);tile(second,"lock",R.string.gaming_touch_lock,false,this::lock);main.addView(second);
    }
    private interface Progress{void change(int value);}
    private void slider(LinearLayout main,String icon,int label,int maximum,int progress,Progress callback){
        LinearLayout row=GamingUi.row(c);GamingUi.Icon image=new GamingUi.Icon(c,icon,GamingUi.TEXT);row.addView(image,new LinearLayout.LayoutParams(dp(21),dp(21)));
        TextView name=GamingUi.text(c,c.getString(label),11,GamingUi.TEXT,false);name.setPadding(dp(7),0,0,0);row.addView(name,new LinearLayout.LayoutParams(dp(75),-2));
        SeekBar slider=new SeekBar(c);slider.setMax(maximum);slider.setProgress(progress);slider.setProgressTintList(ColorStateList.valueOf(GamingUi.accent(c)));slider.setThumbTintList(ColorStateList.valueOf(Color.WHITE));slider.setContentDescription(c.getString(label));
        slider.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener(){public void onStartTrackingTouch(SeekBar s){}public void onStopTrackingTouch(SeekBar s){}public void onProgressChanged(SeekBar s,int p,boolean user){if(user)callback.change(p);}});
        row.addView(slider,new LinearLayout.LayoutParams(0,dp(compact?34:42),1));main.addView(row);
    }
    private TextView tile(LinearLayout row,String icon,int label,boolean selected,Runnable action){
        LinearLayout tile=GamingUi.column(c);tile.setGravity(Gravity.CENTER);tile.setPadding(0,dp(8),0,dp(8));tile.setBackground(GamingUi.background(c,GamingUi.CARD,15,selected));
        tile.addView(new GamingUi.Icon(c,icon,selected?GamingUi.accent(c):GamingUi.TEXT),new LinearLayout.LayoutParams(dp(22),dp(22)));
        TextView text=GamingUi.text(c,c.getString(label),11,GamingUi.TEXT,false);text.setPadding(0,dp(5),0,0);tile.addView(text);tile.setFocusable(true);tile.setContentDescription(c.getString(label));tile.setOnClickListener(v->action.run());
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,dp(compact?52:66),1);p.setMargins(dp(2),0,dp(2),0);row.addView(tile,p);return text;
    }
    void closePanel(){
        boolean wasOpen=open;open=false;picker=null;remove(panel);panel=null;fpsText=null;tempText=null;batteryText=null;wifiText=null;chart=null;recordText=null;
        if(hud!=null&&!captureHidden)hud.setVisibility(View.VISIBLE);if(wasOpen)actions.panelChanged(false);
    }
    void update(String fps,String temperature,String battery,String wifi){
        this.fps=fps;this.temperature=temperature;this.battery=battery;this.wifi=wifi;
        if(hud!=null)hud.setText(c.getString(R.string.gaming_fps,fps)+"  ·  "+temperature);
        if(fpsText!=null)fpsText.setText(c.getString(R.string.gaming_fps,fps));if(tempText!=null)tempText.setText(temperature);
        if(batteryText!=null)batteryText.setText(battery);if(wifiText!=null)wifiText.setText(wifi);
        if(recordText!=null)recordText.setText(GamingRecordingService.recording?R.string.gaming_stop_record:R.string.gaming_record);
    }
    void sample(float value){if(chart!=null)chart.sample(value);}
    void showShortcutPicker(List<GamingCatalog.App> apps){
        if(!open)openPanel();if(panel==null)return;picker=apps;
        LinearLayout shell=(LinearLayout)panel;ScrollView scroll=(ScrollView)shell.getChildAt(1);LinearLayout list=GamingUi.column(c);
        list.addView(GamingUi.text(c,c.getString(R.string.gaming_shortcuts),18,GamingUi.TEXT,true));GamingUi.gap(list,6);
        list.addView(GamingUi.text(c,c.getString(R.string.gaming_shortcuts_summary),12,GamingUi.MUTED,false));GamingUi.gap(list,8);
        list.addView(GamingUi.button(c,c.getString(R.string.gaming_done),false,()->{closePanel();openPanel();}));GamingUi.gap(list,8);
        for(GamingCatalog.App app:apps){boolean selected=GamingPrefs.shortcuts(c).contains(app.info.packageName);
            list.addView(GamingUi.button(c,(selected?"✓  ":"")+app.label,selected,()->actions.toggleShortcut(app.info.packageName)));GamingUi.gap(list,5);}
        scroll.removeAllViews();scroll.addView(list);
    }
    void captureHidden(boolean hidden){
        captureHidden=hidden;if(hidden)closePanel();if(handle!=null)handle.setVisibility(hidden?View.INVISIBLE:View.VISIBLE);if(hud!=null)hud.setVisibility(hidden?View.INVISIBLE:View.VISIBLE);
    }
    private void lock(){
        closePanel();unlock();FrameLayout veil=new FrameLayout(c);veil.setBackgroundColor(0x10000000);
        TextView instruction=GamingUi.text(c,c.getString(R.string.gaming_hold_unlock),16,GamingUi.TEXT,true);instruction.setPadding(dp(18),dp(14),dp(18),dp(14));instruction.setBackground(GamingUi.background(c,0xee101b25,22,true));veil.addView(instruction,new FrameLayout.LayoutParams(-2,-2,Gravity.CENTER));
        veil.setOnTouchListener((v,e)->{if(e.getActionMasked()==MotionEvent.ACTION_DOWN){handler.postDelayed(unlock,2000);instruction.setAlpha(.6f);}else if(e.getActionMasked()==MotionEvent.ACTION_UP||e.getActionMasked()==MotionEvent.ACTION_CANCEL){handler.removeCallbacks(unlock);instruction.setAlpha(1);}return true;});
        veil.setContentDescription(c.getString(R.string.gaming_hold_unlock));WindowManager.LayoutParams p=params(-1,-1,false);p.gravity=Gravity.TOP|Gravity.LEFT;wm.addView(veil,p);touchLock=veil;
    }
    private void unlock(){handler.removeCallbacks(unlock);remove(touchLock);touchLock=null;}
    private void remove(View v){if(v!=null&&v.isAttachedToWindow())try{wm.removeViewImmediate(v);}catch(IllegalArgumentException ignored){}}
}
