package com.cctr.export.core

import android.content.ContentValues
import android.content.Context
import android.graphics.RectF
import android.graphics.pdf.PdfDocument
import android.os.Build
import android.os.Environment
import android.os.Handler
import android.os.Looper
import android.provider.MediaStore
import android.util.Base64
import android.view.View
import android.webkit.JavascriptInterface
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import com.tom_roush.pdfbox.android.PDFBoxResourceLoader
import com.tom_roush.pdfbox.io.MemoryUsageSetting
import com.tom_roush.pdfbox.multipdf.PDFMergerUtility
import kotlinx.coroutines.CancellableContinuation
import kotlinx.coroutines.Deferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withContext
import okhttp3.ConnectionPool
import okhttp3.Dispatcher
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayInputStream
import java.io.File
import java.io.FileOutputStream
import java.io.IOException
import java.nio.charset.StandardCharsets
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import java.util.zip.Deflater
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException
import kotlin.math.ceil
import kotlin.math.roundToInt

class PdfAndZipExporter(private val context: Context) {

    companion object {
        // A4 (72 DPI): 595 x 842 pt；四周 18mm 留白 = 51pt，可打印宽度 493pt（对应 658 CSS px @96dpi）
        private const val CSS_VIEW_WIDTH_PX = 658
        private const val PDF_PAGE_W = 595
        private const val PDF_PAGE_H = 842
        private const val MARGIN_PT = 51f
        private const val CONTENT_W_PT = PDF_PAGE_W - MARGIN_PT * 2f
        private const val CONTENT_H_PT = PDF_PAGE_H - MARGIN_PT * 2f
        private const val MAX_CSS_SLICE_PX = 950
        private const val PAGES_PER_FRAME_BATCH = 2
        private const val RENDER_TIMEOUT_MS = 60_000L

        private const val COMPUTE_BREAKS_JS = """
            (function() {
              const dpr = window.devicePixelRatio || 1;
              const totalH = Math.ceil(document.documentElement.scrollHeight || document.body.scrollHeight);
              const maxPageH = $MAX_CSS_SLICE_PX;
              const smartPag = document.body.getAttribute('data-smart-pagination') !== '0';
              const atomicRanges = [];
              const forcedBreaks = new Set();

              if (smartPag) {
                const articles = Array.from(document.querySelectorAll('article'));
                for (const art of articles) {
                  const r = art.getBoundingClientRect();
                  const top = Math.max(0, Math.floor(r.top + window.scrollY));
                  const bot = Math.min(totalH, Math.ceil(r.bottom + window.scrollY));
                  if (bot - top <= maxPageH) {
                    atomicRanges.push([top, bot]);
                  } else {
                    forcedBreaks.add(bot);
                  }
                }

                // h2 与其紧随的常规小题绑定，不单独留在页尾
                for (const h2 of document.querySelectorAll('h2')) {
                  const next = h2.nextElementSibling;
                  if (next && next.tagName === 'ARTICLE') {
                    const hr = h2.getBoundingClientRect();
                    const nr = next.getBoundingClientRect();
                    const spanTop = Math.max(0, Math.floor(hr.top + window.scrollY));
                    const spanBot = Math.min(totalH, Math.ceil(nr.bottom + window.scrollY));
                    if (spanBot - spanTop <= maxPageH) {
                      atomicRanges.push([spanTop, spanBot]);
                    }
                  }
                }
              }

              const candidates = new Set([0, totalH]);
              const nodes = document.querySelectorAll('h1, h2, h3, p, div.option, div.label, article, img, tr');
              for (const n of nodes) {
                const r = n.getBoundingClientRect();
                if (r.height > 0) {
                  candidates.add(Math.max(0, Math.floor(r.top + window.scrollY)));
                  candidates.add(Math.min(totalH, Math.ceil(r.bottom + window.scrollY)));
                }
              }
              for (const fb of forcedBreaks) candidates.add(fb);

              const isInsideAtomic = (y) => {
                for (const [at, ab] of atomicRanges) {
                  if (y > at + 1 && y < ab - 1) return true;
                }
                return false;
              };

              const sorted = Array.from(candidates)
                .filter(y => !isInsideAtomic(y))
                .sort((a, b) => a - b);

              const breaks = [0];
              let cur = 0;
              while (cur < totalH) {
                let forcedNext = -1;
                for (const fb of forcedBreaks) {
                  if (fb > cur + 10 && fb <= cur + maxPageH) {
                    if (forcedNext === -1 || fb < forcedNext) forcedNext = fb;
                  }
                }
                if (forcedNext !== -1) {
                  breaks.push(forcedNext);
                  cur = forcedNext;
                  continue;
                }

                const limit = cur + maxPageH;
                if (limit >= totalH) {
                  breaks.push(totalH);
                  break;
                }
                let best = -1;
                for (let i = sorted.length - 1; i >= 0; i--) {
                  if (sorted[i] > cur + 20 && sorted[i] <= limit) {
                    best = sorted[i];
                    break;
                  }
                }
                if (best <= cur) best = limit;
                breaks.push(best);
                cur = best;
              }
              return JSON.stringify({ totalH: totalH, breaks: breaks, dpr: dpr });
            })()
        """
    }

