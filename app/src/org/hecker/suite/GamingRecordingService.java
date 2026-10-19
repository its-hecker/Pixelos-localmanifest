// SPDX-License-Identifier: Apache-2.0
package org.hecker.suite;

import android.app.Activity;
import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.ContentValues;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.hardware.display.DisplayManager;
import android.hardware.display.VirtualDisplay;
import android.media.MediaRecorder;
import android.media.projection.MediaProjection;
import android.media.projection.MediaProjectionManager;
import android.net.Uri;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.os.ParcelFileDescriptor;
import android.provider.MediaStore;
import android.util.DisplayMetrics;
import android.util.Log;
import android.widget.Toast;

public final class GamingRecordingService extends Service {
    static volatile boolean recording;
    private static final String STOP="org.hecker.suite.STOP_RECORDING",CHANNEL="gaming_capture";
    private MediaProjection projection;
    private MediaRecorder recorder;
    private VirtualDisplay display;
    private ParcelFileDescriptor descriptor;
    private Uri destination;
    private boolean started,cleaning;
    private final MediaProjection.Callback callback=new MediaProjection.Callback(){@Override public void onStop(){stopSelf();}};

    @Override public IBinder onBind(Intent i){return null;}
    @Override public int onStartCommand(Intent intent,int flags,int startId){
        if(intent==null||STOP.equals(intent.getAction())||!GamingPrefs.enabled(this)){stopSelf();return START_NOT_STICKY;}
        if(recording)return START_NOT_STICKY;
        Intent token=intent.getParcelableExtra("projection",Intent.class);
        if(token==null||intent.getIntExtra("result",0)!=Activity.RESULT_OK){stopSelf();return START_NOT_STICKY;}
        NotificationManager nm=getSystemService(NotificationManager.class);
        nm.createNotificationChannel(new NotificationChannel(CHANNEL,getString(R.string.gaming_record_channel),NotificationManager.IMPORTANCE_LOW));
        PendingIntent stop=PendingIntent.getService(this,42,new Intent(this,GamingRecordingService.class).setAction(STOP),PendingIntent.FLAG_IMMUTABLE);
        Notification notification=new Notification.Builder(this,CHANNEL).setSmallIcon(R.drawable.ic_gaming).setContentTitle(getString(R.string.gaming_recording))
            .setContentText(getString(R.string.gaming_recording_detail)).setOngoing(true).setUsesChronometer(true).setWhen(System.currentTimeMillis())
            .addAction(new Notification.Action.Builder(null,getString(R.string.gaming_stop_record),stop).build()).build();
        try{
            startForeground(32,notification,ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION);
            projection=getSystemService(MediaProjectionManager.class).getMediaProjection(Activity.RESULT_OK,token);
            projection.registerCallback(callback,new Handler(Looper.getMainLooper()));
            ContentValues values=new ContentValues();values.put(MediaStore.Video.Media.DISPLAY_NAME,"Gaming_"+System.currentTimeMillis()+".mp4");
            values.put(MediaStore.Video.Media.MIME_TYPE,"video/mp4");values.put(MediaStore.Video.Media.RELATIVE_PATH,"Movies/HeckerSuite");values.put(MediaStore.Video.Media.IS_PENDING,1);
            destination=getContentResolver().insert(MediaStore.Video.Media.EXTERNAL_CONTENT_URI,values);
            if(destination==null)throw new IllegalStateException("No recording destination");
            descriptor=getContentResolver().openFileDescriptor(destination,"w");if(descriptor==null)throw new IllegalStateException("No output descriptor");
            DisplayMetrics metrics=new DisplayMetrics();getSystemService(DisplayManager.class).getDisplay(0).getRealMetrics(metrics);
            float scale=Math.min(1f,1920f/Math.max(metrics.widthPixels,metrics.heightPixels));
            int width=Math.max(2,((int)(metrics.widthPixels*scale))&~1),height=Math.max(2,((int)(metrics.heightPixels*scale))&~1);
            recorder=new MediaRecorder(this);recorder.setVideoSource(MediaRecorder.VideoSource.SURFACE);recorder.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4);
            recorder.setVideoEncoder(MediaRecorder.VideoEncoder.H264);recorder.setVideoSize(width,height);recorder.setVideoFrameRate(30);
            recorder.setVideoEncodingBitRate(Math.max(4000000,Math.min(16000000,width*height*6)));recorder.setOutputFile(descriptor.getFileDescriptor());
            recorder.setOnErrorListener((m,what,extra)->stopSelf());recorder.prepare();
            display=projection.createVirtualDisplay("Hecker game recording",width,height,metrics.densityDpi,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,recorder.getSurface(),null,null);
            if(display==null)throw new IllegalStateException("No capture display");
            recorder.start();started=true;recording=true;
        }catch(Exception e){Log.e("HeckerGaming","Recording failed",e);stopSelf();}
        return START_NOT_STICKY;
    }
    @Override public void onDestroy(){
        if(cleaning)return;cleaning=true;recording=false;boolean success=started;
        if(started&&recorder!=null)try{recorder.stop();}catch(RuntimeException e){success=false;}
        started=false;
        if(display!=null)display.release();if(recorder!=null)recorder.release();
        if(projection!=null){projection.unregisterCallback(callback);projection.stop();}
        if(descriptor!=null)try{descriptor.close();}catch(java.io.IOException ignored){}
        if(destination!=null){
            try{if(success){ContentValues done=new ContentValues();done.put(MediaStore.Video.Media.IS_PENDING,0);getContentResolver().update(destination,done,null,null);}
                else getContentResolver().delete(destination,null,null);
            }catch(RuntimeException e){success=false;}
        }
        Toast.makeText(this,success?getString(R.string.gaming_capture_saved,"Movies/HeckerSuite"):getString(R.string.gaming_capture_error),Toast.LENGTH_LONG).show();
        stopForeground(STOP_FOREGROUND_REMOVE);super.onDestroy();
    }
}
