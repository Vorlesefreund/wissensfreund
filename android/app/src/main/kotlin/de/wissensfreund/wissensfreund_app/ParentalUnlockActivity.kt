package de.wissensfreund.wissensfreund_app

import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.view.WindowManager
import androidx.biometric.BiometricManager
import androidx.biometric.BiometricPrompt
import androidx.core.content.ContextCompat
import androidx.fragment.app.FragmentActivity
import java.security.MessageDigest
import java.security.SecureRandom

/**
 * Entsperr-Dialog des Kiosk-Overlays.
 *
 * Zwei Wege, analog zu ParentalLockService.authenticate() auf der Dart-Seite:
 *  1. Geraetesperre (Biometrie/Geraete-PIN/Muster) — gewinnt immer, wenn vorhanden.
 *  2. Sonst: App-eigene Eltern-PIN, mit Sicherheitsfrage als Wiederherstellung.
 *
 * WICHTIG: Das Overlay laeuft in einem Foreground-Service ausserhalb von Flutter
 * und kann den Dart-PIN-Dialog nicht aufrufen. Pruefung und Optik sind deshalb
 * hier nativ nachgebaut — gegen exakt denselben gesalzenen SHA-256, den
 * ParentalLockService.setAppPin() in die Flutter-SharedPreferences schreibt.
 * ACHTUNG, Bruchstelle: Aendert sich das Hash-Verfahren auf der Dart-Seite, MUSS
 * es hier mitgezogen werden — sonst sperrt sich die Familie aus.
 *
 * Vorher lief hier ausschliesslich BiometricPrompt. Auf einem Geraet ohne
 * Sperrbildschirm gibt es keinen der erlaubten Authentifikatoren → der Prompt
 * brach sofort ab und "Entsperren" tat sichtbar nichts (PO-Fund am Tablet).
 */
class ParentalUnlockActivity : FragmentActivity() {

    private var failures = 0

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