    private val mainHandler = Handler(Looper.getMainLooper())

    private val imageHttp = OkHttpClient.Builder()
        .dispatcher(Dispatcher().apply {
            maxRequests = 32
            maxRequestsPerHost = 12
        })
        .connectionPool(ConnectionPool(12, 5, TimeUnit.MINUTES))
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .followRedirects(true)
        .build()

    private data class ChunkRenderMeta(
        val slice: List<QuestionItem>,
        val startIndex: Int,
        val includeHeader: Boolean,
        val initialGroup: Triple<String, String, String>?
    )

    private inner class WebViewRenderSession(
        private val webView: WebView,
        private val density: Float
    ) : AutoCloseable {
        private var currentToken = 0
        private var evalStartedForToken = -1
        private var activeCont: CancellableContinuation<PdfDocument>? = null
        private var activeTimeout: Runnable? = null
        private var closed = false

        init {
            val bridge = object {
                @JavascriptInterface
                fun onRenderReady(token: Int, payload: String) {
                    mainHandler.post { handleRenderReady(token, payload) }
                }
            }
            webView.addJavascriptInterface(bridge, "__cctrBridge")
            webView.webViewClient = object : WebViewClient() {
                override fun shouldInterceptRequest(view: WebView?, request: WebResourceRequest?): WebResourceResponse? {
                    val uri = request?.url ?: return null
                    val scheme = uri.scheme?.lowercase().orEmpty()
                    val host = uri.host?.lowercase().orEmpty()
                    if (scheme == "data" || scheme == "about") return null
                    if (scheme == "https" && (
                            host == "cctrcloud.net" || host.endsWith(".cctrcloud.net") ||
                            host == "aliyuncs.com" || host.endsWith(".aliyuncs.com") ||
                            host == "chaoxing.com" || host.endsWith(".chaoxing.com") ||
                            host == "xuexitong.com" || host.endsWith(".xuexitong.com") ||
                            host == "ddfv2.com" || host.endsWith(".ddfv2.com") ||
                            host == "yuketang.cn" || host.endsWith(".yuketang.cn") ||
                            host == "xuetangx.com" || host.endsWith(".xuetangx.com") ||
                            host == "myqcloud.com" || host.endsWith(".myqcloud.com") ||
                            host == "qcloud.com" || host.endsWith(".qcloud.com") ||
                            host == "icourse163.org" || host.endsWith(".icourse163.org") ||
                            host == "126.net" || host.endsWith(".126.net") ||
                            host == "zhihuishu.com" || host.endsWith(".zhihuishu.com") ||
                            host == "icve.com.cn" || host.endsWith(".icve.com.cn")
                        )
                    ) return null
                    return WebResourceResponse("text/plain", "utf-8", ByteArrayInputStream(ByteArray(0)))
                }

                override fun onPageFinished(view: WebView?, url: String?) {
                    val token = currentToken
                    if (closed || activeCont == null || url == "about:blank") return
                    if (evalStartedForToken == token) return
                    evalStartedForToken = token
                    val script = """
                        (async function(t) {
                          try {
                            const verifyRaw = await (${Integrity.VERIFY_AND_SLICE_JS.trim()});
                            const verifyObj = JSON.parse(verifyRaw);
                            if (!verifyObj || !verifyObj.ok) {
                              window.__cctrBridge.onRenderReady(t, verifyRaw);
                              return;
                            }
                            const brkRaw = (${COMPUTE_BREAKS_JS.trim()});
                            const brkObj = JSON.parse(brkRaw);
                            window.__cctrBridge.onRenderReady(t, JSON.stringify({
                              ok: true,
                              totalH: brkObj.totalH,
                              breaks: brkObj.breaks,
                              dpr: brkObj.dpr
                            }));
                          } catch (e) {
                            window.__cctrBridge.onRenderReady(t, JSON.stringify({ ok: false, error: String(e) }));
                          }
                        })($token);
                    """.trimIndent()
                    webView.evaluateJavascript(script, null)
                }
            }
        }

        private fun cancelTimeout() {
            activeTimeout?.let { mainHandler.removeCallbacks(it) }
            activeTimeout = null
        }

        private fun failActive(token: Int, message: String) {
            if (token != currentToken) return
            cancelTimeout()
            val cont = activeCont
            activeCont = null
            if (cont != null && cont.isActive) {
                cont.resumeWithException(IllegalStateException(message))
            }
        }

        private fun handleRenderReady(token: Int, payload: String) {
            if (closed || token != currentToken) return
            val cont = activeCont ?: return
            if (!cont.isActive) {
                cancelTimeout()
                activeCont = null
                return
            }

            val obj = runCatching { JSONObject(payload) }.getOrNull()
            if (obj == null || !obj.optBoolean("ok", false)) {
                val msg = obj?.optString("error").orEmpty().ifBlank { "PDF 内容完整性校验失败" }
                failActive(token, msg)
                return
            }

            val cssTotalH = obj.optDouble("totalH", 800.0).coerceAtLeast(100.0)
            val dpr = obj.optDouble("dpr", density.toDouble()).toFloat().coerceAtLeast(1f)
            val physW = (CSS_VIEW_WIDTH_PX * dpr).roundToInt()
            val physTotalH = ceil(cssTotalH * dpr).toInt().coerceAtLeast(100)
            val arr = obj.optJSONArray("breaks") ?: JSONArray(listOf(0, cssTotalH.toInt()))
            val cssBreaks = List(arr.length()) { idx -> arr.optDouble(idx) }

            webView.measure(
                View.MeasureSpec.makeMeasureSpec(physW, View.MeasureSpec.EXACTLY),
                View.MeasureSpec.makeMeasureSpec(physTotalH, View.MeasureSpec.EXACTLY)
            )
            webView.layout(0, 0, physW, physTotalH)
            val pdfScale = CONTENT_W_PT / physW.toFloat()

            val doc = PdfDocument()
            var pageNumber = 0

            fun drawBatch(startIdx: Int) {
                if (closed || token != currentToken || !cont.isActive) {
                    runCatching { doc.close() }
                    return
                }
                try {
                    val endIdx = minOf(startIdx + PAGES_PER_FRAME_BATCH, cssBreaks.size - 1)
                    for (i in startIdx until endIdx) {
                        val physTop = (cssBreaks[i] * dpr).toFloat()
                        val physBottom = ceil(cssBreaks[i + 1] * dpr).toFloat()
                        val slicePhysH = (physBottom - physTop).coerceAtMost(CONTENT_H_PT / pdfScale)
                        if (slicePhysH <= 1f) continue
                        pageNumber++
                        val pageInfo = PdfDocument.PageInfo.Builder(PDF_PAGE_W, PDF_PAGE_H, pageNumber).create()
                        val page = doc.startPage(pageInfo)
                        val c = page.canvas
                        c.save()
                        c.translate(MARGIN_PT, MARGIN_PT)
                        c.scale(pdfScale, pdfScale)
                        c.clipRect(RectF(0f, 0f, physW.toFloat(), slicePhysH))
                        c.translate(0f, -physTop)
                        webView.draw(c)
                        c.restore()
                        doc.finishPage(page)
                    }
                    if (endIdx < cssBreaks.size - 1) {
                        // 分帧让出主线程给 Choreographer，避免长文档绘图阻塞 UI 动画
                        mainHandler.post { drawBatch(endIdx) }
                    } else {
                        cancelTimeout()
                        activeCont = null
                        if (cont.isActive) {
                            cont.resume(doc)
                        } else {
                            runCatching { doc.close() }
                        }
                    }
                } catch (e: Exception) {
                    runCatching { doc.close() }
                    failActive(token, "PDF 生成失败: ${e.message}")
                }
            }

            drawBatch(0)
        }

        suspend fun renderHtmlToPdfDocument(html: String): PdfDocument = suspendCancellableCoroutine { cont ->
            mainHandler.post {
                if (closed) {
                    if (cont.isActive) cont.resumeWithException(IllegalStateException("渲染会话已关闭"))
                    return@post
                }
                cancelTimeout()
                val token = ++currentToken
                evalStartedForToken = -1
                activeCont = cont

                val timeout = Runnable { failActive(token, "图片解码或排版校验超时") }
                activeTimeout = timeout
                mainHandler.postDelayed(timeout, RENDER_TIMEOUT_MS)

                cont.invokeOnCancellation {
                    mainHandler.post {
                        if (token == currentToken) {
                            cancelTimeout()
                            activeCont = null
                            runCatching { webView.stopLoading() }
                        }
                    }
                }

                // 关键：加载下一分段前必须将 WebView 高度重置回初始 viewport，防止上一块 scrollHeight 污染
                val initPhysW = (CSS_VIEW_WIDTH_PX * density).roundToInt()
                val initPhysH = (1000f * density).roundToInt()
                webView.measure(
                    View.MeasureSpec.makeMeasureSpec(initPhysW, View.MeasureSpec.EXACTLY),
                    View.MeasureSpec.makeMeasureSpec(initPhysH, View.MeasureSpec.EXACTLY)
                )
                webView.layout(0, 0, initPhysW, initPhysH)
                webView.scrollTo(0, 0)
                webView.loadDataWithBaseURL("https://cctrcloud.net/", html, "text/html", "utf-8", null)
            }
        }

        override fun close() {
            mainHandler.post {
                if (closed) return@post
                closed = true
                cancelTimeout()
                activeCont = null
                runCatching {
                    webView.stopLoading()
                    webView.removeJavascriptInterface("__cctrBridge")
                    webView.loadUrl("about:blank")
                    webView.clearHistory()
                    webView.removeAllViews()
                    webView.destroy()
                }
            }
        }
    }

