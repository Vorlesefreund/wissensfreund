package de.wissensfreund.wissensfreund_app

import android.util.Log
import org.tukaani.xz.XZInputStream
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.RandomAccessFile
import java.nio.ByteBuffer
import java.nio.ByteOrder

class ZimReader(private val filePath: String) {

    companion object {
        private const val TAG = "ZimReader"
        private const val ZIM_MAGIC = 0x044D495AL
        private const val MIME_REDIRECT = 0xFFFF

        // German stopwords: query prefixes, filler words, articles, prepositions, etc.
        // These must NOT be used as search terms — they'd match irrelevant articles.
        private val STOPWORDS = setOf(
            // Query-style prefixes / interrogatives
            "erzähl", "erzähle", "erkläre", "erklärt", "sag", "sage", "sagt",
            "was", "wer", "wie", "warum", "wann", "wem", "wen",
            "wo", "woher", "wohin", "wozu", "wieso", "weshalb",
            "welche", "welcher", "welches", "welchem", "welchen",
            // Filler
            "mir", "dir", "uns", "euch", "ihm", "ihnen", "sich",
            "bitte", "gerne", "mal", "doch", "denn", "eigentlich",
            "etwas", "alles", "nichts", "sehr", "viel", "mehr",
            "wirklich", "echt", "halt", "eben", "schon", "noch",
            // Articles and pronouns
            "der", "die", "das", "dem", "den", "des",
            "ein", "eine", "einen", "einem", "einer", "eines",
            "kein", "keine", "keinen", "keinem", "keiner", "keines",
            "ich", "du", "er", "sie", "es", "wir", "ihr",
            "mich", "dich", "ihn",
            "mein", "dein", "sein", "unser", "euer",
            // Prepositions
            "an", "auf", "aus", "bei", "bis", "durch", "für", "gegen",
            "in", "mit", "nach", "neben", "ob", "ohne", "seit",
            "über", "um", "unter", "von", "vor", "während", "wegen",
            "zu", "zwischen",
            // Conjunctions
            "und", "oder", "aber", "auch", "weil", "wenn",
            "dass", "als", "damit", "obwohl",
            // Common verbs (including knowledge/query verbs)
            "ist", "sind", "war", "waren", "bin", "bist",
            "hat", "haben", "hatte", "hatten",
            "wird", "werden", "wurde", "wurden",
            "kann", "können", "konnte", "will", "wollen",
            "soll", "sollen", "muss", "müssen",
            "weiß", "weißt", "wissen", "wisst", "kennen", "kennst", "weißt",
            "magst", "magst", "möchtest", "möchte", "mögen",
            // Other
            "hier", "da", "dort", "nicht", "nun", "jetzt", "dann",
            "immer", "ja", "nein", "so"
        )
    }

    private var raf: RandomAccessFile? = null

    private var majorVersion = 0
    private var articleCount = 0
    private var clusterCount = 0
    private var urlPtrPos   = 0L
    private var titlePtrPos = 0L
    private var clusterPtrPos = 0L
    private var mimeListPos = 0L

    private var urlPtrs        = LongArray(0)
    private var titlePtrs      = IntArray(0)
    private var clusterPtrs    = LongArray(0)
    private var hasTitleIndex  = true        // false for ZIM v6 (titlePtrPos == -1)
    private var htmlMimeIndices = emptySet<Int>()  // MIME type indices for text/html

    // title-sorted list: Pair(urlIndex, title) — loaded once at open
    val allTitles = mutableListOf<Pair<Int, String>>()

    // ── Public API ─────────────────────────────────────────────────────────────

    fun open(onProgress: ((Double) -> Unit)? = null): Boolean {
        return try {
            raf = RandomAccessFile(filePath, "r")
            readHeader()
            readMimeTypes()
            readPtrTables()
            loadAllTitles(onProgress)
            Log.d(TAG, "ZIM open: $articleCount articles, $clusterCount clusters, ${allTitles.size} readable")
            true
        } catch (e: Exception) {
            Log.e(TAG, "open failed: ${e.message}", e)
            false
        }
    }

    fun close() {
        raf?.close()
        raf = null
    }

