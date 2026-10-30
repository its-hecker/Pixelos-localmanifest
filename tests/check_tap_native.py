# SPDX-License-Identifier: Apache-2.0
"""Compile the actual prepared QQS listener with small platform doubles; not a ROM build."""
from pathlib import Path
import argparse
import urllib.request, hashlib, concurrent.futures, subprocess, os
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--rom-root',type=Path,required=True)
parser.add_argument('--cache',type=Path,required=True)
args=parser.parse_args()
cache=args.cache.resolve();cache.mkdir(parents=True,exist_ok=True)
inputs={
 'trove':('org/jetbrains/intellij/deps/trove4j/1.0.20200330/trove4j-1.0.20200330.jar','c5fd725bffab51846bf3c77db1383c60aaaebfe1b7fe2f00d23fe1b7df0a439d'),
'compiler':('org/jetbrains/kotlin/kotlin-compiler-embeddable/2.1.20/kotlin-compiler-embeddable-2.1.20.jar','c54a00718c8c0e3ee858bf42771c7f401c5e3c1738861e18e9536371042fa1b3'),
'stdlib':('org/jetbrains/kotlin/kotlin-stdlib/2.1.20/kotlin-stdlib-2.1.20.jar','1bcc74e8ce84e2c25eaafde10f1248349cce3062b6e36978cbeec610db1e930a'),
'script':('org/jetbrains/kotlin/kotlin-script-runtime/2.1.20/kotlin-script-runtime-2.1.20.jar','ae4397fbb3aa2a1ada09290e753bba99a4114548977c3115526b9958f4cb1a04'),
'reflect':('org/jetbrains/kotlin/kotlin-reflect/1.6.10/kotlin-reflect-1.6.10.jar','3277ac102ae17aad10a55abec75ff5696c8d109790396434b496e75087854203'),
'daemon':('org/jetbrains/kotlin/kotlin-daemon-embeddable/2.1.20/kotlin-daemon-embeddable-2.1.20.jar','d9e83df1d847a201ba3c016a786ced091be9503997d09f6a9cf1796ee489f374'),
'annotations':('org/jetbrains/annotations/13.0/annotations-13.0.jar','ace2a10dc8e2d5fd34925ecac03e4988b2c0f851650c94b8cef49ba1bd111478'),
'coroutines':('org/jetbrains/kotlinx/kotlinx-coroutines-core-jvm/1.8.0/kotlinx-coroutines-core-jvm-1.8.0.jar','9860906a1937490bf5f3b06d2f0e10ef451e65b95b269f22daf68a3d1f5065c5'),
}
def fetch(item):
    name,(url,digest)=item;p=cache/(name+'.jar')
    if not p.exists(): p.write_bytes(urllib.request.urlopen('https://repo.maven.apache.org/maven2/'+url,timeout=60).read())
    assert hashlib.sha256(p.read_bytes()).hexdigest()==digest,name
    return p