    private suspend fun createWebViewSession(): WebViewRenderSession =
        suspendCancellableCoroutine { cont ->
            mainHandler.post {
                try {
                    val wv = WebView(context.applicationContext)
                    wv.settings.apply {
                        javaScriptEnabled = true
                        domStorageEnabled = false
                        allowFileAccess = false
                        loadsImagesAutomatically = true
                        blockNetworkImage = false
                        mixedContentMode = WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE
                        cacheMode = WebSettings.LOAD_DEFAULT
                    }
                    val density = context.resources.displayMetrics.density.coerceAtLeast(1f)
                    val initPhysW = (CSS_VIEW_WIDTH_PX * density).roundToInt()
                    val initPhysH = (1000f * density).roundToInt()
                    wv.setBackgroundColor(android.graphics.Color.WHITE)
                    wv.layout(0, 0, initPhysW, initPhysH)
                    val session = WebViewRenderSession(wv, density)
                    if (cont.isActive) {
                        cont.resume(session)
                    } else {
                        session.close()
                    }
                } catch (e: Exception) {
                    if (cont.isActive) cont.resumeWithException(e)
                }
            }
        }

    private fun sniffAnyImageMime(bytes: ByteArray): String? {
        Integrity.sniffImageMime(bytes)?.let { return it }
        if (bytes.size < 16) return null
        val head = String(bytes, 0, minOf(bytes.size, 512), StandardCharsets.UTF_8).trimStart().lowercase()
        if (head.startsWith("<svg") || (head.startsWith("<?xml") && head.contains("<svg"))) {
            return "image/svg+xml"
        }
        return null
    }