    /**
     * Returns scored results sorted by score descending.
     * Scoring (per matched term):
     *   Title match        +3
     *   First-para match   +2
     *   Body match         +1
     *   Multiple terms in same article → multiply accumulated bonus
     */
    fun search(query: String, maxResults: Int = 5): List<Map<String, Any>> {
        val terms = query.lowercase()
            .split(Regex("[\\s,?!.]+"))
            .filter { it.length >= 2 && it !in STOPWORDS }
        if (terms.isEmpty()) return emptyList()

        // Phase 1: fast title scan
        data class Candidate(val urlIndex: Int, val title: String, var score: Int)
        val candidates = mutableListOf<Candidate>()

        for ((urlIndex, title) in allTitles) {
            val tl   = title.lowercase()
            val tlN  = normalizeUmlauts(tl)   // umlaut-folded for fuzzy matching
            var score = 0
            var hits  = 0
            for (term in terms) {
                val termN = normalizeUmlauts(term)
                val pts = when {
                    tl == term                                    -> 5  // exact
                    tl.length >= 4 && term.startsWith(tl)        -> 4  // inflection (hunde→hund)
                    tl.startsWith(term)                           -> 3  // title prefix
                    tlN == termN                                  -> 5  // exact after umlaut fold
                    tlN.length >= 4 && termN.startsWith(tlN)     -> 4  // inflection after fold
                    tlN.startsWith(termN)                         -> 3  // prefix after fold (mäuse→maus)
                    tl.contains(term)                             -> 1  // compound
                    tl.length >= 4 && term.contains(tl)          -> 1  // reverse substring
                    tlN.contains(termN)                           -> 1  // compound after fold
                    else                                          -> 0
                }
                if (pts > 0) { score += pts; hits++ }
            }
            if (score > 0) {
                val finalScore = if (hits > 1) (score * hits * 0.7).toInt() else score
                candidates.add(Candidate(urlIndex, title, finalScore))
            }
        }

        candidates.sortByDescending { it.score }
        val top = candidates.take(20)

        // Phase 2: re-score top candidates with article body
        val reScored = top.map { c ->
            try {
                val art = getArticleByUrlIndex(c.urlIndex)
                val paraLower = art["firstParagraph"]!!.lowercase()
                val bodyLower = art["text"]!!.lowercase()
                var bonus = 0
                var bodyHits = 0
                for (term in terms) {
                    when {
                        paraLower.contains(term) -> { bonus += 2; bodyHits++ }
                        bodyLower.contains(term)  -> { bonus += 1; bodyHits++ }
                    }
                }
                val finalScore = if (bodyHits > 1) c.score + bonus * bodyHits else c.score + bonus
                c.copy(score = finalScore)
            } catch (_: Exception) { c }
        }

        return reScored
            .sortedByDescending { it.score }
            .take(maxResults)
            .map { mapOf("urlIndex" to it.urlIndex, "title" to it.title, "score" to it.score) }
    }

    fun getArticleByUrlIndex(urlIndex: Int): Map<String, String> {
        val entry = readDirEntry(urlIndex)
            ?: throw IllegalStateException("No entry at $urlIndex")

        // Follow redirect chain (max 5 hops)
        var cur = entry
        repeat(5) {
            if (cur.mimeType != MIME_REDIRECT) return@repeat
            cur = readDirEntry(cur.redirectIndex)
                ?: throw IllegalStateException("Broken redirect")
        }
        if (cur.mimeType == MIME_REDIRECT) throw IllegalStateException("Redirect loop")

        val (clusterData, extOffsets) = readCluster(cur.clusterNumber)
        val blob = extractBlob(clusterData, cur.blobNumber, extOffsets)
        val html = blob.toString(Charsets.UTF_8)
        val text = htmlToText(html)
        val firstPara = extractFirstParagraph(html)
        val title = cur.title.ifEmpty { cur.url }
        val zimUrl = cur.url.removePrefix("A/").removePrefix("C/").trim()

        return mapOf("title" to title, "text" to text, "firstParagraph" to firstPara, "url" to zimUrl)
    }

    // ── Media extraction (images + audio) ────────────────────────────────────

    data class ImageRef(
        val filename: String,
        val mimeType: String,
        val caption: String?,
        val posInHtml: Int = 0,
    )

    data class AudioRef(
        val filename: String,
        val mimeType: String,
        val caption: String?,
        val posInHtml: Int = 0,
    )

    fun getImageRefs(articleUrlIndex: Int): List<ImageRef> {
        var cur = readDirEntry(articleUrlIndex) ?: return emptyList()
        for (i in 0 until 5) {
            if (cur.mimeType != MIME_REDIRECT) break
            cur = readDirEntry(cur.redirectIndex) ?: return emptyList()
        }
        if (cur.mimeType == MIME_REDIRECT) return emptyList()
        return try {
            val (data, ext) = readCluster(cur.clusterNumber)
            val html = extractBlob(data, cur.blobNumber, ext).toString(Charsets.UTF_8)
            extractImageRefsFromHtml(html)
        } catch (e: Exception) {
            Log.e(TAG, "getImageRefs($articleUrlIndex) failed: ${e.message}")
            emptyList()
        }
    }

    fun getImageBytes(filename: String): ByteArray? {
        Log.d(TAG, "getImageBytes: '$filename'")
        val urlIdx = findByFilename(filename) ?: run {
            Log.w(TAG, "getImageBytes: not found: '$filename'")
            return null
        }
        Log.d(TAG, "getImageBytes: found at urlIndex=$urlIdx")
        return try {
            var cur = readDirEntry(urlIdx) ?: return null
            for (i in 0 until 5) {
                if (cur.mimeType != MIME_REDIRECT) break
                cur = readDirEntry(cur.redirectIndex) ?: return null
            }
            if (cur.mimeType == MIME_REDIRECT) return null
            val (data, ext) = readCluster(cur.clusterNumber)
            extractBlob(data, cur.blobNumber, ext)
        } catch (e: Exception) {
            Log.e(TAG, "getImageBytes($filename) failed: ${e.message}")
            null
        }
    }

    // Trim HTML to the article body section, so header/nav images (e.g. K-logo) are excluded.
    private fun extractArticleBody(html: String): String {
        val startMarkers = arrayOf(
            "id=\"mw-content-text\"", "id=\"mw-parser-output\"",
            "id=\"bodyContent\"", "<body"
        )
        for (marker in startMarkers) {
            val idx = html.indexOf(marker, ignoreCase = true)
            if (idx > 0) {
                val tagEnd = html.indexOf('>', idx)
                if (tagEnd > 0) return html.substring(tagEnd + 1)
            }
        }
        return html
    }

