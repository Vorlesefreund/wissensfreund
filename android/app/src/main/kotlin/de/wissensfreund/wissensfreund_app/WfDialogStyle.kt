package de.wissensfreund.wissensfreund_app

import android.app.AlertDialog
import android.content.Context
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.text.InputType
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView

/**
 * Wissensfreund-Optik fuer native Dialoge.
 *
 * Warum das hier existiert: Das Kiosk-Overlay laeuft in einem Foreground-Service
 * ausserhalb von Flutter, seine Dialoge sind deshalb native AlertDialogs. Ohne
 * diese Token saehe derselbe Vorgang (Eltern-PIN eingeben) drinnen nach
 * Wissensfreund und draussen nach System-Android aus.
 *
 * Die Werte spiegeln lib/widgets/parental_pin_dialog.dart — Aenderungen dort
 * gehoeren hier mitgezogen.
 */
object Wf {
    val BG        = Color.parseColor("#FFF8EE")
    val GREEN     = Color.parseColor("#2E7D32")
    val GREEN_LT  = Color.parseColor("#4CAF50")
    val BORDER    = Color.parseColor("#C8E6C9")
    val TEXT      = Color.parseColor("#555555")
    val MUTED     = Color.parseColor("#888888")
    val HINT_BG   = Color.parseColor("#F1F8E9")
    val HINT_TX   = Color.parseColor("#558B2F")
    val ERROR     = Color.parseColor("#C62828")
}

class WfDialogBuilder(private val ctx: Context) {

    private val d = ctx.resources.displayMetrics.density
    private fun dp(x: Int) = (x * d).toInt()