    private suspend fun downloadImageAsDataUri(url: String): String? {
        val backoffsMs = longArrayOf(150L, 350L)
        for (attempt in 0..2) {
            try {
                val req = Request.Builder()
                    .url(url)
                    .header("User-Agent", "Mozilla/5.0")
                    .get()
                    .build()
                imageHttp.newCall(req).execute().use { resp ->
                    if (!resp.isSuccessful) throw IOException("HTTP ${resp.code}")
                    val bytes = resp.body?.bytes() ?: ByteArray(0)
                    val mime = sniffAnyImageMime(bytes) ?: return null
                    val b64 = Base64.encodeToString(bytes, Base64.NO_WRAP)
                    return "data:$mime;base64,$b64"
                }
            } catch (_: Exception) {
                if (attempt < backoffsMs.size) {
                    delay(backoffsMs[attempt])
                }
            }
        }
        return null
    }

    private suspend fun prefetchAndInlineImages(
        questions: List<QuestionItem>,
        onProgress: (String, Float?) -> Unit
    ): List<QuestionItem> = coroutineScope {
        val urls = Integrity.extractAllowedRemoteImageUrls(questions)
        if (urls.isEmpty()) return@coroutineScope questions

        val total = urls.size
        onProgress("正在并发预取 $total 张公式/插图…", 0.28f)
        val completed = AtomicInteger(0)
        val urlMap = ConcurrentHashMap<String, String>(total)
        val sem = Semaphore(10)

        urls.map { url ->
            async(Dispatchers.IO) {
                sem.withPermit {
                    downloadImageAsDataUri(url)?.let { urlMap[url] = it }
                    val done = completed.incrementAndGet()
                    onProgress("正在并发预取公式与插图 ($done/$total)…", 0.28f + 0.17f * done / total)
                }
            }
        }.awaitAll()

        if (urlMap.isEmpty()) return@coroutineScope questions
        onProgress("正在并行内联 ${urlMap.size}/$total 张图片资源…", 0.45f)

        val workers = Runtime.getRuntime().availableProcessors().coerceIn(2, 8)
        if (questions.size < 32) {
            return@coroutineScope Integrity.applyInlinedImages(questions, urlMap)
        }
        val chunkSize = (questions.size + workers - 1) / workers
        questions.chunked(chunkSize).map { slice ->
            async(Dispatchers.Default) {
                Integrity.applyInlinedImages(slice, urlMap)
            }
        }.awaitAll().flatten()
    }

