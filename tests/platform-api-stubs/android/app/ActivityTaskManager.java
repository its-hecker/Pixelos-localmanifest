// SPDX-License-Identifier: Apache-2.0
// Compile-only declaration for the @TestApi surface omitted from the system SDK.
// Never included by Android.bp. prepare.py checks the real framework declarations.
package android.app;
public class ActivityTaskManager {
    public static ActivityTaskManager getInstance(){throw new UnsupportedOperationException();}
    public void registerTaskStackListener(TaskStackListener listener){throw new UnsupportedOperationException();}
    public void unregisterTaskStackListener(TaskStackListener listener){throw new UnsupportedOperationException();}
}
