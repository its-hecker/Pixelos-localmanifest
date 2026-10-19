// SPDX-License-Identifier: Apache-2.0
package org.hecker.suite;

import android.app.ActivityManager;
import android.app.KeyguardManager;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.IntentFilter;
import android.content.SharedPreferences;
import android.content.pm.ServiceInfo;
import android.content.res.Configuration;
import android.net.ConnectivityManager;
import android.net.NetworkCapabilities;
import android.os.BatteryManager;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.PowerManager;
import android.os.SystemClock;
import android.provider.Settings;
import android.util.Log;
import android.view.WindowManager;
import android.widget.Toast;
import android.window.TaskFpsCallback;
import java.util.HashSet;
import java.util.List;
import java.util.ArrayList;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class GamingService extends Service implements GamingOverlay.Actions,
        SharedPreferences.OnSharedPreferenceChangeListener {
    static final String RECORD_STARTED="org.hecker.suite.RECORD_STARTED";
    private static final String CHANNEL="gaming",STOP="org.hecker.suite.STOP_GAMING";
    private final Handler main=new Handler(Looper.getMainLooper());
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private Set<String> games=new HashSet<>(),popups=new HashSet<>();
    private ActivityManager am;private WindowManager wm;private GamingOverlay overlay;
    private int gameTask=-1,fpsTask=-1,catalogGeneration;
    private String gamePackage;
    private boolean active,brightnessChanged,stateRegistered,packagesRegistered,destroyed;
    private GamingTaskObserver taskObserver;
    private float fps=Float.NaN;
    private long fpsAt,recordGrace;
    private Intent battery;
    private TaskFpsCallback fpsCallback;
    private final Runnable evaluate=this::evaluate;
    private final BroadcastReceiver state=new BroadcastReceiver(){@Override public void onReceive(Context c,Intent i){
        if(Intent.ACTION_BATTERY_CHANGED.equals(i.getAction())){battery=i;updateStatus();}
        else if(Intent.ACTION_SCREEN_OFF.equals(i.getAction())){recordGrace=0;pause();}
        else schedule(250);
    }};
    private final BroadcastReceiver packages=new BroadcastReceiver(){@Override public void onReceive(Context c,Intent i){loadCatalog();}};

    static void start(Context c){
        if(!GamingPrefs.enabled(c))return;
        try{c.startForegroundService(new Intent(c,GamingService.class));}
        catch(RuntimeException e){Log.w("HeckerGaming","Could not start dashboard",e);Toast.makeText(c,R.string.gaming_unavailable,Toast.LENGTH_LONG).show();}
    }
    @Override public void onCreate(){
        super.onCreate();am=getSystemService(ActivityManager.class);wm=getSystemService(WindowManager.class);
        NotificationManager notifications=getSystemService(NotificationManager.class);
        notifications.createNotificationChannel(new NotificationChannel(CHANNEL,getString(R.string.gaming_monitor),NotificationManager.IMPORTANCE_LOW));
        startForeground(31,notification(),ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        overlay=new GamingOverlay(this,this);
        GamingPrefs.get(this).registerOnSharedPreferenceChangeListener(this);
        // Clear only this target-37 app's implicit DND rule after a restart.
        focusState(false);
        try{
            taskObserver=new GamingTaskObserver(()->main.post(()->schedule(120)));
            IntentFilter filter=new IntentFilter(Intent.ACTION_SCREEN_OFF);filter.addAction(Intent.ACTION_SCREEN_ON);filter.addAction(Intent.ACTION_USER_PRESENT);filter.addAction(Intent.ACTION_BATTERY_CHANGED);
            battery=registerReceiver(state,filter,Context.RECEIVER_NOT_EXPORTED);stateRegistered=true;
            IntentFilter packageFilter=new IntentFilter(Intent.ACTION_PACKAGE_ADDED);packageFilter.addAction(Intent.ACTION_PACKAGE_REMOVED);packageFilter.addAction(Intent.ACTION_PACKAGE_CHANGED);packageFilter.addDataScheme("package");
            registerReceiver(packages,packageFilter,Context.RECEIVER_NOT_EXPORTED);packagesRegistered=true;loadCatalog();
        }catch(RuntimeException e){Log.e("HeckerGaming","Required platform access unavailable",e);Toast.makeText(this,R.string.gaming_unavailable,Toast.LENGTH_LONG).show();stopSelf();}
    }
    @Override public int onStartCommand(Intent i,int flags,int startId){
        if(!GamingPrefs.enabled(this)||i!=null&&STOP.equals(i.getAction())){
            GamingPrefs.get(this).edit().putBoolean("enabled",false).apply();stopSelf();return START_NOT_STICKY;
        }
        if(i!=null&&RECORD_STARTED.equals(i.getAction()))recordGrace=SystemClock.elapsedRealtime()+2500;
        schedule(150);return START_STICKY;
    }
    @Override public IBinder onBind(Intent i){return null;}
    private Notification notification(){
        PendingIntent hub=PendingIntent.getActivity(this,0,new Intent(this,GamingActivity.class),PendingIntent.FLAG_IMMUTABLE|PendingIntent.FLAG_UPDATE_CURRENT);
        PendingIntent stop=PendingIntent.getService(this,1,new Intent(this,GamingService.class).setAction(STOP),PendingIntent.FLAG_IMMUTABLE);
        return new Notification.Builder(this,CHANNEL).setSmallIcon(R.drawable.ic_gaming).setContentTitle(getString(R.string.gaming_title))
            .setContentText(active&&gamePackage!=null?getString(R.string.gaming_monitor_active,GamingCatalog.label(this,gamePackage)):getString(R.string.gaming_monitor_ready))
            .setContentIntent(hub).setOngoing(true).setOnlyAlertOnce(true).addAction(new Notification.Action.Builder(null,getString(R.string.gaming_disable),stop).build()).build();
    }
    private void loadCatalog(){
        int request=++catalogGeneration;worker.execute(()->{
            Set<String> found=new HashSet<>();for(GamingCatalog.App app:GamingCatalog.load(this,true))found.add(app.info.packageName);
            main.post(()->{if(destroyed||request!=catalogGeneration)return;games=found;schedule(0);});
        });
    }
    private void schedule(long delay){if(destroyed)return;main.removeCallbacks(evaluate);main.postDelayed(evaluate,delay);}
    private boolean unlocked(){return getSystemService(PowerManager.class).isInteractive()&&!getSystemService(KeyguardManager.class).isKeyguardLocked();}
    private static String pkg(ActivityManager.RunningTaskInfo task){return task.topActivity==null?"":task.topActivity.getPackageName();}
    private boolean focused(ActivityManager.RunningTaskInfo task){
        try{return task.getClass().getField("isFocused").getBoolean(task);}catch(ReflectiveOperationException e){return false;}
    }
    private void evaluate(){
        if(destroyed)return;
        if(!GamingPrefs.enabled(this)){stopSelf();return;}
        if(!unlocked()||!Settings.canDrawOverlays(this)){pause();return;}
        try{
            List<ActivityManager.RunningTaskInfo> tasks=am.getRunningTasks(20);
            List<GamingPolicy.Task> snapshot=new ArrayList<>();boolean previousVisible=false;
            for(ActivityManager.RunningTaskInfo task:tasks){
                if(!GamingPlatform.ownDisplayTask(task))continue;
                String packageName=pkg(task);
                if(task.taskId==gameTask&&task.isVisible()&&games.contains(packageName))previousVisible=true;
                snapshot.add(new GamingPolicy.Task(task.taskId,packageName,task.isVisible(),focused(task),
                        popups.contains(packageName)&&GamingPlatform.freeform(task)));
            }
            GamingPolicy.Task selected=GamingPolicy.activeGame(snapshot,games,popups,gameTask,true);
            if(selected!=null){
                boolean changed=gameTask!=selected.id;
                if(changed){stopFps();popups.clear();}
                gameTask=selected.id;gamePackage=selected.pkg;activate();
                if(changed)getSystemService(NotificationManager.class).notify(31,notification());
            }else{pause();if(!previousVisible){gameTask=-1;gamePackage=null;popups.clear();}}
        }catch(RuntimeException e){Log.w("HeckerGaming","Task observation failed",e);pause();}
        if(active||SystemClock.elapsedRealtime()<recordGrace)schedule(1000);
    }
    private void activate(){
        if(!active){active=true;overlay.show();getSystemService(NotificationManager.class).notify(31,notification());}
        focusState(GamingPrefs.get(this).getBoolean("focus",false));syncFps();updateStatus();
    }
    private void pause(){
        boolean wasActive=active;active=false;
        if(overlay!=null)overlay.hide();stopFps();focusState(false);
        if(brightnessChanged){try{GamingPlatform.brightness(this,Float.NaN);}catch(ReflectiveOperationException|RuntimeException ignored){}brightnessChanged=false;}
        if(GamingRecordingService.recording&&SystemClock.elapsedRealtime()>=recordGrace)stopService(new Intent(this,GamingRecordingService.class));
        if(wasActive)getSystemService(NotificationManager.class).notify(31,notification());
    }
    private void syncFps(){
        boolean wanted=active&&gameTask>=0&&(overlay.isOpen()||GamingPrefs.get(this).getBoolean("fps",true));
        if(!wanted){stopFps();return;}if(fpsCallback!=null&&fpsTask==gameTask)return;
        stopFps();int sampledTask=gameTask;
        TaskFpsCallback callback=new TaskFpsCallback(){@Override public void onFpsReported(float reported){
            if(!active||fpsTask!=sampledTask||fpsCallback!=this)return;fps=GamingPolicy.usableFps(reported);fpsAt=SystemClock.elapsedRealtime();overlay.sample(fps);updateStatus();
        }};
        try{fpsTask=sampledTask;fpsCallback=callback;wm.registerTaskFpsCallback(sampledTask,getMainExecutor(),callback);}
        catch(RuntimeException e){Log.w("HeckerGaming","Task FPS unavailable",e);stopFps();}
    }
    private void stopFps(){
        if(fpsCallback!=null)try{wm.unregisterTaskFpsCallback(fpsCallback);}catch(RuntimeException ignored){}
        fpsCallback=null;fpsTask=-1;fps=Float.NaN;fpsAt=0;
    }
    private void updateStatus(){
        if(overlay==null||!active)return;
        String frames=Float.isFinite(fps)&&SystemClock.elapsedRealtime()-fpsAt<5000?String.format(java.util.Locale.getDefault(),"%.0f",fps):"—";
        String temp="—",level="—";
        if(battery!=null){int raw=battery.getIntExtra(BatteryManager.EXTRA_TEMPERATURE,Integer.MIN_VALUE);
            if(raw!=Integer.MIN_VALUE)temp=getString(R.string.gaming_temperature,raw/10f);
            int amount=battery.getIntExtra(BatteryManager.EXTRA_LEVEL,-1),scale=battery.getIntExtra(BatteryManager.EXTRA_SCALE,-1);
            if(amount>=0&&scale>0)level=getString(R.string.gaming_battery,amount*100/scale);
        }
        ConnectivityManager network=getSystemService(ConnectivityManager.class);NetworkCapabilities capabilities=network.getNetworkCapabilities(network.getActiveNetwork());
        int connection=capabilities==null?R.string.gaming_offline:capabilities.hasTransport(NetworkCapabilities.TRANSPORT_WIFI)?R.string.gaming_wifi:R.string.gaming_mobile;
        overlay.update(frames,temp,level,getString(connection));
    }
    private void focusState(boolean wanted){
        SharedPreferences prefs=GamingPrefs.get(this);boolean applied=prefs.getBoolean("focus_applied",false);
        if(applied==wanted)return;NotificationManager nm=getSystemService(NotificationManager.class);
        if(!nm.isNotificationPolicyAccessGranted()){if(applied)prefs.edit().putBoolean("focus_applied",false).apply();return;}
        try{
            // Android 15+ targets control an app-owned implicit Zen rule, not the global DND state.
            nm.setInterruptionFilter(wanted?NotificationManager.INTERRUPTION_FILTER_PRIORITY:NotificationManager.INTERRUPTION_FILTER_ALL);
            prefs.edit().putBoolean("focus_applied",wanted).apply();
        }catch(SecurityException e){Log.w("HeckerGaming","Focus access was revoked",e);}
    }
    @Override public void panelChanged(boolean open){syncFps();}
    @Override public void clean(){
        if(!active||gamePackage==null)return;String protectedGame=gamePackage;
        worker.execute(()->{try{int count=GamingPlatform.clean(this,protectedGame);main.post(()->toast(getString(R.string.gaming_clean_result,count)));}
            catch(RuntimeException e){main.post(()->toast(getString(R.string.gaming_unavailable)));}});
    }
    @Override public void screenshot(){
        if(!active)return;overlay.captureHidden(true);
        main.postDelayed(()->{
            if(!active||!unlocked()){if(active)overlay.captureHidden(false);return;}
            GamingCapture.screenshot(this,(success)->main.post(()->{
                if(destroyed)return;if(active)overlay.captureHidden(false);
                toast(success?getString(R.string.gaming_capture_saved,"Pictures/HeckerSuite"):getString(R.string.gaming_capture_error));
            }));
        },180);
    }
    @Override public void record(){
        if(GamingRecordingService.recording){stopService(new Intent(this,GamingRecordingService.class));updateStatus();return;}
        if(!active)return;recordGrace=SystemClock.elapsedRealtime()+60000;overlay.captureHidden(true);
        try{startActivity(new Intent(this,GamingCaptureConsentActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));}
        catch(RuntimeException e){overlay.captureHidden(false);toast(getString(R.string.gaming_capture_error));}
    }
    @Override public void focus(){
        NotificationManager nm=getSystemService(NotificationManager.class);
        if(!nm.isNotificationPolicyAccessGranted()){
            overlay.closePanel();toast(getString(R.string.gaming_focus_access));
            startActivity(new Intent(Settings.ACTION_NOTIFICATION_POLICY_ACCESS_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));return;
        }
        GamingPrefs.get(this).edit().putBoolean("focus",!GamingPrefs.get(this).getBoolean("focus",false)).apply();
    }
    @Override public void internet(){overlay.closePanel();try{startActivity(new Intent(Settings.Panel.ACTION_INTERNET_CONNECTIVITY).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));}catch(RuntimeException e){toast(getString(R.string.gaming_unavailable));}}
    @Override public void shortcut(String packageName){
        if(!active||!GamingPrefs.shortcuts(this).contains(packageName))return;
        Intent intent=GamingCatalog.launch(this,packageName);if(intent==null){toast(getString(R.string.gaming_launch_error));return;}
        try{GamingPlatform.popup(this,intent);popups.add(packageName);schedule(250);}
        catch(ReflectiveOperationException|RuntimeException e){Log.w("HeckerGaming","Popup launch failed",e);toast(getString(R.string.gaming_popup_unavailable));}
    }
    @Override public void chooseShortcuts(){worker.execute(()->{
        List<GamingCatalog.App> apps=GamingCatalog.load(this,false);main.post(()->{if(!destroyed&&active)overlay.showShortcutPicker(apps);});
    });}
    @Override public void toggleShortcut(String pkg){
        if(!GamingPrefs.shortcuts(this).contains(pkg)&&GamingPrefs.shortcuts(this).size()>=5){toast(getString(R.string.gaming_limit));return;}GamingPrefs.toggleShortcut(this,pkg);
    }
    @Override public void brightness(float brightness){try{GamingPlatform.brightness(this,brightness);brightnessChanged=true;}catch(ReflectiveOperationException|RuntimeException e){toast(getString(R.string.gaming_unavailable));}}
    @Override public void onSharedPreferenceChanged(SharedPreferences prefs,String key){
        if(destroyed||key.startsWith("hud_")||key.equals("focus_applied"))return;
        if(key.equals("enabled")&&!GamingPrefs.enabled(this)){stopSelf();return;}
        if(key.equals("added")||key.equals("excluded")||key.equals("automatic"))loadCatalog();
        else if(active){overlay.restyle();syncFps();focusState(prefs.getBoolean("focus",false));updateStatus();}
    }
    @Override public void onConfigurationChanged(Configuration config){super.onConfigurationChanged(config);if(active){overlay.restyle();updateStatus();}}
    @Override public void onTaskRemoved(Intent i){if(GamingPrefs.enabled(this))super.onTaskRemoved(i);else stopSelf();}
    @Override public void onDestroy(){
        destroyed=true;catalogGeneration++;recordGrace=0;main.removeCallbacksAndMessages(null);pause();
        if(taskObserver!=null)try{taskObserver.close();}catch(RuntimeException ignored){}
        if(stateRegistered)unregisterReceiver(state);if(packagesRegistered)unregisterReceiver(packages);
        GamingPrefs.get(this).unregisterOnSharedPreferenceChangeListener(this);worker.shutdownNow();stopForeground(STOP_FOREGROUND_REMOVE);super.onDestroy();
    }
    private void toast(String message){Toast.makeText(this,message,Toast.LENGTH_LONG).show();}
}