    private fun extractImageRefsFromHtml(html: String): List<ImageRef> {
        // Only search the article body — excludes logo/nav images in the page header.
        val body = extractArticleBody(html)
        val result = mutableListOf<ImageRef>()
        val seen = mutableSetOf<String>()
        val imgRegex = Regex("""<img\b[^>]*?\bsrc="([^"]+)"[^>]*>""", RegexOption.IGNORE_CASE)
        for (match in imgRegex.findAll(body)) {
            val src = match.groupValues[1]
            val filename = extractImageFilename(src)
            if (filename == null) continue
            if (filename in seen) continue
            val ext = filename.substringAfterLast('.', "").lowercase()
            if (ext !in setOf("jpg", "jpeg", "png", "webp", "gif")) continue
            val mimeType = when (ext) {
                "jpg", "jpeg" -> "image/jpeg"
                "png"  -> "image/png"
                "webp" -> "image/webp"
                "gif"  -> "image/gif"
                else   -> "image/jpeg"
            }
            val caption = findNearbyCaption(body, match.range.last)
            seen.add(filename)
            result.add(ImageRef(filename, mimeType, caption, match.range.first))
        }
        Log.d(TAG, "imgExtract: returning ${result.size} images")
        return result
    }

    fun getAudioRefs(articleUrlIndex: Int): List<AudioRef> {
        var cur = readDirEntry(articleUrlIndex) ?: return emptyList()
        for (i in 0 until 5) {
            if (cur.mimeType != MIME_REDIRECT) break
            cur = readDirEntry(cur.redirectIndex) ?: return emptyList()
        }
        if (cur.mimeType == MIME_REDIRECT) return emptyList()
        return try {
            val (data, ext) = readCluster(cur.clusterNumber)
            val html = extractBlob(data, cur.blobNumber, ext).toString(Charsets.UTF_8)
            extractAudioRefsFromHtml(html)
        } catch (e: Exception) {
            Log.e(TAG, "getAudioRefs($articleUrlIndex) failed: ${e.message}")
            emptyList()
        }
    }

    fun getAudioBytes(filename: String): ByteArray? {
        Log.d(TAG, "getAudioBytes: '$filename'")
        val urlIdx = findByFilename(filename) ?: run {
            Log.w(TAG, "getAudioBytes: not found: '$filename'")
            return null
        }
        return try {
            var cur = readDirEntry(urlIdx) ?: return null
            for (i in 0 until 5) {
                if (cur.mimeType != MIME_REDIRECT) break
                cur = readDirEntry(cur.redirectIndex) ?: return null
            }
            if (cur.mimeType == MIME_REDIRECT) return null
            val (data, ext) = readCluster(cur.clusterNumber)
            extractBlob(data, cur.blobNumber, ext)
        } catch (e: Exception) {
            Log.e(TAG, "getAudioBytes($filename) failed: ${e.message}")
            null
        }
    }

    private fun extractAudioRefsFromHtml(html: String): List<AudioRef> {
        val body = extractArticleBody(html)
        val result = mutableListOf<AudioRef>()
        val seen = mutableSetOf<String>()

        // Path 1: <audio><source src="..."> tags (rare in Klexikon ZIM, kept for completeness)
        val audioBlockRegex = Regex("""<audio\b[^>]*>([\s\S]*?)</audio>""", RegexOption.IGNORE_CASE)
        val sourceRegex = Regex("""<source\b[^>]*?\bsrc="([^"]+)"[^>]*>""", RegexOption.IGNORE_CASE)
        for (audioMatch in audioBlockRegex.findAll(body)) {
            val srcMatch = sourceRegex.find(audioMatch.value) ?: continue
            val filename = extractAudioFilename(srcMatch.groupValues[1]) ?: continue
            if (filename in seen) continue
            val ext = filename.substringAfterLast('.', "").lowercase()
            if (ext !in setOf("mp3", "ogg", "oga", "opus", "wav")) continue
            val mimeType = when (ext) {
                "mp3" -> "audio/mpeg"; "ogg", "oga" -> "audio/ogg"
                "opus" -> "audio/opus"; "wav" -> "audio/wav"; else -> "audio/mpeg"
            }
            seen.add(filename)
            result.add(AudioRef(filename, mimeType, findNearbyCaption(body, audioMatch.range.last), audioMatch.range.first))
        }

        // Path 2: Wikimedia audio links via wpDestFile= (Klexikon's actual audio format)
        // e.g. href="...?wpDestFile=Ludwig_van_Beethoven_-_symphony_no._5.ogg"
        val wpRegex = Regex(
            """href="[^"]*[?&]wpDestFile=([^"&]+\.(?:ogg|oga|mp3|opus|wav))""",
            RegexOption.IGNORE_CASE
        )
        for (m in wpRegex.findAll(body)) {
            val filename = java.net.URLDecoder.decode(m.groupValues[1], "UTF-8")
            if (filename in seen) continue
            seen.add(filename)
            val ext = filename.substringAfterLast('.', "").lowercase()
            val mimeType = when (ext) {
                "mp3" -> "audio/mpeg"; "ogg", "oga" -> "audio/ogg"
                "opus" -> "audio/opus"; "wav" -> "audio/wav"; else -> "audio/ogg"
            }
            val caption = findCaptionBefore(body, m.range.first)
            result.add(AudioRef(filename, mimeType, caption, m.range.first))
            Log.d(TAG, "audioExtract(wpDestFile): $filename caption=$caption")
        }

        Log.d(TAG, "audioExtract: ${result.size} audio refs (${seen.size} unique)")
        return result
    }

