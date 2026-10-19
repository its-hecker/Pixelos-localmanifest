// SPDX-License-Identifier: Apache-2.0
package org.hecker.suite;
import java.util.Set;
import java.util.List;

public final class GamingPolicyTest {
    private static int checks;
    private static void check(boolean condition){checks++;if(!condition)throw new AssertionError("Gaming policy check "+checks);}
    public static void main(String[] args){
        check(GamingPolicy.isGame("game",true,true,Set.of(),Set.of()));
        check(!GamingPolicy.isGame("game",true,false,Set.of(),Set.of()));
        check(GamingPolicy.isGame("manual",false,false,Set.of("manual"),Set.of()));
        check(!GamingPolicy.isGame("game",true,true,Set.of("game"),Set.of("game")));
        check(!GamingPolicy.isGame("other",false,true,Set.of(),Set.of()));
        check(GamingPolicy.retainSession(true,true,true));
        check(!GamingPolicy.retainSession(true,true,false));
        check(!GamingPolicy.retainSession(false,true,true));
        check(!GamingPolicy.retainSession(true,false,true));
        GamingPolicy.Task game=new GamingPolicy.Task(1,"game",true,false,false);
        GamingPolicy.Task popup=new GamingPolicy.Task(2,"chat",true,true,true);
        Set<String> games=Set.of("game","game2"),popups=Set.of("chat");
        check(GamingPolicy.activeGame(List.of(popup,game),games,popups,1,true).id==1);
        check(GamingPolicy.activeGame(List.of(game,popup),games,popups,1,true).id==1);
        check(GamingPolicy.activeGame(List.of(popup,game),games,popups,1,false)==null);
        check(GamingPolicy.activeGame(List.of(popup),games,popups,1,true)==null);
        check(GamingPolicy.activeGame(List.of(popup,new GamingPolicy.Task(1,"game",false,false,false)),games,popups,1,true)==null);
        check(GamingPolicy.activeGame(List.of(new GamingPolicy.Task(2,"chat",true,true,false),game),games,popups,1,true)==null);
        check(GamingPolicy.activeGame(List.of(new GamingPolicy.Task(2,"unknown",true,true,true),game),games,popups,1,true)==null);
        // Native App Lock/system authentication above a game must hide the gaming UI.
        check(GamingPolicy.activeGame(List.of(new GamingPolicy.Task(1,"android",true,true,false)),games,popups,1,true)==null);
        check(GamingPolicy.activeGame(List.of(new GamingPolicy.Task(3,"android",true,true,false),game),games,popups,1,true)==null);
        check(GamingPolicy.activeGame(List.of(game,new GamingPolicy.Task(3,"game2",true,true,false)),games,popups,1,true).id==3);
        Set<Integer> protectedUids=Set.of(11001,11002);
        check(GamingPolicy.canClean(11003,11000,400,false,protectedUids));
        check(!GamingPolicy.canClean(11001,11000,400,false,protectedUids));
        check(!GamingPolicy.canClean(11002,11000,400,false,protectedUids));
        check(!GamingPolicy.canClean(11000,11000,400,false,protectedUids));
        check(!GamingPolicy.canClean(11003,11000,100,false,protectedUids));
        check(!GamingPolicy.canClean(11003,11000,125,false,protectedUids));
        check(!GamingPolicy.canClean(11003,11000,300,false,protectedUids));
        check(!GamingPolicy.canClean(11003,11000,400,true,protectedUids));
        check(!GamingPolicy.canClean(1000,11000,400,false,protectedUids));
        check(!GamingPolicy.canClean(99001,11000,400,false,protectedUids));
        check(!GamingPolicy.canClean(20001,11000,400,false,protectedUids));
        check(!GamingPolicy.canClean(111003,11000,400,false,protectedUids));
        check(GamingPolicy.canClean(111003,111000,400,false,Set.of()));
        check(GamingPolicy.usableFps(0)==0);
        check(GamingPolicy.usableFps(59.9f)==59.9f);
        check(Float.isNaN(GamingPolicy.usableFps(-1)));
        check(Float.isNaN(GamingPolicy.usableFps(Float.NaN)));
        check(Float.isNaN(GamingPolicy.usableFps(Float.POSITIVE_INFINITY)));
        System.out.println("Gaming detection, popup visibility, cleanup protection and real FPS: "+checks+" checks passed");
    }
}