    private val root = LinearLayout(ctx).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(24), dp(22), dp(24), dp(14))
        background = GradientDrawable().apply {
            shape = GradientDrawable.RECTANGLE
            cornerRadius = dp(20).toFloat()
            setColor(Wf.BG)
        }
    }

    private val errorView = TextView(ctx).apply {
        setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
        setTextColor(Wf.ERROR)
        visibility = View.GONE
    }

    private var dialog: AlertDialog? = null

    fun title(text: String) = apply {
        root.addView(LinearLayout(ctx).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(TextView(ctx).apply {
                setText("🔒")
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
            })
            addView(TextView(ctx).apply {
                setText(text)
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 18f)
                setTextColor(Wf.GREEN)
                typeface = Typeface.DEFAULT_BOLD
                setPadding(dp(10), 0, 0, 0)
            })
        })
    }

    fun message(text: String) = apply {
        root.addView(TextView(ctx).apply {
            setText(text)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
            setTextColor(Wf.TEXT)
            setLineSpacing(0f, 1.45f)
            setPadding(0, dp(14), 0, 0)
        })
    }

    /** Hervorgehobene Sicherheitsfrage — Pendant zu _QuestionBox in Dart. */
    fun questionBox(text: String) = apply {
        root.addView(TextView(ctx).apply {
            setText(text)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 13f)
            setTextColor(Color.parseColor("#1B5E20"))
            typeface = Typeface.DEFAULT_BOLD
            setPadding(dp(10), dp(10), dp(10), dp(10))
            background = GradientDrawable().apply {
                shape = GradientDrawable.RECTANGLE
                cornerRadius = dp(10).toFloat()
                setColor(Color.WHITE)
                setStroke(dp(1), Wf.BORDER)
            }
            (layoutParams as? ViewGroup.MarginLayoutParams)?.topMargin = dp(14)
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).also { it.topMargin = dp(14) }
        })
    }

    /** Hinweis-Kasten — Pendant zu _NoteHint in Dart. */
    fun hint(text: String) = apply {
        root.addView(TextView(ctx).apply {
            setText(text)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 11.5f)
            setTextColor(Wf.HINT_TX)
            setLineSpacing(0f, 1.4f)
            setPadding(dp(10), dp(10), dp(10), dp(10))
            background = GradientDrawable().apply {
                shape = GradientDrawable.RECTANGLE
                cornerRadius = dp(10).toFloat()
                setColor(Wf.HINT_BG)
                setStroke(dp(1), Wf.BORDER)
            }
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).also { it.topMargin = dp(14) }
        })
    }

    /** Eingabefeld im App-Stil. [pin] = Ziffern, verdeckt, gesperrt. */
    fun field(hintText: String, pin: Boolean): EditText {
        val e = EditText(ctx).apply {
            hint = hintText
            setHintTextColor(Wf.MUTED)
            setTextColor(Color.parseColor("#333333"))
            background = GradientDrawable().apply {
                shape = GradientDrawable.RECTANGLE
                cornerRadius = dp(12).toFloat()
                setColor(Color.WHITE)
                setStroke(dp(1), Wf.BORDER)
            }
            setPadding(dp(12), dp(12), dp(12), dp(12))
            if (pin) {
                inputType = InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_VARIATION_PASSWORD
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 20f)
                letterSpacing = 0.4f
            } else {
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
            }
            layoutParams = LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ).also { it.topMargin = dp(10) }
        }
        root.addView(e)
        return e
    }

    fun showError(text: String) {
        errorView.text = text
        errorView.visibility = View.VISIBLE
    }

    /**
     * Aktionsleiste. [neutral] steht linksbuendig ("PIN vergessen?"),
     * Abbrechen/Bestaetigen rechts — wie im Flutter-Dialog.
     */
    fun actions(
        positive: String,
        onPositive: () -> Unit,
        onCancel: () -> Unit,
        neutral: String? = null,
        onNeutral: (() -> Unit)? = null,
    ) = apply {
        root.addView(errorView, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        ).also { it.topMargin = dp(10) })

        if (neutral != null && onNeutral != null) {
            root.addView(TextView(ctx).apply {
                setText(neutral)
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 12f)
                setTextColor(Wf.GREEN)
                setPadding(0, dp(12), 0, 0)
                setOnClickListener { onNeutral() }
            })
        }

        root.addView(LinearLayout(ctx).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.END
            setPadding(0, dp(14), 0, 0)
            addView(Button(ctx).apply {
                text = "Abbrechen"
                isAllCaps = false
                setTextColor(Wf.MUTED)
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
                setBackgroundColor(Color.TRANSPARENT)
                setOnClickListener { onCancel() }
            })
            addView(Button(ctx).apply {
                text = positive
                isAllCaps = false
                setTextColor(Color.WHITE)
                setTextSize(TypedValue.COMPLEX_UNIT_SP, 14f)
                typeface = Typeface.DEFAULT_BOLD
                background = GradientDrawable().apply {
                    shape = GradientDrawable.RECTANGLE
                    cornerRadius = dp(24).toFloat()
                    setColor(Wf.GREEN)
                }
                setPadding(dp(24), 0, dp(24), 0)
                layoutParams = LinearLayout.LayoutParams(
                    LinearLayout.LayoutParams.WRAP_CONTENT, dp(44)
                ).also { it.leftMargin = dp(8) }
                setOnClickListener { onPositive() }
            })
        })
    }

    /** Deaktiviert den Bestaetigen-Knopf fuer [ms] — bremst Durchprobieren. */
    fun lockPositive(ms: Long) {
        val bar = root.getChildAt(root.childCount - 1) as? LinearLayout ?: return
        val btn = bar.getChildAt(bar.childCount - 1) as? Button ?: return
        btn.isEnabled = false
        btn.postDelayed({ btn.isEnabled = true }, ms)
    }

    fun show(): AlertDialog {
        val dlg = AlertDialog.Builder(ctx)
            .setView(root)
            .setCancelable(false)
            .create()
        // Systemhintergrund transparent, damit unsere runden Ecken sichtbar sind.
        dlg.window?.setBackgroundDrawableResource(android.R.color.transparent)
        dlg.show()
        dialog = dlg
        return dlg
    }

    fun dismiss() = dialog?.dismiss()
}