    // Looks back up to 300 chars for the last sentence-ending text before a link.
    private fun findCaptionBefore(html: String, beforePos: Int): String? {
        val window = html.substring(maxOf(0, beforePos - 300), beforePos)
        val text = window.replace(Regex("<[^>]+>"), " ")
            .replace(Regex("&[a-zA-Z#0-9]+;"), " ")
            .replace(Regex("\\s+"), " ").trim()
        if (text.isEmpty()) return null
        for (sep in listOf(":", ".", "!", "?")) {
            val idx = text.lastIndexOf(sep)
            if (idx >= 0) {
                val candidate = text.substring(idx + 1).trim()
                if (candidate.length in 5..200) return candidate
            }
        }
        return text.takeLast(120).trim().ifEmpty { null }
    }

    private fun extractAudioFilename(src: String): String? {
        var path = src
        while (path.startsWith("../")) path = path.removePrefix("../")
        if (path.startsWith("./")) path = path.removePrefix("./")
        if (path.startsWith("/")) path = path.removePrefix("/")
        val ext = path.substringAfterLast('.', "").lowercase()
        return if (ext.isNotEmpty()) path else null
    }

    private fun extractImageFilename(src: String): String? {
        // Do NOT URL-decode: ZIM URL table stores percent-encoded URLs,
        // and the HTML src also uses percent-encoding — they must match as-is.
        // Strip relative path prefixes (./  ../  ../../  leading /) so what remains
        // is the path that can be found under any namespace prefix in getImageBytes().
        var path = src
        while (path.startsWith("../")) path = path.removePrefix("../")
        if (path.startsWith("./")) path = path.removePrefix("./")
        if (path.startsWith("/")) path = path.removePrefix("/")
        val ext = path.substringAfterLast('.', "").lowercase()
        return if (ext.isNotEmpty() && path.contains('/')) path else {
            // No subdirectory — bare filename only
            if (ext.isNotEmpty()) path else null
        }
    }

    // Robust multi-variant filename lookup.
    //
    // Tries each candidate against all namespace prefixes (C/, I/, -/I/, -/, A/).
    // Candidates tried in order:
    //   1. filename as-is                      (covers new ZIM: namespace=C, url=I/name.jpg)
    //   2. basename (strips first path segment) (covers old ZIM: namespace=I, url=name.jpg)
    // Each candidate is also tried URL-decoded once and twice
    // (handles %C3%A9 → é and %2520 → %20 → space double-encoding).
    private fun findByFilename(filename: String?): Int? {
        if (filename.isNullOrEmpty()) return null

        fun tryPrefixes(name: String): Int? =
            findUrlIndexByPath("C/$name")
                ?: findUrlIndexByPath("I/$name")
                ?: findUrlIndexByPath("-/I/$name")
                ?: findUrlIndexByPath("-/$name")
                ?: findUrlIndexByPath("A/$name")

        fun decode(s: String): String? = try {
            java.net.URLDecoder.decode(s.replace("+", "%2B"), "UTF-8").takeIf { it != s }
        } catch (_: Exception) { null }

        val slash = filename.indexOf('/')
        val candidates = buildList {
            add(filename)
            // Strip first path component ("I/name.jpg" → "name.jpg") for old-ZIM compat
            if (slash in 1 until filename.lastIndex) add(filename.substring(slash + 1))
        }

        for (base in candidates) {
            tryPrefixes(base)?.let { return it }
            val d1 = decode(base) ?: continue
            tryPrefixes(d1)?.let { return it }
            val d2 = decode(d1) ?: continue
            tryPrefixes(d2)?.let { return it }
        }
        return null
    }

