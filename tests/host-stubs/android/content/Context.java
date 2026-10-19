package android.content;
import android.content.pm.PackageManager;
public abstract class Context {
    public abstract int checkPermission(String permission, int pid, int uid);
    public abstract PackageManager getPackageManager();
}