    private suspend fun buildChunkHtmlsInParallel(
        questions: List<QuestionItem>,
        variant: AnswerVariant,
        title: String,
        smartPagination: Boolean
    ): List<String> = coroutineScope {
        val chunks = Integrity.buildAdaptiveQuestionChunks(questions)
        if (chunks.size <= 1) {
            return@coroutineScope listOf(
                Integrity.buildExportDocumentHtml(
                    questions = questions,
                    variant = variant,
                    title = title,
                    smartPagination = smartPagination
                )
            )
        }
        val metas = ArrayList<ChunkRenderMeta>(chunks.size)
        var startIdx = 1
        var prevGroup: Triple<String, String, String>? = null
        for ((idx, slice) in chunks.withIndex()) {
            metas.add(
                ChunkRenderMeta(
                    slice = slice,
                    startIndex = startIdx,
                    includeHeader = (idx == 0),
                    initialGroup = prevGroup
                )
            )
            startIdx += slice.size
            val lastQ = slice.last()
            prevGroup = Triple(lastQ.subjectName, lastQ.chapterName, lastQ.questionType)
        }
        metas.map { meta ->
            async(Dispatchers.Default) {
                Integrity.buildExportDocumentHtml(
                    questions = meta.slice,
                    variant = variant,
                    title = title,
                    startIndex = meta.startIndex,
                    includeHeader = meta.includeHeader,
                    initialGroup = meta.initialGroup,
                    smartPagination = smartPagination
                )
            }
        }.awaitAll()
    }