with concurrent.futures.ThreadPoolExecutor(max_workers=7) as pool: jars=list(pool.map(fetch,inputs.items()))
print('Compiler artifacts verified',flush=True)
source=args.rom_root / 'frameworks/base/packages/SystemUI/src/com/android/systemui/shade/QQSGestureListener.kt'
src=cache/'src';src.mkdir(exist_ok=True)
stubs={
'Context.kt':'''package android.content
class Context(val resources: android.content.res.Resources = android.content.res.Resources()) { val contentResolver=Any() }
''',
'Resources.kt':'''package android.content.res
class Resources { var defaultEnabled=false; fun getBoolean(id:Int)=defaultEnabled; fun getDimensionPixelSize(id:Int)=100 }
''',
'Power.kt':'''package android.os
class PowerManager { var sleeps=0; var time=0L; fun goToSleep(value:Long) { sleeps++; time=value } }
object UserHandle { const val USER_CURRENT = -2 }
''',
'Settings.kt':'''package android.provider
object Settings { object System {
 const val DOUBLE_TAP_SLEEP_GESTURE="double_tap_sleep_gesture"
 var currentUser=0
 val values=mutableMapOf<Int,Int>()
 fun getIntForUser(resolver:Any,key:String,default:Int,user:Int):Int {
  check(key==DOUBLE_TAP_SLEEP_GESTURE && user==android.os.UserHandle.USER_CURRENT)
  return values[currentUser] ?: default
 }
} }
''',
'Touch.kt':'''package android.view
class GestureDetector { open class SimpleOnGestureListener { open fun onDoubleTapEvent(e:MotionEvent)=false } }
class MotionEvent(val actionMasked:Int,val y:Float=0f,val time:Long=123L) {
 fun getY()=y; fun getEventTime()=time
 companion object { const val ACTION_UP=1; const val ACTION_DOWN=0; const val ACTION_CANCEL=3 }
}
''',
'Annotation.kt':'''package com.android.systemui.dagger
annotation class SysUISingleton
''',
'Inject.kt':'''package javax.inject
annotation class Inject
''',
'Falsing.kt':'''package com.android.systemui.plugins
class FalsingManager { var isFalseDoubleTap=false }
''',
'State.kt':'''package com.android.systemui.plugins.statusbar
class StatusBarStateController { var isDozing=false; var state=0; fun getState()=state }
''',
'Constants.kt':'''package com.android.systemui.statusbar
object StatusBarState { const val KEYGUARD=1 }
''',
'Central.kt':'''package com.android.systemui.statusbar.phone
class CentralSurfaces { var bouncer=false; fun isBouncerShowing()=bouncer }
''',
'R.kt':'''package com.android.internal
object R { object bool { const val config_dt2sGestureEnabledByDefault=1 }; object dimen { const val quick_qs_offset_height=2 } }
''',
'Probe.kt':'''import android.content.Context
import android.os.PowerManager
import android.provider.Settings
import android.view.MotionEvent
import com.android.systemui.plugins.FalsingManager
import com.android.systemui.plugins.statusbar.StatusBarStateController
import com.android.systemui.statusbar.phone.CentralSurfaces
import com.android.systemui.shade.QQSGestureListener
object Probe {
 @JvmStatic fun main(args:Array<String>) {
  val c=Context(); val p=PowerManager(); val f=FalsingManager(); val s=StatusBarStateController(); val b=CentralSurfaces()
  val listener=QQSGestureListener(c,f,p,s,b)
  var cases=0
  fun tap(expected:Boolean,y:Float=0f,action:Int=MotionEvent.ACTION_UP) {
   val count=p.sleeps
   check(listener.onDoubleTapEvent(MotionEvent(action,y))==expected)
   check(p.sleeps==count+(if(expected) 1 else 0))
   if(expected) check(p.time==123L)
   cases++
  }
  tap(false)
  Settings.System.values[0]=1; tap(true)
  tap(false,action=MotionEvent.ACTION_DOWN); tap(false,action=MotionEvent.ACTION_CANCEL)
  tap(false,y=200f); s.state=1; tap(true,y=200f)
  s.isDozing=true; tap(false); tap(false,y=200f); s.isDozing=false
  b.bouncer=true; tap(false); tap(false,y=200f); b.bouncer=false
  f.isFalseDoubleTap=true; tap(false); f.isFalseDoubleTap=false
  Settings.System.values[0]=0; tap(false)
  Settings.System.currentUser=10; tap(false); Settings.System.values[10]=1; tap(true)
  Settings.System.currentUser=0; tap(false)
  Settings.System.values.clear(); c.resources.defaultEnabled=true; tap(true)
  c.resources.defaultEnabled=false; tap(false)
  println("Actual patched QQSGestureListener compiled: $cases toggle/user/doze/bouncer/falsing/action/region cases PASS")
 }
}
''',
}
# Avoid synthetic JVM getter collisions in Kotlin-only framework stubs.
stubs['Touch.kt']=stubs['Touch.kt'].replace('val y:Float','private val y:Float')
stubs['State.kt']=stubs['State.kt'].replace('var state=0; fun getState()=state','var mode=0; fun getState()=mode')
stubs['Probe.kt']=stubs['Probe.kt'].replace('s.state=1','s.mode=1')
for name,text in stubs.items(): (src/name).write_text(text)
(src/'QQSGestureListener.kt').write_text(source.read_text())
classpath=os.pathsep.join(map(str,jars)); output=cache/'classes'
subprocess.run(['java','-cp',classpath,'org.jetbrains.kotlin.cli.jvm.K2JVMCompiler','-jvm-target','17','-no-stdlib','-no-reflect','-classpath',str(cache/'stdlib.jar'),'-d',str(output),*map(str,src.glob('*.kt'))],check=True)
subprocess.run(['java','-cp',str(output)+os.pathsep+str(cache/'stdlib.jar'),'Probe'],check=True)
