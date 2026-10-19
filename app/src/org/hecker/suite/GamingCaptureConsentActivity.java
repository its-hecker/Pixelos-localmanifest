// SPDX-License-Identifier: Apache-2.0
package org.hecker.suite;

import android.app.Activity;
import android.content.Intent;
import android.media.projection.MediaProjectionManager;
import android.os.Bundle;
import android.widget.Toast;

/** System consent is required for each recording; projection tokens are never reused. */
public final class GamingCaptureConsentActivity extends Activity {
    @Override public void onCreate(Bundle state){
        super.onCreate(state);
        if(!GamingPrefs.enabled(this)){finishAndRemoveTask();return;}
        if(state==null){
            try{startActivityForResult(getSystemService(MediaProjectionManager.class).createScreenCaptureIntent(),41);}
            catch(RuntimeException e){Toast.makeText(this,R.string.gaming_capture_error,Toast.LENGTH_LONG).show();finishAndRemoveTask();}
        }
    }
    @Override protected void onActivityResult(int request,int result,Intent data){
        super.onActivityResult(request,result,data);
        if(request==41&&result==RESULT_OK&&data!=null&&GamingPrefs.enabled(this)){
            try{
                startForegroundService(new Intent(this,GamingRecordingService.class).putExtra("result",result).putExtra("projection",data));
                startService(new Intent(this,GamingService.class).setAction(GamingService.RECORD_STARTED));
            }catch(RuntimeException e){Toast.makeText(this,R.string.gaming_capture_error,Toast.LENGTH_LONG).show();}
        }
        finishAndRemoveTask();
    }
}