        if (deviceLockAvailable()) showBiometricPrompt() else showPinDialog()
    }

    // ── Weg 1: Geraetesperre ─────────────────────────────────────────────────

    private val authenticators =
        BiometricManager.Authenticators.BIOMETRIC_STRONG or
            BiometricManager.Authenticators.BIOMETRIC_WEAK or
            BiometricManager.Authenticators.DEVICE_CREDENTIAL

    private fun deviceLockAvailable(): Boolean =
        BiometricManager.from(this).canAuthenticate(authenticators) ==
            BiometricManager.BIOMETRIC_SUCCESS

    private fun showBiometricPrompt() {
        val executor = ContextCompat.getMainExecutor(this)
        val prompt = BiometricPrompt(this, executor, object : BiometricPrompt.AuthenticationCallback() {
            override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult) =
                unlockAndLeave()

            override fun onAuthenticationError(errorCode: Int, errString: CharSequence) = abort()

            override fun onAuthenticationFailed() {
                // Falscher Fingerabdruck — Prompt bleibt offen
            }
        })

        val info = BiometricPrompt.PromptInfo.Builder()
            .setTitle("Kinderschutz")
            .setSubtitle("Bitte Eltern-Biometrie oder PIN bestätigen")
            .setAllowedAuthenticators(authenticators)
            .build()

        prompt.authenticate(info)
    }

    // ── Weg 2: App-eigene Eltern-PIN ─────────────────────────────────────────

    private fun showPinDialog() {
        val hash = flutterPref("parental_pin_hash")
        val salt = flutterPref("parental_pin_salt")
        // Keine PIN hinterlegt → nichts zu pruefen. Fail-closed: Overlay bleibt.
        if (hash == null || salt == null) {
            abort()
            return
        }
        val hasQuestion = flutterPref("parental_sec_question") != null

        val b = WfDialogBuilder(this)
        b.title("Eltern-PIN")
        b.message("Bitte gib die Eltern-PIN ein, um das Gerät freizugeben.")
        val input = b.field("PIN", pin = true)
        b.actions(
            positive = "Entsperren",
            onPositive = {
                val pin = input.text.toString().trim()
                if (sha256("$salt:$pin") == hash) {
                    b.dismiss()
                    unlockAndLeave()
                } else {
                    failures++
                    input.text.clear()
                    b.showError("Falsche PIN.")
                    // Wachsende Sperre bremst Durchprobieren (4 Stellen = 10.000 Kombis).
                    b.lockPositive(400L * failures)
                }
            },
            onCancel = { b.dismiss(); abort() },
            neutral = if (hasQuestion) "PIN vergessen?" else null,
            onNeutral = if (hasQuestion) ({ b.dismiss(); showRecoveryDialog() }) else null,
        )
        b.show()
    }

    // ── Weg 2b: Wiederherstellung per Sicherheitsfrage ───────────────────────

    private fun showRecoveryDialog() {
        val question = flutterPref("parental_sec_question")
        val hash     = flutterPref("parental_sec_answer_hash")
        val salt     = flutterPref("parental_sec_answer_salt")
        if (question == null || hash == null || salt == null) {
            abort()
            return
        }

        val b = WfDialogBuilder(this)
        b.title("PIN zurücksetzen")
        b.message("Beantworte deine Sicherheitsfrage, um eine neue PIN zu vergeben.")
        b.questionBox(question)
        val input = b.field("Deine Antwort", pin = false)
        b.actions(
            positive = "Weiter",
            onPositive = {
                // Normalisierung muss dem Dart-Pendant entsprechen: trim + lowercase.
                val answer = input.text.toString().trim().lowercase()
                if (sha256("$salt:$answer") == hash) {
                    b.dismiss()
                    showNewPinDialog()
                } else {
                    failures++
                    b.showError("Antwort stimmt nicht.")
                    b.lockPositive(400L * failures)
                }
            },
            onCancel = { b.dismiss(); abort() },
        )
        b.show()
    }

    /** Neue PIN vergeben — die Sicherheitsfrage bleibt bestehen. */
    private fun showNewPinDialog() {
        val b = WfDialogBuilder(this)
        b.title("Neue Eltern-PIN")
        b.message("Vergib eine neue PIN für den Eltern-Bereich.")
        val pin1 = b.field("Neue PIN", pin = true)
        val pin2 = b.field("PIN wiederholen", pin = true)
        b.hint("Notiere die PIN oder fotografiere sie — bewahre sie ausserhalb " +
            "der Reichweite deines Kindes auf.")
        b.actions(
            positive = "Speichern",
            onPositive = {
                val a = pin1.text.toString().trim()
                val c = pin2.text.toString().trim()
                when {
                    a.length != 4 -> b.showError("Bitte 4 Ziffern eingeben.")
                    a != c        -> b.showError("Die PINs stimmen nicht überein.")
                    else -> {
                        saveNewPin(a)
                        b.dismiss()
                        unlockAndLeave()
                    }
                }
            },
            onCancel = { b.dismiss(); abort() },
        )
        b.show()
    }

    // ── Prefs / Hash ─────────────────────────────────────────────────────────

    /** Liest einen von Flutter geschriebenen Wert (shared_preferences → "flutter."-Praefix). */
    private fun flutterPref(key: String): String? =
        getSharedPreferences("FlutterSharedPreferences", Context.MODE_PRIVATE)
            .getString("flutter.$key", null)

    /**
     * Schreibt die neue PIN in dieselben Flutter-Prefs, die die Dart-Seite liest.
     * Dart cached SharedPreferences im Speicher — ParentalLockService._loadPinState()
     * ruft deshalb reload(), sonst pruefte die App weiter gegen den alten Hash.
     */
    private fun saveNewPin(pin: String) {
        val bytes = ByteArray(16).also { SecureRandom().nextBytes(it) }
        val salt = android.util.Base64.encodeToString(
            bytes, android.util.Base64.URL_SAFE or android.util.Base64.NO_WRAP
        )
        getSharedPreferences("FlutterSharedPreferences", Context.MODE_PRIVATE).edit()
            .putString("flutter.parental_pin_salt", salt)
            .putString("flutter.parental_pin_hash", sha256("$salt:$pin"))
            .apply()
    }

    /** Muss byteweise dem Dart-Pendant entsprechen: sha256(utf8("salt:wert")) als Kleinbuchstaben-Hex. */
    private fun sha256(value: String): String =
        MessageDigest.getInstance("SHA-256")
            .digest(value.toByteArray(Charsets.UTF_8))
            .joinToString("") { "%02x".format(it) }

    // ── Ausgaenge ────────────────────────────────────────────────────────────

    private fun unlockAndLeave() {
        WissensfreundForegroundService.released = true
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1) setShowWhenLocked(false)
        startActivity(Intent(Intent.ACTION_MAIN).apply {
            addCategory(Intent.CATEGORY_HOME)
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        })
        finishAffinity()
    }

    private fun abort() {
        WissensfreundForegroundService.released = false
        WissensfreundForegroundService.showOverlay()
        finish()
    }
}
