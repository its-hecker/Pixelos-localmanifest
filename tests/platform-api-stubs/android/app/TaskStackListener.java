// SPDX-License-Identifier: Apache-2.0
// Compile-only declarations, checked against the selected ROM's actual source.
package android.app;
public abstract class TaskStackListener extends android.os.Binder {
    public void onTaskStackChanged() throws android.os.RemoteException{}
    public void onTaskMovedToFront(ActivityManager.RunningTaskInfo task) throws android.os.RemoteException{}
    public void onTaskFocusChanged(int taskId,boolean focused) throws android.os.RemoteException{}
    public void onTaskRemoved(int taskId) throws android.os.RemoteException{}
}
