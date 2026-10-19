// SPDX-License-Identifier: Apache-2.0
package org.hecker.suite;

import android.app.ActivityManager;
import android.app.ActivityTaskManager;
import android.app.TaskStackListener;

/** Native task events avoid polling for games while the dashboard is idle. */
final class GamingTaskObserver implements AutoCloseable {
    private final TaskStackListener listener;
    GamingTaskObserver(Runnable changed){
        listener=new TaskStackListener(){
            @Override public void onTaskStackChanged(){changed.run();}
            @Override public void onTaskMovedToFront(ActivityManager.RunningTaskInfo task){changed.run();}
            @Override public void onTaskFocusChanged(int taskId,boolean focused){changed.run();}
            @Override public void onTaskRemoved(int taskId){changed.run();}
        };
        ActivityTaskManager.getInstance().registerTaskStackListener(listener);
    }
    @Override public void close(){ActivityTaskManager.getInstance().unregisterTaskStackListener(listener);}
}