    private fun findNearbyCaption(html: String, afterPos: Int): String? {
        fun cleanHtml(raw: String): String? = raw
            // Remove magnify helper div — otherwise "Vergrößern" leaks into caption text
            .replace(Regex("""<div\b[^>]*\bmagnify\b[^>]*>[\s\S]*?</div>""", RegexOption.IGNORE_CASE), "")
            .replace(Regex("<[^>]+>"), " ")
            .replace("&amp;", "&").replace("&nbsp;", " ")
            .replace("&lt;", "<").replace("&gt;", ">")
            .replace("&auml;", "ä").replace("&ouml;", "ö").replace("&uuml;", "ü")
            .replace("&Auml;", "Ä").replace("&Ouml;", "Ö").replace("&Uuml;", "Ü")
            .replace("&szlig;", "ß").replace("&ndash;", "–").replace("&mdash;", "—")
            .replace("&quot;", "\"").replace("&apos;", "'")
            .replace(Regex("\\s+"), " ").trim()
            .ifEmpty { null }

        fun captionFromWindow(w: String): String? {
            // HTML5 / modern Kiwix: <figcaption>…</figcaption>
            val figIdx = w.indexOf("<figcaption", ignoreCase = true)
            if (figIdx >= 0) {
                val gt    = w.indexOf('>', figIdx)
                val close = w.indexOf("</figcaption>", figIdx, ignoreCase = true)
                if (gt >= 0 && close > gt)
                    cleanHtml(w.substring(gt + 1, close))?.let { return it }
            }

            // Classic MediaWiki / Klexikon: <div class="thumbcaption">…</div>
            // Uses nestedDivContent() so the inner magnify div doesn't terminate the match early.
            val thumbIdx = w.indexOf("thumbcaption", ignoreCase = true)
            if (thumbIdx >= 0) {
                val gt = w.indexOf('>', thumbIdx)
                if (gt >= 0)
                    nestedDivContent(w, gt + 1)?.let { cleanHtml(it) }?.let { return it }
            }

            // MediaWiki image galleries: <div class="gallerytext">…</div>
            val galIdx = w.indexOf("gallerytext", ignoreCase = true)
            if (galIdx >= 0) {
                val gt = w.indexOf('>', galIdx)
                if (gt >= 0)
                    nestedDivContent(w, gt + 1)?.let { cleanHtml(it) }?.let { return it }
            }

            return null
        }

        val end = minOf(afterPos + 3000, html.length)

        // Primary: forward search from end of <img> tag
        captionFromWindow(html.substring(afterPos, end))?.let { return it }

        // Fallback: find the enclosing container block and search from its opening tag.
        // Handles cases where the caption marker is more than 3000 chars from the img end
        // (e.g. large srcset) or where the img is nested deeper than expected.
        val blockStart = findEnclosingBlock(html, afterPos) ?: return null
        if (blockStart >= afterPos) return null
        return captionFromWindow(html.substring(blockStart, end))
    }

    // Returns the inner HTML of a div whose opening tag has already been consumed,
    // tracking nested <div> depth so the result isn't cut off by an inner </div>.
    private fun nestedDivContent(html: String, start: Int): String? {
        var depth = 1
        var pos   = start
        while (pos < html.length) {
            val o = html.indexOf("<div",  pos, ignoreCase = true)
            val c = html.indexOf("</div>", pos, ignoreCase = true)
            when {
                c < 0               -> return null
                o >= 0 && o < c     -> { depth++; pos = o + 4 }
                else                -> { if (--depth == 0) return html.substring(start, c); pos = c + 6 }
            }
        }
        return null
    }

    // Searches backwards from beforePos to find the opening of the nearest enclosing
    // image container block (thumbinner, gallerybox, or <figure>).
    // Returns the absolute position of the opening '<' in html, or null if not found.
    private fun findEnclosingBlock(html: String, beforePos: Int): Int? {
        val searchFrom = maxOf(0, beforePos - 3000)
        val prefix = html.substring(searchFrom, beforePos)
        var best = -1

        for (cls in listOf("thumbinner", "gallerybox")) {
            val idx = prefix.lastIndexOf(cls)
            if (idx < 0) continue
            // Walk back to the opening '<' of the tag containing this class
            var t = idx
            while (t > 0 && prefix[t] != '<') t--
            if (t >= 0 && prefix.regionMatches(t, "<div", 0, 4, ignoreCase = true) && t > best)
                best = t
        }
        val figIdx = prefix.lastIndexOf("<figure", ignoreCase = true)
        if (figIdx >= 0 && figIdx > best) best = figIdx

        return if (best >= 0) searchFrom + best else null
    }

    private fun findUrlIndexByPath(targetPath: String): Int? {
        var lo = 0; var hi = articleCount - 1
        while (lo <= hi) {
            val mid = (lo + hi) ushr 1
            val e = readDirEntry(mid) ?: break
            val path = "${e.namespace}/${e.url}"
            when {
                path < targetPath -> lo = mid + 1
                path > targetPath -> hi = mid - 1
                else              -> return mid
            }
        }
        return null
    }

    // ── Header / index loading ─────────────────────────────────────────────────

    private fun readHeader() {
        val buf = ByteArray(80)
        raf!!.seek(0)
        raf!!.readFully(buf)
        val bb = ByteBuffer.wrap(buf).order(ByteOrder.LITTLE_ENDIAN)

        val magic = bb.int.toLong() and 0xFFFFFFFFL
        if (magic != ZIM_MAGIC)
            throw IllegalStateException("Bad ZIM magic: 0x${magic.toString(16)}")

        majorVersion = bb.short.toInt() and 0xFFFF
        bb.position(24)
        articleCount = bb.int
        clusterCount = bb.int
        urlPtrPos    = bb.long
        titlePtrPos  = bb.long
        clusterPtrPos = bb.long
        mimeListPos  = bb.long
        Log.d(TAG, "v$majorVersion, articles=$articleCount, clusters=$clusterCount")
    }

    private fun readMimeTypes() {
        raf!!.seek(mimeListPos)
        val types = mutableListOf<String>()
        for (i in 0 until 256) {
            val s = readNullTermString() ?: break
            if (s.isEmpty()) break
            types.add(s)
        }
        htmlMimeIndices = types.indices.filter { types[it].startsWith("text/html") }.toSet()
        Log.d(TAG, "MIME types: $types — HTML indices: $htmlMimeIndices")
    }