    private suspend fun renderHtmlListPipelined(
        session: WebViewRenderSession,
        htmlList: List<String>,
        tempDir: File,
        prefix: String,
        onChunkDone: (completedIndex: Int, total: Int) -> Unit
    ): List<File> = coroutineScope {
        val writeSem = Semaphore(2)
        val writeJobs = ArrayList<Deferred<File>>(htmlList.size)
        for ((idx, html) in htmlList.withIndex()) {
            val doc = session.renderHtmlToPdfDocument(html)
            val outFile = File(tempDir, "${prefix}_$idx.pdf")
            val job = async(Dispatchers.IO) {
                writeSem.withPermit {
                    try {
                        FileOutputStream(outFile).use { fos -> doc.writeTo(fos) }
                    } finally {
                        doc.close()
                    }
                    outFile
                }
            }
            writeJobs.add(job)
            onChunkDone(idx + 1, htmlList.size)
        }
        writeJobs.awaitAll()
    }

    private suspend fun mergeChunkFilesToTarget(chunkFiles: List<File>, targetPdf: File) = withContext(Dispatchers.IO) {
        if (chunkFiles.size == 1) {
            chunkFiles.first().copyTo(targetPdf, overwrite = true)
            return@withContext
        }
        PDFBoxResourceLoader.init(context.applicationContext)
        val merger = PDFMergerUtility()
        merger.destinationFileName = targetPdf.absolutePath
        chunkFiles.forEach { merger.addSource(it) }
        merger.mergeDocuments(MemoryUsageSetting.setupMixed(32L * 1024L * 1024L))
    }

    suspend fun exportMergedPdf(
        questions: List<QuestionItem>,
        variant: AnswerVariant,
        baseName: String,
        smartPagination: Boolean = true,
        onProgress: (String, Float?) -> Unit
    ): ExportedFileEntry = withContext(Dispatchers.Default) {
        Integrity.validateQuestions(questions)
        onProgress("正在准备渲染 ${questions.size} 道题（多线程管道排版）…", 0.28f)
        val inlined = prefetchAndInlineImages(questions, onProgress)

        onProgress("正在并行生成排版文档分片…", 0.46f)
        val htmlChunks = buildChunkHtmlsInParallel(inlined, variant, baseName, smartPagination)

        val vTag = when (variant) {
            AnswerVariant.WITH_ANSWERS_RED -> "红标答案"
            AnswerVariant.WITH_ANSWERS_PLAIN -> "普通答案"
            AnswerVariant.WITHOUT_ANSWERS -> "无答案"
        }
        val ts = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.CHINA).format(Date())
        val fileName = "${Integrity.safeArchiveSegment(baseName)}_${vTag}_$ts.pdf"
        val dir = withContext(Dispatchers.IO) { File(context.filesDir, "exports").apply { mkdirs() } }
        val localFile = File(dir, fileName)
        val tempDir = File(context.cacheDir, "pdf_chunks_${System.nanoTime()}").apply { mkdirs() }

        val session = createWebViewSession()
        try {
            val chunkFiles = renderHtmlListPipelined(session, htmlChunks, tempDir, "chunk") { done, total ->
                val frac = 0.47f + 0.46f * done / total.coerceAtLeast(1)
                onProgress("正在分页制版分片 ($done/$total)…", frac)
            }
            onProgress("正在合成最终 A4 PDF 文档…", 0.94f)
            mergeChunkFilesToTarget(chunkFiles, localFile)
        } finally {
            session.close()
            withContext(Dispatchers.IO) { tempDir.deleteRecursively() }
        }

