// SPDX-License-Identifier: Apache-2.0
package org.hecker.suite;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;

public final class GamingBootReceiver extends BroadcastReceiver {
    @Override public void onReceive(Context context,Intent intent){
        if(Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())||Intent.ACTION_MY_PACKAGE_REPLACED.equals(intent.getAction()))GamingService.start(context);
    }
}