    private fun readPtrTables() {
        urlPtrs = LongArray(articleCount)
        raf!!.seek(urlPtrPos)
        val urlBuf = ByteArray(articleCount * 8)
        raf!!.readFully(urlBuf)
        ByteBuffer.wrap(urlBuf).order(ByteOrder.LITTLE_ENDIAN).asLongBuffer().get(urlPtrs)

        // ZIM v6 sets titlePtrPos = 0xFFFFFFFF_FFFFFFFF (-1 signed) → no title index
        hasTitleIndex = titlePtrPos > 0
        if (hasTitleIndex) {
            titlePtrs = IntArray(articleCount)
            raf!!.seek(titlePtrPos)
            val titleBuf = ByteArray(articleCount * 4)
            raf!!.readFully(titleBuf)
            ByteBuffer.wrap(titleBuf).order(ByteOrder.LITTLE_ENDIAN).asIntBuffer().get(titlePtrs)
        }

        clusterPtrs = LongArray(clusterCount)
        raf!!.seek(clusterPtrPos)
        val clBuf = ByteArray(clusterCount * 8)
        raf!!.readFully(clBuf)
        ByteBuffer.wrap(clBuf).order(ByteOrder.LITTLE_ENDIAN).asLongBuffer().get(clusterPtrs)
    }

    private fun loadAllTitles(onProgress: ((Double) -> Unit)? = null) {
        for (i in 0 until articleCount) {
            // v5: iterate title-sorted table; v6: iterate URL table directly
            val urlIdx = if (hasTitleIndex) titlePtrs[i] else i
            val entry = readDirEntry(urlIdx) ?: continue
            if (entry.mimeType == MIME_REDIRECT) continue
            if (hasTitleIndex) {
                // v5: namespace filter
                if (entry.namespace != 'A' && entry.namespace != 'C') continue
            } else {
                // v6: filter by MIME type — only text/html entries are actual articles
                if (htmlMimeIndices.isNotEmpty() && entry.mimeType !in htmlMimeIndices) continue
            }
            val title = entry.title.ifEmpty { entry.url }
            allTitles.add(Pair(urlIdx, title))

            if (articleCount > 0 && i % 50 == 0) {
                onProgress?.invoke(i.toDouble() / articleCount)
            }
        }
        onProgress?.invoke(1.0)
    }

    // ── Directory entry ────────────────────────────────────────────────────────

    private data class DirEntry(
        val mimeType: Int,
        val namespace: Char,
        val url: String,
        val title: String,
        val clusterNumber: Int,
        val blobNumber: Int,
        val redirectIndex: Int,
    )

    private fun readDirEntry(urlIndex: Int): DirEntry? {
        if (urlIndex < 0 || urlIndex >= articleCount) return null
        raf!!.seek(urlPtrs[urlIndex])

        val mimeType   = readUInt16()
        val paramLen   = raf!!.read()
        val namespace  = raf!!.read().toChar()
        raf!!.skipBytes(4) // revision

        val clusterNumber: Int
        val blobNumber:    Int
        val redirectIndex: Int

        if (mimeType == MIME_REDIRECT) {
            redirectIndex  = readUInt32()
            clusterNumber  = 0
            blobNumber     = 0
        } else {
            clusterNumber  = readUInt32()
            blobNumber     = readUInt32()
            redirectIndex  = 0
        }

        val url   = readNullTermString() ?: ""
        val title = readNullTermString() ?: ""
        if (paramLen > 0) raf!!.skipBytes(paramLen)

        return DirEntry(mimeType, namespace, url, title, clusterNumber, blobNumber, redirectIndex)
    }

    // ── Cluster / blob ─────────────────────────────────────────────────────────

    private fun readCluster(clusterNumber: Int): Pair<ByteArray, Boolean> {
        val offset     = clusterPtrs[clusterNumber]
        val nextOffset = if (clusterNumber + 1 < clusterCount) clusterPtrs[clusterNumber + 1]
                         else raf!!.length()

        raf!!.seek(offset)
        val info           = raf!!.read()
        val comprType      = info and 0x0F
        val extendedBlobs  = (info and 0x10) != 0

        val compSize = (nextOffset - offset - 1).toInt().coerceAtLeast(0)
        val compData = ByteArray(compSize)
        raf!!.readFully(compData)

        val decompressed = when (comprType) {
            0, 1 -> compData
            2    -> InflaterInputStream(ByteArrayInputStream(compData)).readBytes()
            4    -> XZInputStream(ByteArrayInputStream(compData)).readBytes()
            5    -> ZimZstd.decompress(compData) ?: throw IllegalStateException("ZSTD decompression failed")
            else -> throw IllegalStateException("Unsupported cluster compression: $comprType")
        }
        return Pair(decompressed, extendedBlobs)
    }

    private fun extractBlob(data: ByteArray, blobNumber: Int, extendedOffsets: Boolean): ByteArray {
        val bb = ByteBuffer.wrap(data).order(ByteOrder.LITTLE_ENDIAN)
        return if (extendedOffsets) {
            val start = bb.getLong(blobNumber * 8)
            val end   = bb.getLong((blobNumber + 1) * 8)
            data.copyOfRange(start.toInt(), end.toInt())
        } else {
            val start = Integer.toUnsignedLong(bb.getInt(blobNumber * 4))
            val end   = Integer.toUnsignedLong(bb.getInt((blobNumber + 1) * 4))
            data.copyOfRange(start.toInt(), end.toInt())
        }
    }

    // ── HTML → plain text ──────────────────────────────────────────────────────

