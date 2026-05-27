package de.wissensfreund.wissensfreund_app

import android.app.admin.DeviceAdminReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

class WissensfreundDeviceAdmin : DeviceAdminReceiver() {
    override fun onEnabled(context: Context, intent: Intent) {
        Log.d("DeviceAdmin", "Wissensfreund device admin enabled")
    }
    override fun onDisabled(context: Context, intent: Intent) {
        Log.d("DeviceAdmin", "Wissensfreund device admin disabled")
    }
}
