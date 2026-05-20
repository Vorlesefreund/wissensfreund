package de.wissensfreund.wissensfreund_app

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.MediaRecorder
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.util.Log
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodChannel
import java.io.File
import java.util.concurrent.Executors

class MainActivity : FlutterActivity() {

    private val tag = "WissensfreundSTT"
    private val channelName = "wissensfreund/speech"
    private val zimChannelName = "wissensfreund/zim"
    private val zimProgressChannelName = "wissensfreund/zim_progress"

    private var recognizer: SpeechRecognizer? = null
    private var pendingResult: MethodChannel.Result? = null
    private var audioFocusRequest: AudioFocusRequest? = null

    private var zimReader: ZimReader? = null
    private val zimExecutor = Executors.newSingleThreadExecutor()
    private var zimProgressSink: EventChannel.EventSink? = null
    private var zimLoadStarted = false

    companion object {
        private const val MIC_PERMISSION_CODE = 1001
        private const val ZIM_FILENAME = "klexikon.zim"
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), MIC_PERMISSION_CODE)
        }
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, channelName)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "startSpeech" -> startSpeech(result)
                    "stopSpeech"  -> stopSpeech(result)
                    else          -> result.notImplemented()
                }
            }

        EventChannel(flutterEngine.dartExecutor.binaryMessenger, zimProgressChannelName)
            .setStreamHandler(object : EventChannel.StreamHandler {
                override fun onListen(arguments: Any?, events: EventChannel.EventSink?) {
                    zimProgressSink = events
                    if (!zimLoadStarted) {
                        zimLoadStarted = true
                        startZimLoading()
                    }
                }
                override fun onCancel(arguments: Any?) {
                    zimProgressSink = null
                }
            })

        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, zimChannelName)
            .setMethodCallHandler { call, result ->
                when (call.method) {
                    "search"  -> {
                        val query      = call.argument<String>("query") ?: ""
                        val maxResults = call.argument<Int>("maxResults") ?: 5
                        zimSearch(query, maxResults, result)
                    }
                    "article" -> {
                        val urlIndex = call.argument<Int>("urlIndex") ?: -1
                        zimGetArticle(urlIndex, result)
                    }
                    "listImages" -> {
                        val urlIndex = call.argument<Int>("urlIndex") ?: -1
                        zimListImages(urlIndex, result)
                    }
                    "getImageBytes" -> {
                        val filename = call.argument<String>("filename") ?: ""
                        zimGetImageBytes(filename, result)
                    }
                    else -> result.notImplemented()
                }
            }
    }

    // ── ZIM loading (triggered from EventChannel onListen) ───────────────────

    // Search both app-specific external storage (user-visible, cleared on uninstall)
    // and internal files dir (survives reinstall, accessible via adb on debug builds).
    private fun findZimPath(): String? {
        getExternalFilesDir(null)?.let { dir ->
            val f = File(dir, ZIM_FILENAME)
            if (f.exists()) { Log.d("ZimReader", "ZIM found (external): ${f.absolutePath}"); return f.absolutePath }
        }
        val f = File(filesDir, ZIM_FILENAME)
        if (f.exists()) { Log.d("ZimReader", "ZIM found (internal): ${f.absolutePath}"); return f.absolutePath }
        Log.w("ZimReader", "ZIM not found in external (${getExternalFilesDir(null)?.absolutePath}) or internal (${filesDir.absolutePath})")
        return null
    }

    private fun startZimLoading() {
        val zimPath = findZimPath()
        if (zimPath == null) {
            Handler(Looper.getMainLooper()).post {
                zimProgressSink?.success(mapOf("status" to "not_found"))
            }
            return
        }
        zimExecutor.execute {
            val reader = ZimReader(zimPath)
            val ok = reader.open { progress ->
                Handler(Looper.getMainLooper()).post {
                    zimProgressSink?.success(progress)
                }
            }
            if (ok) zimReader = reader
            Handler(Looper.getMainLooper()).post {
                val event = if (ok) {
                    mapOf("status" to "ok", "articleCount" to (zimReader?.allTitles?.size ?: 0))
                } else {
                    mapOf("status" to "not_found")
                }
                zimProgressSink?.success(event)
            }
        }
    }

    // ── ZIM channel handlers ──────────────────────────────────────────────────

    private fun zimSearch(query: String, maxResults: Int, result: MethodChannel.Result) {
        val reader = zimReader
        if (reader == null) { result.success(emptyList<Any>()); return }
        zimExecutor.execute {
            val results = reader.search(query, maxResults)
            Handler(Looper.getMainLooper()).post { result.success(results) }
        }
    }

    private fun zimListImages(urlIndex: Int, result: MethodChannel.Result) {
        val reader = zimReader
        if (reader == null || urlIndex < 0) { result.success(emptyList<Any>()); return }
        zimExecutor.execute {
            val refs = reader.getImageRefs(urlIndex)
            val mapped = refs.map {
                mapOf("filename" to it.filename, "mimeType" to it.mimeType, "caption" to it.caption)
            }
            Handler(Looper.getMainLooper()).post { result.success(mapped) }
        }
    }

    private fun zimGetImageBytes(filename: String, result: MethodChannel.Result) {
        val reader = zimReader
        if (reader == null || filename.isEmpty()) { result.success(null); return }
        zimExecutor.execute {
            val bytes = reader.getImageBytes(filename)
            Handler(Looper.getMainLooper()).post { result.success(bytes) }
        }
    }

    private fun zimGetArticle(urlIndex: Int, result: MethodChannel.Result) {
        val reader = zimReader
        if (reader == null || urlIndex < 0) {
            result.error("ZIM_ERROR", "ZIM not ready or bad index", null); return
        }
        zimExecutor.execute {
            try {
                val art = reader.getArticleByUrlIndex(urlIndex)
                Handler(Looper.getMainLooper()).post { result.success(art) }
            } catch (e: Exception) {
                Log.e("ZimReader", "getArticle($urlIndex) failed: ${e.message}", e)
                Handler(Looper.getMainLooper()).post {
                    result.error("ZIM_ERROR", e.message, null)
                }
            }
        }
    }

    private fun claimAudioFocusForStt() {
        val am = getSystemService(Context.AUDIO_SERVICE) as AudioManager
        am.abandonAudioFocus(null)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val req = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT)
                .setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build()
                )
                .setAcceptsDelayedFocusGain(false)
                .build()
            audioFocusRequest = req
            val res = am.requestAudioFocus(req)
            Log.d(tag, "requestAudioFocus result: $res")
        } else {
            @Suppress("DEPRECATION")
            val res = am.requestAudioFocus(
                null, AudioManager.STREAM_VOICE_CALL, AudioManager.AUDIOFOCUS_GAIN_TRANSIENT
            )
            Log.d(tag, "requestAudioFocus (legacy) result: $res")
        }
    }

    private fun releaseAudioFocus() {
        val am = getSystemService(Context.AUDIO_SERVICE) as AudioManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            audioFocusRequest?.let { am.abandonAudioFocusRequest(it) }
            audioFocusRequest = null
        } else {
            @Suppress("DEPRECATION")
            am.abandonAudioFocus(null)
        }
    }

    private fun startSpeech(result: MethodChannel.Result) {
        runOnUiThread {
            // Request RECORD_AUDIO at runtime if not yet granted (reset on reinstall)
            if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
                pendingResult?.success("")
                pendingResult = result
                requestPermissions(arrayOf(Manifest.permission.RECORD_AUDIO), MIC_PERMISSION_CODE)
                return@runOnUiThread
            }
            pendingResult?.success("")
            pendingResult = result
            claimAudioFocusForStt()
            // Brief delay to let TTS audio session settle, then warmup mic
            Handler(Looper.getMainLooper()).postDelayed({
                doStartRecognition(isRetry = false)
            }, 300)
        }
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == MIC_PERMISSION_CODE) {
            if (grantResults.isNotEmpty() && grantResults[0] == PackageManager.PERMISSION_GRANTED) {
                claimAudioFocusForStt()
                Handler(Looper.getMainLooper()).postDelayed({
                    if (pendingResult != null) doStartRecognition(isRetry = false)
                }, 300)
            } else {
                pendingResult?.success("")
                pendingResult = null
            }
        }
    }

    // Opens AudioRecord briefly in VOICE_RECOGNITION mode to prime the audio driver
    // for speech input (TTS may leave the driver in music-playback mode).
    private fun warmupAndRecognize(isRetry: Boolean) {
        Thread {
            try {
                val bufSize = AudioRecord.getMinBufferSize(
                    16000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT
                )
                if (bufSize > 0) {
                    val ar = AudioRecord(
                        MediaRecorder.AudioSource.VOICE_RECOGNITION,
                        16000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT,
                        bufSize
                    )
                    if (ar.state == AudioRecord.STATE_INITIALIZED) {
                        ar.startRecording()
                        Thread.sleep(150)
                        ar.stop()
                    }
                    ar.release()
                    Log.d(tag, "Mic warmup done")
                }
            } catch (e: Exception) {
                Log.e(tag, "Mic warmup error: ${e.message}")
            }
            Handler(Looper.getMainLooper()).post {
                if (pendingResult != null) startActualRecognition(isRetry)
            }
        }.start()
    }

    private fun doStartRecognition(isRetry: Boolean) {
        recognizer?.cancel()
        recognizer?.destroy()
        recognizer = null
        warmupAndRecognize(isRetry)
    }

    private fun startActualRecognition(isRetry: Boolean) {
        val sr = try {
            if (isRetry) {
                Log.d(tag, "Retry: creating cloud recognizer")
                SpeechRecognizer.createSpeechRecognizer(this)
            } else if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S &&
                SpeechRecognizer.isOnDeviceRecognitionAvailable(this)
            ) {
                Log.d(tag, "First attempt: on-device recognizer")
                SpeechRecognizer.createOnDeviceSpeechRecognizer(this)
            } else {
                Log.d(tag, "First attempt: cloud recognizer (no on-device)")
                SpeechRecognizer.createSpeechRecognizer(this)
            }
        } catch (e: Exception) {
            Log.e(tag, "Failed to create recognizer: ${e.message}")
            releaseAudioFocus()
            pendingResult?.success("")
            pendingResult = null
            return
        }
        recognizer = sr

        sr.setRecognitionListener(object : RecognitionListener {
            override fun onReadyForSpeech(params: Bundle?) { Log.d(tag, "onReadyForSpeech") }
            override fun onBeginningOfSpeech() { Log.d(tag, "onBeginningOfSpeech") }
            override fun onEndOfSpeech() { Log.d(tag, "onEndOfSpeech") }
            override fun onRmsChanged(rmsdB: Float) {}
            override fun onBufferReceived(buffer: ByteArray?) {}
            override fun onPartialResults(partialResults: Bundle?) {}
            override fun onEvent(eventType: Int, params: Bundle?) {}

            override fun onError(error: Int) {
                Log.e(tag, "onError: $error")
                val isTransient = error == SpeechRecognizer.ERROR_RECOGNIZER_BUSY ||
                        error == SpeechRecognizer.ERROR_AUDIO ||
                        error == SpeechRecognizer.ERROR_CLIENT
                if (!isRetry && isTransient && pendingResult != null) {
                    Log.d(tag, "Transient error ($error), retrying in 400ms")
                    Handler(Looper.getMainLooper()).postDelayed({
                        if (pendingResult != null) doStartRecognition(isRetry = true)
                    }, 400)
                } else {
                    releaseAudioFocus()
                    pendingResult?.success("")
                    pendingResult = null
                }
            }

            override fun onResults(results: Bundle?) {
                val text = results
                    ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                    ?.firstOrNull() ?: ""
                Log.d(tag, "onResults: \"$text\"")
                if (text.isEmpty() && !isRetry && pendingResult != null) {
                    Log.d(tag, "Empty result, retrying with cloud recognizer")
                    Handler(Looper.getMainLooper()).postDelayed({
                        if (pendingResult != null) doStartRecognition(isRetry = true)
                    }, 400)
                    return
                }
                releaseAudioFocus()
                pendingResult?.success(text)
                pendingResult = null
            }
        })

        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, "de-DE")
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, false)
            putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, packageName)
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 1500L)
            putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, 1500L)
        }
        sr.startListening(intent)
        Log.d(tag, "startListening called (retry=$isRetry)")
    }

    private fun stopSpeech(result: MethodChannel.Result) {
        runOnUiThread {
            recognizer?.stopListening()
            result.success(null)
        }
    }

    override fun onDestroy() {
        recognizer?.destroy()
        recognizer = null
        zimExecutor.execute { zimReader?.close(); zimReader = null }
        zimExecutor.shutdown()
        super.onDestroy()
    }
}