    // Remove header/footer and image captions before text extraction
    private fun preClean(html: String): String {
        var s = html

        // 1. Start from main article body — skip <head>, page title <h1>, nav chrome
        val startMarkers = arrayOf("id=\"mw-content-text\"", "id=\"mw-parser-output\"", "id=\"bodyContent\"", "<body")
        for (marker in startMarkers) {
            val idx = s.indexOf(marker, ignoreCase = true)
            if (idx > 0) {
                val tagEnd = s.indexOf('>', idx)
                if (tagEnd > 0) { s = s.substring(tagEnd + 1); break }
            }
        }

        // 2. Cut at MediaWiki footer/category markers
        for (marker in arrayOf(
            "id=\"mw-footer\"", "id=\"footer\"", "class=\"printfooter\"",
            "id=\"catlinks\"", "id=\"mw-data-after-content\"", "id=\"mw-navigation\"",
            "class=\"noprint\"", "id=\"oer-award\"", "id=\"oer-logo\"", "id=\"cc-logo\""
        )) {
            val idx = s.indexOf(marker, ignoreCase = true)
            if (idx > 0) {
                var pos = idx
                while (pos > 0 && s[pos] != '<') pos--
                if (pos > 0) { s = s.substring(0, pos); break }
            }
        }

        // 3. Cut at the Klexikon "Weblinks" section (article body, not MediaWiki footer)
        //    Klexikon articles end with a standard Weblinks section linking to MiniKlexikon + FragFinn.
        for (marker in arrayOf(
            "id=\"Weblinks\"",
            "id=\"Weiterführende_Informationen\"",
            "id=\"Weitere_Informationen\"",
            "id=\"Mehr_Informationen\""
        )) {
            val idx = s.indexOf(marker, ignoreCase = true)
            if (idx > 0) {
                // Walk back to the heading tag that contains this anchor
                var pos = idx
                while (pos > 0 && s[pos] != '<') pos--
                // Step back one more tag boundary to include the heading wrapper
                if (pos > 1) {
                    pos--
                    while (pos > 0 && s[pos] != '<') pos--
                }
                if (pos > 0) { s = s.substring(0, pos); break }
            }
        }

        // 4. Cut at Klexikon credit/license/outro text.
        //    Find the EARLIEST position across all markers — multiple promo blocks may appear
        //    in different orders; a break-on-first-match would cut too late.
        run {
            val markers = arrayOf(
                // Paragraph starting with "Klexikon ist für Kinder…" (oldest variant)
                "Klexikon ist für Kinder",
                "Online-Lexikon für Schulkinder",
                "findet ihr einen besonders einfachen Artikel",
                "weitere Kinderseiten",
                "Kindersuchmaschine",
                "MiniKlexikon.de",
                "miniklexikon.zum.de",
                "FragFinn", "Frag Finn",            // children's search engine in outro
                // Older donation-link paragraph
                "Klexikon ist ein",
                "betterplace.org",
                "zu 3.500 Themen",
                "für Unterricht, Hausaufgaben",
                // "Das Kinderlexikon Klexikon sorgt…" paragraph
                "Das Kinderlexikon Klexikon sorgt",
                "Medienkompetenz und Bildungsgerechtigkeit",
                // Ambassador paragraph
                "Klexikon-Botschafter",
                "KiKA-Moderatoren",
                "Ralph Caspers",
                "Checker Julian",
                "Julian Janssen",
                "Wissen macht Ah",
                // Funding-body paragraph
                "bzkj.de",
                "mabb.de",
                "Bundeszentrale für Kinder",
                // Generic fallbacks
                "Diese Seite wurde zuletzt",
                "Dieser Artikel ist Teil des Klexikons",
                "Klexikon gehört",
                "Das Klexikon ist",
                "steht unter der Lizenz",
                "Creative Commons"
            )
            var cutPos = -1
            for (marker in markers) {
                val idx = s.indexOf(marker, ignoreCase = true)
                if (idx > 0 && (cutPos < 0 || idx < cutPos)) {
                    var pos = idx
                    while (pos > 0 && s[pos] != '<') pos--
                    if (pos > 0) cutPos = pos
                }
            }
            if (cutPos > 0) s = s.substring(0, cutPos)
        }

        // 4. Remove image blocks — inside-out so captions are gone even if outer class differs
        s = removeNestedDivsByClass(s, "thumbcaption") // innermost caption
        s = removeNestedDivsByClass(s, "thumbinner")   // mid-level wrapper
        s = removeNestedDivsByClass(s, "thumb")        // outer thumb wrapper
        s = removeNestedDivsByClass(s, "gallerytext")  // image gallery captions
        s = removeNestedDivsByClass(s, "gallery")      // gallery <div>

        // 4b. Remove <ul class="gallery"> blocks (Klexikon media galleries are <ul>, not <div>)
        s = s.replace(Regex("<ul\\b[^>]*\\bgallery\\b[^>]*>[\\s\\S]*?</ul>", RegexOption.IGNORE_CASE), "")

        // 4c. Cut at visual-reference paragraphs that precede galleries/videos
        for (marker in arrayOf(
            "Unten sieht man Film",
            "Unten seht ihr",
            "Im folgenden Film",
            "Im folgenden Video",
            "Hier sieht man Film",
            "Hier seht ihr"
        )) {
            val idx = s.indexOf(marker, ignoreCase = true)
            if (idx > 0) {
                var pos = idx
                while (pos > 0 && s[pos] != '<') pos--
                s = s.substring(0, pos)
                break
            }
        }

        // 5. Remove table of contents
        s = removeNestedDivsByClass(s, "toc")

        // 6. Remove <figure> blocks (image + figcaption)
        s = s.replace(Regex("<figure\\b[^>]*>[\\s\\S]*?</figure>", RegexOption.IGNORE_CASE), "")

        // 7. Remove edit-section links
        s = s.replace(Regex("<span[^>]*class=\"[^\"]*mw-editsection[^\"]*\"[^>]*>[\\s\\S]*?</span>", RegexOption.IGNORE_CASE), "")

        // 8. Remove remaining bare <img> and <video> tags
        s = s.replace(Regex("<img\\b[^>]*>", RegexOption.IGNORE_CASE), "")
        s = s.replace(Regex("<video\\b[^>]*>|</video>", RegexOption.IGNORE_CASE), "")

        return s
    }

