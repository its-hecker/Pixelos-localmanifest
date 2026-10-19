// SPDX-License-Identifier: Apache-2.0
package org.hecker.suite;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.app.NotificationManager;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.drawable.Drawable;
import android.net.Uri;
import android.os.Bundle;
import android.provider.Settings;
import android.text.Editable;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.View;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.SeekBar;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class GamingActivity extends Activity implements SharedPreferences.OnSharedPreferenceChangeListener {
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private LinearLayout page, library;
    private String tab="games";
    private int generation;
    private boolean pendingEnable,visible;

    @Override public void onCreate(Bundle state){
        super.onCreate(state); if(state!=null){tab=state.getString("tab","games");pendingEnable=state.getBoolean("pending_enable",false);}
        GamingPrefs.get(this).registerOnSharedPreferenceChangeListener(this);
        render();
    }
    @Override protected void onResume(){
        super.onResume();visible=true;
        if(pendingEnable && Settings.canDrawOverlays(this)){pendingEnable=false;setEnabled(true);}
        render();
        if(GamingPrefs.enabled(this))GamingService.start(this);
    }
    @Override protected void onPause(){visible=false;super.onPause();}
    @Override protected void onSaveInstanceState(Bundle out){super.onSaveInstanceState(out);out.putString("tab",tab);out.putBoolean("pending_enable",pendingEnable);}
    @Override protected void onDestroy(){
        generation++;GamingPrefs.get(this).unregisterOnSharedPreferenceChangeListener(this);worker.shutdownNow();super.onDestroy();
    }
    @Override public void onSharedPreferenceChanged(SharedPreferences prefs,String key){
        if(visible && !isFinishing() && !isDestroyed() && !key.startsWith("session_") && !key.startsWith("hud_") && !key.equals("focus_applied"))render();
    }
    private TextView title(int string){return GamingUi.text(this,getString(string),22,GamingUi.TEXT,true);}
    private void render(){
        int request=++generation;
        LinearLayout root=GamingUi.column(this);root.setBackgroundColor(GamingUi.BG);
        int pad=GamingUi.dp(this,20);
        root.setOnApplyWindowInsetsListener((v,insets)->{
            android.graphics.Insets bars=insets.getInsets(android.view.WindowInsets.Type.systemBars()|android.view.WindowInsets.Type.displayCutout());
            root.setPadding(bars.left,bars.top,bars.right,bars.bottom);return insets;});
        LinearLayout top=GamingUi.row(this);top.setPadding(pad,pad,pad,GamingUi.dp(this,12));
        GamingUi.Icon back=new GamingUi.Icon(this,"back",GamingUi.TEXT);back.setContentDescription(getString(R.string.back));back.setImportantForAccessibility(View.IMPORTANT_FOR_ACCESSIBILITY_YES);back.setFocusable(true);
        back.setOnClickListener(v->finish());top.addView(back,new LinearLayout.LayoutParams(GamingUi.dp(this,40),GamingUi.dp(this,40)));
        top.addView(GamingUi.text(this,getString(R.string.suite_title),15,GamingUi.MUTED,false));root.addView(top);
        ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);page=GamingUi.column(this);page.setPadding(pad,0,pad,pad);
        page.addView(GamingUi.text(this,getString(R.string.gaming_title),32,GamingUi.TEXT,true));GamingUi.gap(page,20);
        if(tab.equals("games"))games(request);else if(tab.equals("tools"))tools();else style();
        scroll.addView(page);root.addView(scroll,new LinearLayout.LayoutParams(-1,0,1));
        LinearLayout nav=GamingUi.row(this);nav.setPadding(pad,GamingUi.dp(this,8),pad,GamingUi.dp(this,8));
        String[] names={"games","tools","style"};int[] labels={R.string.gaming_games,R.string.gaming_tools,R.string.gaming_style};
        for(int i=0;i<3;i++){String name=names[i];TextView button=GamingUi.button(this,getString(labels[i]),tab.equals(name),()->{tab=name;render();});LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(0,-2,1);lp.setMargins(3,0,3,0);nav.addView(button,lp);}
        root.addView(nav);setContentView(root);
    }
    private void games(int request){
        FrameLayout hero=new FrameLayout(this);
        hero.addView(new GamingUi.Banner(this,getDrawable(R.drawable.ic_gaming),true),new FrameLayout.LayoutParams(-1,GamingUi.dp(this,150)));
        LinearLayout copy=GamingUi.column(this);copy.setPadding(GamingUi.dp(this,20),GamingUi.dp(this,28),0,0);
        copy.addView(title(R.string.gaming_ready));GamingUi.gap(copy,12);
        copy.addView(GamingUi.text(this,getString(GamingPrefs.enabled(this)?R.string.gaming_enabled:R.string.gaming_disabled),13,GamingUi.accent(this),true));hero.addView(copy);page.addView(hero);GamingUi.gap(page,16);
        toggle(R.string.gaming_enable,0,GamingPrefs.enabled(this),this::setEnabled);
        toggle(R.string.gaming_auto,R.string.gaming_auto_summary,GamingPrefs.get(this).getBoolean("automatic",true),v->GamingPrefs.get(this).edit().putBoolean("automatic",v).apply());
        LinearLayout heading=GamingUi.row(this);GamingUi.weighted(heading,title(R.string.gaming_library));heading.addView(GamingUi.button(this,getString(R.string.gaming_add),false,()->picker(false)));page.addView(heading);GamingUi.gap(page,12);
        library=GamingUi.column(this);library.addView(GamingUi.text(this,getString(R.string.gaming_loading),14,GamingUi.MUTED,false));page.addView(library);
        worker.execute(()->{List<GamingCatalog.App> apps=GamingCatalog.load(this,true);runOnUiThread(()->{
            if(request!=generation||isDestroyed())return;library.removeAllViews();
            if(apps.isEmpty())library.addView(GamingUi.text(this,getString(R.string.gaming_empty),16,GamingUi.MUTED,false));
            if(!apps.isEmpty())library.addView(gameCard(apps.get(0),true));
            for(int i=1;i<apps.size();i+=2){
                LinearLayout row=GamingUi.row(this);row.setGravity(Gravity.TOP);
                for(int j=i;j<i+2;j++){
                    View item=j<apps.size()?gameCard(apps.get(j),false):new View(this);
                    LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(0,-2,1);lp.setMargins(GamingUi.dp(this,3),0,GamingUi.dp(this,3),GamingUi.dp(this,10));row.addView(item,lp);
                }
                library.addView(row);
            }
        });});
    }
    private View gameCard(GamingCatalog.App app,boolean featured){
        LinearLayout card=GamingUi.card(this);card.setPadding(0,0,0,GamingUi.dp(this,12));
        Drawable icon=app.info.loadIcon(getPackageManager());card.addView(new GamingUi.Banner(this,icon,featured),new LinearLayout.LayoutParams(-1,GamingUi.dp(this,featured?148:104)));
        LinearLayout row=GamingUi.row(this);row.setPadding(GamingUi.dp(this,14),GamingUi.dp(this,12),GamingUi.dp(this,14),0);
        TextView label=GamingUi.text(this,app.label,featured?19:14,GamingUi.TEXT,true);label.setMaxLines(2);label.setEllipsize(android.text.TextUtils.TruncateAt.END);GamingUi.weighted(row,label);
        TextView play=GamingUi.button(this,featured?getString(R.string.gaming_play):"▶",true,()->{
            Intent launch=GamingCatalog.launch(this,app.info.packageName);
            if(launch!=null)try{startActivity(launch);}catch(RuntimeException e){toast(R.string.gaming_launch_error);}
        });play.setContentDescription(getString(R.string.gaming_play)+" "+app.label);row.addView(play);card.addView(row);
        card.setOnLongClickListener(v->{new AlertDialog.Builder(this).setTitle(app.label).setItems(new String[]{getString(R.string.gaming_remove)},(d,i)->GamingPrefs.include(this,app.info.packageName,false)).show();return true;});return card;
    }
    private interface Change{void set(boolean value);}
    private void toggle(int label,int summary,boolean checked,Change change){
        LinearLayout card=GamingUi.card(this),row=GamingUi.row(this),copy=GamingUi.column(this);
        copy.addView(GamingUi.text(this,getString(label),16,GamingUi.TEXT,true));
        if(summary!=0){GamingUi.gap(copy,6);copy.addView(GamingUi.text(this,getString(summary),13,GamingUi.MUTED,false));}
        GamingUi.weighted(row,copy);Switch control=new Switch(this);control.setContentDescription(getString(label));control.setChecked(checked);control.setThumbTintList(ColorStateList.valueOf(GamingUi.accent(this)));control.setOnCheckedChangeListener((button,value)->change.set(value));row.addView(control);card.addView(row);page.addView(card);
    }
    private void setEnabled(boolean value){
        if(value&&!Settings.canDrawOverlays(this)){
            pendingEnable=true;toast(R.string.gaming_overlay_access);
            try{startActivity(new Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,Uri.parse("package:"+getPackageName())));}catch(RuntimeException e){toast(R.string.gaming_unavailable);}render();return;
        }
        GamingPrefs.get(this).edit().putBoolean("enabled",value).apply();
        if(value){if(checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},7);GamingService.start(this);}
        else stopService(new Intent(this,GamingService.class));
    }
    private void tools(){
        toggle(R.string.gaming_enable,0,GamingPrefs.enabled(this),this::setEnabled);
        toggle(R.string.gaming_fps_toggle,R.string.gaming_fps_summary,GamingPrefs.get(this).getBoolean("fps",true),v->GamingPrefs.get(this).edit().putBoolean("fps",v).apply());
        toggle(R.string.gaming_focus,R.string.gaming_focus_summary,GamingPrefs.get(this).getBoolean("focus",false),v->{
            if(v&&!getSystemService(NotificationManager.class).isNotificationPolicyAccessGranted()){
                toast(R.string.gaming_focus_access);startActivity(new Intent(Settings.ACTION_NOTIFICATION_POLICY_ACCESS_SETTINGS));render();
            }else GamingPrefs.get(this).edit().putBoolean("focus",v).apply();
        });
        LinearLayout card=GamingUi.card(this);card.addView(title(R.string.gaming_shortcuts));GamingUi.gap(card,8);
        card.addView(GamingUi.text(this,getString(R.string.gaming_shortcuts_summary),14,GamingUi.MUTED,false));GamingUi.gap(card,12);
        card.addView(GamingUi.button(this,getString(R.string.gaming_shortcuts_count,GamingPrefs.shortcuts(this).size()),false,()->picker(true)));page.addView(card);
        page.addView(GamingUi.text(this,getString(R.string.gaming_saves),14,GamingUi.MUTED,false));GamingUi.gap(page,16);
        page.addView(GamingUi.text(this,getString(R.string.gaming_record_explainer),13,GamingUi.MUTED,false));GamingUi.gap(page,12);
        page.addView(GamingUi.text(this,getString(R.string.gaming_frame_note),13,GamingUi.MUTED,false));
    }
    private void style(){
        page.addView(title(R.string.gaming_accent));GamingUi.gap(page,14);LinearLayout colors=GamingUi.row(this);
        int[] values={0xff35eee3,0xffb29aff,0xffbbf35a,0xffffbe65};int[] labels={R.string.gaming_cyan,R.string.gaming_violet,R.string.gaming_lime,R.string.gaming_amber};
        for(int i=0;i<values.length;i++){int color=values[i];TextView chip=GamingUi.button(this,getString(labels[i]),GamingUi.accent(this)==color,()->GamingPrefs.get(this).edit().putInt("accent",color).apply());chip.setTextColor(GamingUi.accent(this)==color?GamingUi.BG:color);LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(0,-2,1);p.setMargins(3,0,3,0);colors.addView(chip,p);}page.addView(colors);GamingUi.gap(page,24);
        toggle(R.string.gaming_edge,R.string.gaming_edge_summary,GamingPrefs.get(this).getBoolean("left",false),v->GamingPrefs.get(this).edit().putBoolean("left",v).apply());
        page.addView(title(R.string.gaming_opacity));SeekBar opacity=new SeekBar(this);opacity.setMax(40);opacity.setProgress(GamingPrefs.get(this).getInt("opacity",94)-60);opacity.setContentDescription(getString(R.string.gaming_opacity));
        opacity.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener(){public void onStartTrackingTouch(SeekBar s){}public void onProgressChanged(SeekBar s,int p,boolean user){}public void onStopTrackingTouch(SeekBar s){GamingPrefs.get(GamingActivity.this).edit().putInt("opacity",60+s.getProgress()).apply();}});page.addView(opacity);
    }
    private void picker(boolean shortcuts){
        LinearLayout box=GamingUi.column(this);int p=GamingUi.dp(this,16);box.setPadding(p,p,p,p);
        EditText search=new EditText(this);search.setSingleLine();search.setHint(R.string.gaming_search);box.addView(search);
        ScrollView scroll=new ScrollView(this);LinearLayout list=GamingUi.column(this);scroll.addView(list);box.addView(scroll,new LinearLayout.LayoutParams(-1,GamingUi.dp(this,360)));
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle(shortcuts?R.string.gaming_shortcuts:R.string.gaming_add).setView(box).setPositiveButton(R.string.gaming_done,null).create();dialog.show();
        worker.execute(()->{List<GamingCatalog.App> apps=GamingCatalog.load(this,false);runOnUiThread(()->{
            if(!dialog.isShowing()||isDestroyed())return;
            Runnable[] fill=new Runnable[1];fill[0]=()->{list.removeAllViews();String query=search.getText().toString().trim().toLowerCase(java.util.Locale.ROOT);
                for(GamingCatalog.App app:apps){if(!app.label.toLowerCase(java.util.Locale.ROOT).contains(query)&&!app.info.packageName.contains(query))continue;
                    boolean tagged=app.info.category==android.content.pm.ApplicationInfo.CATEGORY_GAME||(app.info.flags&android.content.pm.ApplicationInfo.FLAG_IS_GAME)!=0;
                    boolean selected=shortcuts?GamingPrefs.shortcuts(this).contains(app.info.packageName):GamingPolicy.isGame(app.info.packageName,tagged,GamingPrefs.get(this).getBoolean("automatic",true),GamingPrefs.added(this),GamingPrefs.excluded(this));
                    TextView row=GamingUi.button(this,(selected?"✓  ":"")+app.label,selected,()->{
                        if(shortcuts){if(!GamingPrefs.shortcuts(this).contains(app.info.packageName)&&GamingPrefs.shortcuts(this).size()>=5){toast(R.string.gaming_limit);return;}GamingPrefs.toggleShortcut(this,app.info.packageName);}
                        else GamingPrefs.include(this,app.info.packageName,!selected);
                        fill[0].run();
                    });list.addView(row);GamingUi.gap(list,6);
                }};fill[0].run();search.addTextChangedListener(new TextWatcher(){public void beforeTextChanged(CharSequence s,int st,int count,int after){}public void onTextChanged(CharSequence s,int st,int before,int count){fill[0].run();}public void afterTextChanged(Editable e){}});
        });});
    }
    private void toast(int string){Toast.makeText(this,string,Toast.LENGTH_LONG).show();}
}
