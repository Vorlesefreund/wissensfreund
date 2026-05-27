package de.wissensfreund.wissensfreund_app

import android.app.KeyguardManager
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.view.WindowManager
import androidx.fragment.app.FragmentActivity

/**
 * Transparente Activity für den Eltern-Entsperrfluss.
 *
 * Reihenfolge (wichtig):
 *  1. requestDismissKeyguard() — Keyguard läuft noch
 *  2. Erst im onDismissSucceeded-Callback: released = true (Kiosk freigeben)
 *  3. 150 ms warten, damit Android die Entsperr-Animation abschließt
 *  4. Home-Intent mit FLAG_ACTIVITY_NEW_TASK + finish()
 *
 * setShowWhenLocked(true) sorgt dafür, dass der Entsperr-Dialog auch über
 * dem Sperrbildschirm sichtbar ist.
 */
class ParentalUnlockActivity : FragmentActivity() {

    private val mainHandler = Handler(Looper.getMainLooper())

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) {
            setShowWhenLocked(true)
            setTurnScreenOn(true)
        } else {
            @Suppress("DEPRECATION")
            window.addFlags(
                WindowManager.LayoutParams.FLAG_SHOW_WHEN_LOCKED or
                    WindowManager.LayoutParams.FLAG_TURN_SCREEN_ON
            )
        }

        requestKeyguardDismiss()
    }

    private fun requestKeyguardDismiss() {
        val km = getSystemService(KEYGUARD_SERVICE) as KeyguardManager

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            km.requestDismissKeyguard(this, object : KeyguardManager.KeyguardDismissCallback() {

                override fun onDismissSucceeded() {
                    WissensfreundForegroundService.released = true
                    // 2-Sekunden-Fenster öffnen: verhindert dass MainActivity.onStart/onStop
                    // released zurücksetzt falls Samsung die App während des Keyguard-Dismissals
                    // kurz in den Vordergrund bringt.
                    MainActivity.signalUnlockCompleted()
                    // 300 ms Delay: Samsung braucht länger für die Entsperr-Animation
                    mainHandler.postDelayed({ goHome() }, 300)
                }

                override fun onDismissError() {
                    WissensfreundForegroundService.showOverlay()
                    finish()
                }

                override fun onDismissCancelled() {
                    WissensfreundForegroundService.released = false
                    WissensfreundForegroundService.showOverlay()
                    finish()
                }
            })
        } else {
            // API < 26: kein requestDismissKeyguard → direkt freigeben
            WissensfreundForegroundService.released = true
            mainHandler.postDelayed({ goHome() }, 150)
        }
    }

    private fun goHome() {
        if (!isFinishing) {
            startActivity(Intent(Intent.ACTION_MAIN).apply {
                addCategory(Intent.CATEGORY_HOME)
                flags = Intent.FLAG_ACTIVITY_NEW_TASK
            })
            finish()
        }
    }
}
