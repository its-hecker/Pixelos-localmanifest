package android.content.pm;
public class ApplicationInfo {
    public int uid;
    public boolean privileged;
    public boolean isPrivilegedApp() { return privileged; }
}