    // Walk the html string and remove every <div> whose class contains cssClass,
    // including all nested content. Uses a depth counter so nested divs are handled correctly.
    private fun removeNestedDivsByClass(html: String, cssClass: String): String {
        val result = StringBuilder()
        var i = 0
        val pattern = Regex("""<div\b[^>]*\bclass="[^"]*\b${Regex.escape(cssClass)}\b""", RegexOption.IGNORE_CASE)
        while (i < html.length) {
            val match = pattern.find(html, i) ?: run {
                result.append(html.substring(i))
                return result.toString()
            }
            result.append(html.substring(i, match.range.first))
            // Advance to end of the opening tag
            var pos = match.range.last + 1
            while (pos < html.length && html[pos] != '>') pos++
            if (pos < html.length) pos++ // skip '>'
            // Walk to the matching </div>
            var depth = 1
            while (pos < html.length && depth > 0) {
                val nextOpen  = html.indexOf("<div", pos, ignoreCase = true)
                val nextClose = html.indexOf("</div>", pos, ignoreCase = true)
                when {
                    nextClose < 0                        -> { pos = html.length; depth = 0 }
                    nextOpen < 0 || nextClose < nextOpen -> { pos = nextClose + 6; depth-- }
                    else                                 -> { pos = nextOpen + 4; depth++ }
                }
            }
            i = pos
        }
        return result.toString()
    }

    private fun htmlToText(html: String): String {
        var s = preClean(html)
        // Drop script / style blocks
        s = s.replace(Regex("<script[\\s\\S]*?</script>", RegexOption.IGNORE_CASE), "")
        s = s.replace(Regex("<style[\\s\\S]*?</style>", RegexOption.IGNORE_CASE), "")
        // Drop nav, header, footer, table, figure blocks
        s = s.replace(Regex("<(nav|header|footer|table|figure|figcaption)[\\s\\S]*?</(nav|header|footer|table|figure|figcaption)>", RegexOption.IGNORE_CASE), "")
        // Block → newline
        s = s.replace(Regex("</(p|div|h[1-6]|li|tr)>", RegexOption.IGNORE_CASE), "\n")
        s = s.replace(Regex("<br\\s*/?>", RegexOption.IGNORE_CASE), "\n")
        // Strip remaining tags
        s = s.replace(Regex("<[^>]+>"), "")
        // Decode common entities
        s = s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
            .replace("&quot;", "\"").replace("&apos;", "'")
            .replace("&nbsp;", " ").replace("&#160;", " ")
            .replace("&ndash;", "–").replace("&mdash;", "—")
        // Normalise whitespace
        s = s.replace(Regex("[ \t]+"), " ")
        s = s.replace(Regex("\n[ \t]+"), "\n")
        s = s.replace(Regex("\n{3,}"), "\n\n")
        return s.trim()
    }

    private fun extractFirstParagraph(html: String): String {
        val cleaned = preClean(html)
        val m = Regex("<p[^>]*>([\\s\\S]*?)</p>", RegexOption.IGNORE_CASE).find(cleaned)
            ?: return ""
        return htmlToText(m.groupValues[1]).take(600)
    }

    private fun normalizeUmlauts(s: String): String =
        s.replace("ä", "a").replace("ö", "o").replace("ü", "u")
         .replace("Ä", "A").replace("Ö", "O").replace("Ü", "U")
         .replace("ß", "ss")

    // ── Low-level I/O ──────────────────────────────────────────────────────────

    private fun readNullTermString(): String? {
        val out = ByteArrayOutputStream()
        while (true) {
            val b = raf!!.read()
            if (b == -1) return null
            if (b == 0)  return out.toByteArray().toString(Charsets.UTF_8)
            out.write(b)
        }
    }

    private fun readUInt16(): Int {
        val b0 = raf!!.read(); val b1 = raf!!.read()
        return (b0 and 0xFF) or ((b1 and 0xFF) shl 8)
    }

    private fun readUInt32(): Int {
        val buf = ByteArray(4); raf!!.readFully(buf)
        return ByteBuffer.wrap(buf).order(ByteOrder.LITTLE_ENDIAN).int
    }
}

// Minimal stand-in if zlib is needed without the full Inflater setup
private fun InflaterInputStream(input: ByteArrayInputStream) =
    java.util.zip.InflaterInputStream(input)
