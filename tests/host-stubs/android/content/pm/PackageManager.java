package android.content.pm;
public abstract class PackageManager {
    public static final int PERMISSION_GRANTED = 0;
    public static final int SIGNATURE_MATCH = 0;
    public static class NameNotFoundException extends Exception {}
    public abstract ApplicationInfo getApplicationInfoAsUser(String name, int flags, int user)
            throws NameNotFoundException;
    public abstract int checkSignatures(String one, String two);
}
