package de.wissensfreund.wissensfreund_app

import android.os.Build
import android.os.Bundle
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity

/**
 * Transparente Activity, die direkt nach dem Tippen auf "Entsperren"
 * im nativen Overlay gestartet wird. Zeigt den System-BiometricPrompt
 * (Fingerabdruck / PIN / Muster) — kein eigenes Flutter-UI nötig.
 *
 * FragmentActivity (statt AppCompatActivity) — benötigt kein AppCompat-Theme,
 * kompatibel mit dem transparenten Android-Basis-Theme.
 *
 * Erfolg  → released = true, Overlay bleibt weg, Activity schließt sich →
 *            Android kehrt zur vorherigen Aufgabe (Recents / Homescreen) zurück.
 * Abbruch → Overlay wird wieder eingeblendet, Activity schließt sich.
 */
class ParentalUnlockActivity : FragmentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        showBiometricPrompt()
    }

    private fun showBiometricPrompt() {
        val executor = ContextCompat.getMainExecutor(this)

        val callback = object : BiometricPrompt.AuthenticationCallback() {
            override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) {
                WissensfreundForegroundService.released = true
                finish()
            }

            override fun onAuthenticationError(errorCode: Int, errString: CharSequence) {
                // Abbruch oder nicht behebarer Fehler → Overlay wieder einblenden
                WissensfreundForegroundService.showOverlay()
                finish()
            }

            override fun onAuthenticationFailed() {
                // Einzelner Fehlversuch — BiometricPrompt zeigt eigene Fehlermeldung
            }
        }

        // BIOMETRIC_WEAK (Frontkamera-Gesichtserkennung) erst ab API 30 mit DEVICE_CREDENTIAL kombinierbar
        val authenticators = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            BiometricManager.Authenticators.BIOMETRIC_STRONG or
                BiometricManager.Authenticators.BIOMETRIC_WEAK or
                BiometricManager.Authenticators.DEVICE_CREDENTIAL
        } else {
            BiometricManager.Authenticators.BIOMETRIC_STRONG or
                BiometricManager.Authenticators.DEVICE_CREDENTIAL
        }

        val promptInfo = BiometricPrompt.PromptInfo.Builder()
            .setTitle("Wissensfreund")
            .setSubtitle("Entsperren")
            .setAllowedAuthenticators(authenticators)
            .build()

        BiometricPrompt(this, executor, callback).authenticate(promptInfo)
    }
}
