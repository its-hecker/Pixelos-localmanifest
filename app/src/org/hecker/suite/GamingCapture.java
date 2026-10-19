// SPDX-License-Identifier: Apache-2.0
package org.hecker.suite;

import android.content.ContentValues;
import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.ColorSpace;
import android.hardware.HardwareBuffer;
import android.net.Uri;
import android.os.OutcomeReceiver;
import android.provider.MediaStore;
import java.io.OutputStream;
import java.util.concurrent.Executor;
import java.util.concurrent.Executors;
import java.util.function.Consumer;

final class GamingCapture {
    private static final Executor EXECUTOR=Executors.newSingleThreadExecutor();
    static void screenshot(Context context,Consumer<Boolean> complete){
        Context application=context.getApplicationContext();
        try{
            Class<?> capture=Class.forName("android.window.ScreenCapture");
            Class<?> args=Class.forName("android.window.ScreenCapture$ScreenCaptureParams");
            Class<?> builderType=Class.forName("android.window.ScreenCapture$ScreenCaptureParams$Builder");
            Object builder=builderType.getConstructor(int.class).newInstance(0);
            // REDACT secure/protected content. Never request CAPTURE_BLACKOUT_CONTENT.
            builderType.getMethod("setSecureContentPolicy",int.class).invoke(builder,0);
            builderType.getMethod("setProtectedContentPolicy",int.class).invoke(builder,0);
            Object params=builderType.getMethod("build").invoke(builder);
            capture.getMethod("capture",args,Executor.class,OutcomeReceiver.class).invoke(null,params,EXECUTOR,
                new OutcomeReceiver<Object,Exception>(){
                    @Override public void onResult(Object result){
                        HardwareBuffer buffer=null;Bitmap hardware=null,copy=null;
                        try{
                            buffer=(HardwareBuffer)result.getClass().getMethod("getHardwareBuffer").invoke(result);
                            ColorSpace space=(ColorSpace)result.getClass().getMethod("getColorSpace").invoke(result);
                            hardware=Bitmap.wrapHardwareBuffer(buffer,space);if(hardware==null)throw new IllegalStateException("No screenshot buffer");
                            copy=hardware.copy(Bitmap.Config.ARGB_8888,false);if(copy==null)throw new IllegalStateException("Cannot read screenshot");
                            save(application,copy);complete.accept(true);
                        }catch(Exception e){complete.accept(false);}
                        finally{if(copy!=null)copy.recycle();if(hardware!=null)hardware.recycle();if(buffer!=null)buffer.close();}
                    }
                    @Override public void onError(Exception error){complete.accept(false);}
                });
        }catch(ReflectiveOperationException|RuntimeException e){complete.accept(false);}
    }
    private static void save(Context c,Bitmap bitmap)throws Exception{
        ContentValues values=new ContentValues();values.put(MediaStore.Images.Media.DISPLAY_NAME,"Gaming_"+System.currentTimeMillis()+".png");
        values.put(MediaStore.Images.Media.MIME_TYPE,"image/png");values.put(MediaStore.Images.Media.RELATIVE_PATH,"Pictures/HeckerSuite");values.put(MediaStore.Images.Media.IS_PENDING,1);
        Uri uri=c.getContentResolver().insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI,values);if(uri==null)throw new IllegalStateException("No media destination");
        try{
            try(OutputStream stream=c.getContentResolver().openOutputStream(uri)){if(stream==null||!bitmap.compress(Bitmap.CompressFormat.PNG,100,stream))throw new IllegalStateException("Screenshot write failed");}
            ContentValues done=new ContentValues();done.put(MediaStore.Images.Media.IS_PENDING,0);c.getContentResolver().update(uri,done,null,null);
        }catch(Exception e){c.getContentResolver().delete(uri,null,null);throw e;}
    }
    private GamingCapture(){}
}
