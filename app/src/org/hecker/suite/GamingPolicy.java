// SPDX-License-Identifier: Apache-2.0
package org.hecker.suite;

import java.util.Set;
import java.util.List;

/** Pure session/cleanup rules, shared by the service and host regression checks. */
final class GamingPolicy {
    static final class Task {
        final int id;final String pkg;final boolean visible,focused,freeform;
        Task(int id,String pkg,boolean visible,boolean focused,boolean freeform){
            this.id=id;this.pkg=pkg;this.visible=visible;this.focused=focused;this.freeform=freeform;
        }
    }
    static Task activeGame(List<Task> tasks,Set<String> games,Set<String> popups,int previousId,boolean unlocked){
        if(!unlocked)return null;
        Task top=null,previous=null;
        for(Task task:tasks){
            if(task.visible&&(top==null||task.focused))top=task;
            if(task.id==previousId&&task.visible&&games.contains(task.pkg))previous=task;
        }
        if(top==null)return null;
        if(games.contains(top.pkg))return top;
        return retainSession(previous!=null,popups.contains(top.pkg)&&top.freeform,true)?previous:null;
    }
    static boolean isGame(String pkg, boolean categoryGame, boolean automatic,
            Set<String> added, Set<String> excluded) {
        return !excluded.contains(pkg) && (added.contains(pkg) || automatic && categoryGame);
    }
    static boolean retainSession(boolean gameVisible, boolean popupOnTop, boolean unlocked) {
        return unlocked && gameVisible && popupOnTop;
    }
    static boolean canClean(int uid, int ownUid, int importance, boolean system,
            Set<Integer> protectedUids) {
        int appId = uid % 100000;
        // Isolated and SDK sandbox UIDs do not identify an installed app to clean.
        return uid / 100000 == ownUid / 100000 && appId >= 10000 && appId <= 19999
                && importance >= 400 && !system && uid != ownUid && !protectedUids.contains(uid);
    }
    static float usableFps(float value) {
        return Float.isFinite(value) && value >= 0 ? value : Float.NaN;
    }
    private GamingPolicy() {}
}