        onProgress("正在写入系统 Download/CCTRExport 目录…", 0.98f)
        withContext(Dispatchers.IO) {
            mirrorToDownloads(fileName, "application/pdf", localFile)
        }
        ExportedFileEntry(
            name = fileName,
            path = localFile.absolutePath,
            sizeBytes = localFile.length(),
            createdAt = ts,
            questionCount = questions.size,
            format = ExportFormat.MERGED_PDF
        )
    }

    suspend fun exportCategorizedZip(
        questions: List<QuestionItem>,
        variant: AnswerVariant,
        baseName: String,
        smartPagination: Boolean = true,
        onProgress: (String, Float?) -> Unit
    ): ExportedFileEntry = withContext(Dispatchers.Default) {
        Integrity.validateQuestions(questions)
        onProgress("正在准备分类归档 ${questions.size} 道题…", 0.28f)
        val inlined = prefetchAndInlineImages(questions, onProgress)

        val groups = inlined.groupBy { Triple(it.subjectName, it.chapterName, it.questionType) }
        val usedPaths = HashSet<String>()
        val groupEntries = groups.entries.toList()
        val relPaths = ArrayList<String>(groupEntries.size)
        for ((key, _) in groupEntries) {
            val sDir = Integrity.safeArchiveSegment(key.first)
            val cDir = Integrity.safeArchiveSegment(key.second)
            val tName = Integrity.safeArchiveSegment(key.third)
            var relPath = "$sDir/$cDir/$tName.pdf"
            var suffix = 2
            while (!usedPaths.add(relPath.lowercase())) {
                relPath = "$sDir/$cDir/${tName}_$suffix.pdf"
                suffix++
            }
            relPaths.add(relPath)
        }

        onProgress("正在并行生成 ${groupEntries.size} 个分类排版 HTML…", 0.46f)
        val groupHtmlLists = coroutineScope {
            groupEntries.map { (key, items) ->
                async(Dispatchers.Default) {
                    buildChunkHtmlsInParallel(
                        questions = items,
                        variant = variant,
                        title = "${key.first} / ${key.second} / ${key.third}",
                        smartPagination = smartPagination
                    )
                }
            }.awaitAll()
        }
        val totalChunks = groupHtmlLists.sumOf { it.size }.coerceAtLeast(1)

        val vTag = when (variant) {
            AnswerVariant.WITH_ANSWERS_RED -> "红标答案"
            AnswerVariant.WITH_ANSWERS_PLAIN -> "普通答案"
            AnswerVariant.WITHOUT_ANSWERS -> "无答案"
        }
        val ts = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.CHINA).format(Date())
        val fileName = "${Integrity.safeArchiveSegment(baseName)}_${vTag}_$ts.zip"
        val dir = withContext(Dispatchers.IO) { File(context.filesDir, "exports").apply { mkdirs() } }
        val localZip = File(dir, fileName)
        val tempDir = File(context.cacheDir, "zip_chunks_${System.nanoTime()}").apply { mkdirs() }
        val manifestGroups = JSONArray()

        val session = createWebViewSession()
        var renderedSoFar = 0
        try {
            val renderedGroupChunkFiles = ArrayList<List<File>>(groupEntries.size)
            for (gIdx in groupEntries.indices) {
                val (key, _) = groupEntries[gIdx]
                val htmlList = groupHtmlLists[gIdx]
                val chunkFiles = renderHtmlListPipelined(session, htmlList, tempDir, "grp_${gIdx}") { _, _ ->
                    renderedSoFar++
                    val frac = 0.47f + 0.40f * renderedSoFar / totalChunks
                    onProgress("正在制版分类 (${gIdx + 1}/${groupEntries.size})：${key.second} / ${key.third}", frac)
                }
                renderedGroupChunkFiles.add(chunkFiles)
            }

            onProgress("正在校验 SHA-256 并快速写入 ZIP 归档…", 0.90f)
            withContext(Dispatchers.IO) {
                ZipOutputStream(FileOutputStream(localZip)).use { zos ->
                    zos.setLevel(Deflater.BEST_SPEED)
                    for (gIdx in groupEntries.indices) {
                        val (key, items) = groupEntries[gIdx]
                        val relPath = relPaths[gIdx]
                        val mergedPdf = File(tempDir, "merged_$gIdx.pdf")
                        mergeChunkFilesToTarget(renderedGroupChunkFiles[gIdx], mergedPdf)
                        val pdfBytes = mergedPdf.readBytes()
                        zos.putNextEntry(ZipEntry(relPath))
                        zos.write(pdfBytes)
                        zos.closeEntry()

                        manifestGroups.put(
                            JSONObject().apply {
                                put("subject", key.first)
                                put("chapter", key.second)
                                put("type", key.third)
                                put("path", relPath)
                                put("count", items.size)
                                put("questionIds", JSONArray(items.map { it.id }))
                                put("sha256", Integrity.sha256Hex(pdfBytes))
                            }
                        )
                    }
                    val manifest = JSONObject().apply {
                        put("version", 1)
                        put("variant", variant.key)
                        put("questionCount", questions.size)
                        put("groups", manifestGroups)
                    }
                    zos.putNextEntry(ZipEntry("导出清单.json"))
                    zos.write(manifest.toString(2).toByteArray(Charsets.UTF_8))
                    zos.closeEntry()
                }
            }
        } finally {
            session.close()
            withContext(Dispatchers.IO) { tempDir.deleteRecursively() }
        }

        onProgress("正在写入系统 Download/CCTRExport 目录…", 0.98f)
        withContext(Dispatchers.IO) {
            mirrorToDownloads(fileName, "application/zip", localZip)
        }
        ExportedFileEntry(
            name = fileName,
            path = localZip.absolutePath,
            sizeBytes = localZip.length(),
            createdAt = ts,
            questionCount = questions.size,
            format = ExportFormat.CATEGORIZED_ZIP
        )
    }

    suspend fun exportFormattedFile(
        questions: List<QuestionItem>,
        format: ExportFormat,
        variant: AnswerVariant,
        baseName: String,
        onProgress: (String, Float?) -> Unit
    ): ExportedFileEntry = withContext(Dispatchers.IO) {
        Integrity.validateQuestions(questions)
        onProgress("正在转换 ${questions.size} 道题为 ${format.label}…", 0.55f)
        val bytes = when (format) {
            ExportFormat.EXCEL_XLSX -> FormatConverter.exportToXlsx(questions, variant, baseName)
            ExportFormat.ANKI_TSV -> FormatConverter.exportToAnkiTsv(questions, baseName)
            ExportFormat.MARKDOWN_MD -> FormatConverter.exportToMarkdown(questions, variant, baseName)
            ExportFormat.STANDARD_JSON -> FormatConverter.exportToJson(questions, variant, baseName)
            else -> error("不支持的快捷格式：$format")
        }
        val vTag = when (variant) {
            AnswerVariant.WITH_ANSWERS_RED -> "红标答案"
            AnswerVariant.WITH_ANSWERS_PLAIN -> "普通答案"
            AnswerVariant.WITHOUT_ANSWERS -> "无答案"
        }
        val ts = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.CHINA).format(Date())
        val fileName = "${Integrity.safeArchiveSegment(baseName)}_${vTag}_$ts.${format.ext}"
        val dir = File(context.filesDir, "exports").apply { mkdirs() }
        val localFile = File(dir, fileName)
        localFile.writeBytes(bytes)
        onProgress("正在写入系统 Download/CCTRExport 目录…", 0.92f)
        mirrorToDownloads(fileName, format.mimeType, localFile)
        ExportedFileEntry(
            name = fileName,
            path = localFile.absolutePath,
            sizeBytes = localFile.length(),
            createdAt = ts,
            questionCount = questions.size,
            format = format
        )
    }

    private fun mirrorToDownloads(fileName: String, mimeType: String, sourceFile: File) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            runCatching {
                val values = ContentValues().apply {
                    put(MediaStore.Downloads.DISPLAY_NAME, fileName)
                    put(MediaStore.Downloads.MIME_TYPE, mimeType)
                    put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/CCTRExport")
                }
                val uri = context.contentResolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                if (uri != null) {
                    context.contentResolver.openOutputStream(uri)?.use { out ->
                        sourceFile.inputStream().use { inp -> inp.copyTo(out) }
                    }
                }
            }
        }
    }

    fun listSavedExports(): List<File> {
        val dir = File(context.filesDir, "exports")
        if (!dir.exists()) return emptyList()
        return dir.listFiles()?.sortedByDescending { it.lastModified() } ?: emptyList()
    }
}
