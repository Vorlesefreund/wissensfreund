package de.wissensfreund.wissensfreund_app

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.Color
import android.graphics.PixelFormat
import android.graphics.Typeface
import android.os.Build
import android.os.Handler
import android.os.IBinder
import android.os.Looper
import android.provider.Settings
import android.util.Log
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView

class WissensfreundForegroundService : Service() {

    companion object {
        private const val TAG             = "WfOverlay"
        private const val NOTIFICATION_ID = 42
        private const val CHANNEL_ID      = "wissensfreund_kiosk"

        @Volatile var instance: WissensfreundForegroundService? = null

        // "Gerät freigeben" — Overlay pausiert bis Wissensfreund wieder geöffnet wird
        @Volatile var released = false

        fun showOverlay() { instance?.postOnMain { instance?.showOverlayInternal() } }
        fun hideOverlay() { instance?.postOnMain { instance?.hideOverlayInternal() } }
    }

    private val mainHandler = Handler(Looper.getMainLooper())
    private fun postOnMain(block: () -> Unit) {
        if (Looper.myLooper() == Looper.getMainLooper()) block() else mainHandler.post(block)
    }

    private var wm: WindowManager? = null
    private var overlayRoot: FrameLayout? = null
    private var overlayAdded = false

    // ── Lifecycle ────────────────────────────────────────────────────────────

    override fun onCreate() {
        super.onCreate()
        instance = this
        wm = getSystemService(WINDOW_SERVICE) as WindowManager
        overlayRoot = buildOverlayView()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(NOTIFICATION_ID, buildNotification(), ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE)
        } else {
            startForeground(NOTIFICATION_ID, buildNotification())
        }
        Log.d(TAG, "Foreground Service gestartet")
    }

    override fun onDestroy() {
        hideOverlayInternal()
        instance = null
        super.onDestroy()
        Log.d(TAG, "Foreground Service beendet")
    }

    override fun onBind(intent: Intent?): IBinder? = null

    // ── Notification ─────────────────────────────────────────────────────────

    private fun buildNotification(): Notification {
        val nm = getSystemService(NOTIFICATION_SERVICE) as NotificationManager
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "Kinderschutz", NotificationManager.IMPORTANCE_LOW)
                .apply { setShowBadge(false) }
        )
        return Notification.Builder(this, CHANNEL_ID)
            .setContentTitle("Kinderschutz aktiv")
            .setContentText("Wissensfreund schützt dein Kind")
            .setSmallIcon(android.R.drawable.ic_lock_lock)
            .setOngoing(true)
            .build()
    }

    // ── Overlay ───────────────────────────────────────────────────────────────

    fun showOverlayInternal() {
        if (overlayAdded) return
        if (!Settings.canDrawOverlays(this)) {
            Log.w(TAG, "canDrawOverlays = false — Overlay nicht möglich")
            return
        }
        try {
            val params = WindowManager.LayoutParams(
                WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.MATCH_PARENT,
                WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
                WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or
                    WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS or
                    WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE,
                PixelFormat.OPAQUE
            )
            wm?.addView(overlayRoot, params)
            overlayAdded = true
            Log.d(TAG, "Overlay eingeblendet")
        } catch (e: Exception) {
            Log.e(TAG, "addView fehlgeschlagen: ${e.message}")
        }
    }

    fun hideOverlayInternal() {
        if (!overlayAdded) return
        try {
            wm?.removeView(overlayRoot)
            overlayAdded = false
            Log.d(TAG, "Overlay ausgeblendet")
        } catch (e: Exception) {
            Log.e(TAG, "removeView fehlgeschlagen: ${e.message}")
        }
    }

    // ── Overlay-UI (programmatisch, kein XML benötigt) ────────────────────────

    private fun buildOverlayView(): FrameLayout {
        val d = resources.displayMetrics.density
        fun dp(x: Int) = (x * d).toInt()

        val root = FrameLayout(this).apply {
            setBackgroundColor(Color.parseColor("#FFF8EE"))
            setOnClickListener { /* blockiert alle Touch-Events */ }
            isClickable = true
        }

        val col = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER_HORIZONTAL
            setPadding(dp(40), 0, dp(40), 0)
        }

        // Logo
        col.addView(TextView(this).apply {
            text = "🎓"; textSize = 52f; gravity = Gravity.CENTER
        })
        // App-Name
        col.addView(TextView(this).apply {
            text = "Wissensfreund"; textSize = 24f; gravity = Gravity.CENTER
            setTextColor(Color.parseColor("#2E7D32"))
            typeface = Typeface.DEFAULT_BOLD
            setPadding(0, dp(4), 0, 0)
        })
        // Schloss-Kreis
        col.addView(FrameLayout(this).apply {
            val size = dp(96)
            layoutParams = LinearLayout.LayoutParams(size, size).also { it.topMargin = dp(40) }
            background = android.graphics.drawable.GradientDrawable().apply {
                shape = android.graphics.drawable.GradientDrawable.OVAL
                setColor(Color.parseColor("#E8F5E9"))
            }
            addView(TextView(this@WissensfreundForegroundService).apply {
                text = "🔒"; textSize = 38f; gravity = Gravity.CENTER
                layoutParams = FrameLayout.LayoutParams(
                    FrameLayout.LayoutParams.MATCH_PARENT,
                    FrameLayout.LayoutParams.MATCH_PARENT
                )
            })
        })
        // "Für Erwachsene"
        col.addView(TextView(this).apply {
            text = "Für Erwachsene"; textSize = 22f; gravity = Gravity.CENTER
            setTextColor(Color.parseColor("#2E7D32")); typeface = Typeface.DEFAULT_BOLD
            setPadding(0, dp(28), 0, 0)
        })
        // Hinweistext
        col.addView(TextView(this).apply {
            text = "Bitte Fingerabdruck oder PIN eingeben"
            textSize = 14f; gravity = Gravity.CENTER
            setTextColor(Color.parseColor("#555555"))
            setPadding(0, dp(8), 0, 0)
        })
        // Entsperren-Button (Eltern)
        col.addView(Button(this).apply {
            text = "Entsperren"
            setTextColor(Color.WHITE); textSize = 16f; isAllCaps = false
            typeface = Typeface.DEFAULT_BOLD
            background = android.graphics.drawable.GradientDrawable().apply {
                shape = android.graphics.drawable.GradientDrawable.RECTANGLE
                cornerRadius = dp(50).toFloat()
                setColor(Color.parseColor("#2E7D32"))
            }
            val lp = LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, dp(58))
            lp.topMargin = dp(40)
            layoutParams = lp
            setOnClickListener { onUnlockTapped() }
        })
        // Trennlinie
        col.addView(View(this).apply {
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, dp(1)
            ).also { it.topMargin = dp(28) }
            setBackgroundColor(Color.parseColor("#E0E0E0"))
        })
        // Zurück-zu-Wissensfreund (Kind)
        col.addView(Button(this).apply {
            text = "Zurück zu Wissensfreund"
            setTextColor(Color.parseColor("#555555")); textSize = 15f; isAllCaps = false
            setBackgroundColor(Color.TRANSPARENT)
            val lp = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, dp(52)
            ).also { it.topMargin = dp(4) }
            layoutParams = lp
            setOnClickListener { onBackToWissensfreundTapped() }
        })

        root.addView(col, FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.WRAP_CONTENT,
            Gravity.CENTER
        ))
        return root
    }

    // Entsperren: Overlay ausblenden, transparente BiometricPrompt-Activity starten.
    // Bei Abbruch stellt ParentalUnlockActivity das Overlay wieder her.
    private fun onUnlockTapped() {
        hideOverlayInternal()
        val intent = Intent(this, ParentalUnlockActivity::class.java)
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        startActivity(intent)
    }

    // Kind kehrt zurück: Overlay ausblenden, Wissensfreund in Vordergrund.
    private fun onBackToWissensfreundTapped() {
        hideOverlayInternal()
        val intent = packageManager.getLaunchIntentForPackage(packageName) ?: return
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_REORDER_TO_FRONT)
        startActivity(intent)
    }
}
