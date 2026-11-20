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
import android.view.View
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import com.tom_roush.pdfbox.android.PDFBoxResourceLoader
import com.tom_roush.pdfbox.io.MemoryUsageSetting
import com.tom_roush.pdfbox.multipdf.PDFMergerUtility
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.FileOutputStream
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
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
        private const val CHUNK_QUESTION_SIZE = 6

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

    private fun releaseWebView(webView: WebView) {
        runCatching {
            webView.stopLoading()
            webView.loadUrl("about:blank")
            webView.clearHistory()
            webView.removeAllViews()
            webView.destroy()
        }
    }

    suspend fun renderHtmlToPdfBytes(html: String): ByteArray = suspendCancellableCoroutine { cont ->
        mainHandler.post {
            val webView = WebView(context.applicationContext)
            var finished = false
            fun fail(msg: String) {
                if (finished) return
                finished = true
                releaseWebView(webView)
                if (cont.isActive) cont.resumeWithException(IllegalStateException(msg))
            }
            fun succeed(bytes: ByteArray) {
                if (finished) return
                finished = true
                releaseWebView(webView)
                if (cont.isActive) cont.resume(bytes)
            }

            webView.settings.apply {
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
            webView.setBackgroundColor(android.graphics.Color.WHITE)
            webView.layout(0, 0, initPhysW, (1000f * density).roundToInt())

            webView.webViewClient = object : WebViewClient() {
                override fun shouldInterceptRequest(view: WebView?, request: WebResourceRequest?): WebResourceResponse? {
                    val uri = request?.url ?: return null
                    val scheme = uri.scheme?.lowercase().orEmpty()
                    val host = uri.host?.lowercase().orEmpty()
                    if (scheme == "data" || scheme == "about") return null
                    if (scheme == "https" && (
                            host == "cctrcloud.net" || host.endsWith(".cctrcloud.net") ||
                            host == "aliyuncs.com" || host.endsWith(".aliyuncs.com")
                        )
                    ) return null
                    return WebResourceResponse("text/plain", "utf-8", ByteArrayInputStream(ByteArray(0)))
                }

                override fun onPageFinished(view: WebView?, url: String?) {
                    if (finished) return
                    // 轮询异步 VERIFY_AND_SLICE_JS 的结果
                    val wrapper = """
                        window.__cctrVerifyOut = null;
                        (${Integrity.VERIFY_AND_SLICE_JS.trim()})
                          .then(r => { window.__cctrVerifyOut = r; })
                          .catch(e => { window.__cctrVerifyOut = JSON.stringify({ ok: false, error: String(e) }); });
                    """.trimIndent()
                    webView.evaluateJavascript(wrapper, null)

                    var checks = 0
                    fun pollVerify() {
                        if (finished) return
                        checks++
                        if (checks > 1200) {
                            fail("图片解码或排版校验超时")
                            return
                        }
                        webView.evaluateJavascript("window.__cctrVerifyOut") { rawRes ->
                            val clean = rawRes?.trim().orEmpty()
                            if (clean == "null" || clean.isEmpty()) {
                                mainHandler.postDelayed(::pollVerify, 100)
                                return@evaluateJavascript
                            }
                            val jsonStr = decodeJsString(clean)
                            val obj = runCatching { JSONObject(jsonStr) }.getOrNull()
                            if (obj == null || !obj.optBoolean("ok", false)) {
                                fail(obj?.optString("error").orEmpty().ifBlank { "PDF 内容完整性校验失败" })
                                return@evaluateJavascript
                            }
                            // 校验通过，计算自然分页断点并绘制 PdfDocument
                            webView.evaluateJavascript(COMPUTE_BREAKS_JS) { rawBrk ->
                                val brkJson = runCatching { JSONObject(decodeJsString(rawBrk.orEmpty())) }.getOrNull()
                                if (brkJson == null) {
                                    fail("无法计算 PDF 分页尺寸")
                                    return@evaluateJavascript
                                }
                                val cssTotalH = brkJson.optDouble("totalH", 800.0).coerceAtLeast(100.0)
                                val dpr = brkJson.optDouble("dpr", density.toDouble()).toFloat().coerceAtLeast(1f)
                                val physW = (CSS_VIEW_WIDTH_PX * dpr).roundToInt()
                                val physTotalH = ceil(cssTotalH * dpr).toInt().coerceAtLeast(100)
                                val arr = brkJson.optJSONArray("breaks") ?: JSONArray(listOf(0, cssTotalH.toInt()))
                                val cssBreaks = List(arr.length()) { idx -> arr.optDouble(idx) }

                                webView.measure(
                                    View.MeasureSpec.makeMeasureSpec(physW, View.MeasureSpec.EXACTLY),
                                    View.MeasureSpec.makeMeasureSpec(physTotalH, View.MeasureSpec.EXACTLY)
                                )
                                webView.layout(0, 0, physW, physTotalH)
                                val pdfScale = CONTENT_W_PT / physW.toFloat()

                                val doc = PdfDocument()
                                try {
                                    for (i in 0 until cssBreaks.size - 1) {
                                        val physTop = (cssBreaks[i] * dpr).toFloat()
                                        val physBottom = ceil(cssBreaks[i + 1] * dpr).toFloat()
                                        val slicePhysH = (physBottom - physTop).coerceAtMost(CONTENT_H_PT / pdfScale)
                                        if (slicePhysH <= 1f) continue
                                        val pageInfo = PdfDocument.PageInfo.Builder(PDF_PAGE_W, PDF_PAGE_H, i + 1).create()
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
                                    val baos = ByteArrayOutputStream()
                                    doc.writeTo(baos)
                                    succeed(baos.toByteArray())
                                } catch (e: Exception) {
                                    fail("PDF 生成失败: ${e.message}")
                                } finally {
                                    doc.close()
                                }
                            }
                        }
                    }
                    mainHandler.postDelayed(::pollVerify, 80)
                }
            }

            webView.loadDataWithBaseURL("https://cctrcloud.net/", html, "text/html", "utf-8", null)
        }
    }

    private suspend fun renderQuestionsChunkedToFile(
        questions: List<QuestionItem>,
        variant: AnswerVariant,
        title: String,
        targetPdf: File,
        smartPagination: Boolean = true,
        onProgress: (String) -> Unit
    ) {
        Integrity.validateQuestions(questions)
        if (questions.size <= CHUNK_QUESTION_SIZE) {
            val html = Integrity.buildExportDocumentHtml(questions, variant, title = title, smartPagination = smartPagination)
            targetPdf.writeBytes(renderHtmlToPdfBytes(html))
            return
        }

        PDFBoxResourceLoader.init(context.applicationContext)
        val tempDir = File(context.cacheDir, "pdf_chunks_${System.nanoTime()}").apply { mkdirs() }
        val chunkFiles = mutableListOf<File>()
        try {
            var prevGroup: Triple<String, String, String>? = null
            var idx = 0
            while (idx < questions.size) {
                val end = minOf(idx + CHUNK_QUESTION_SIZE, questions.size)
                val slice = questions.subList(idx, end)
                onProgress("正在分页渲染第 ${idx + 1}–$end 题 / 共 ${questions.size} 题…")
                val html = Integrity.buildExportDocumentHtml(
                    slice,
                    variant = variant,
                    title = title,
                    startIndex = idx + 1,
                    includeHeader = (idx == 0),
                    initialGroup = prevGroup,
                    smartPagination = smartPagination
                )
                val lastQ = slice.last()
                prevGroup = Triple(lastQ.subjectName, lastQ.chapterName, lastQ.questionType)

                val chunkFile = File(tempDir, "chunk_${chunkFiles.size}.pdf")
                val bytes = renderHtmlToPdfBytes(html)
                chunkFile.writeBytes(bytes)
                chunkFiles.add(chunkFile)
                idx = end
            }
            onProgress("正在合并 ${chunkFiles.size} 个分段 A4 PDF…")
            withContext(Dispatchers.IO) {
                val merger = PDFMergerUtility()
                merger.destinationFileName = targetPdf.absolutePath
                chunkFiles.forEach { merger.addSource(it) }
                merger.mergeDocuments(MemoryUsageSetting.setupTempFileOnly())
            }
        } finally {
            tempDir.deleteRecursively()
        }
    }

    suspend fun exportMergedPdf(
        questions: List<QuestionItem>,
        variant: AnswerVariant,
        baseName: String,
        smartPagination: Boolean = true,
        onProgress: (String) -> Unit
    ): ExportedFileEntry {
        Integrity.validateQuestions(questions)
        onProgress("正在准备渲染 ${questions.size} 道题（分段低内存排版）…")
        val vTag = when (variant) {
            AnswerVariant.WITH_ANSWERS_RED -> "红标答案"
            AnswerVariant.WITH_ANSWERS_PLAIN -> "普通答案"
            AnswerVariant.WITHOUT_ANSWERS -> "无答案"
        }
        val ts = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.CHINA).format(Date())
        val fileName = "${Integrity.safeArchiveSegment(baseName)}_${vTag}_$ts.pdf"
        val dir = File(context.filesDir, "exports").apply { mkdirs() }
        val localFile = File(dir, fileName)
        renderQuestionsChunkedToFile(questions, variant, baseName, localFile, smartPagination, onProgress)
        mirrorToDownloads(fileName, "application/pdf", localFile)
        return ExportedFileEntry(
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
        onProgress: (String) -> Unit
    ): ExportedFileEntry {
        Integrity.validateQuestions(questions)
        val groups = questions.groupBy { Triple(it.subjectName, it.chapterName, it.questionType) }
        val tempPdf = File(context.cacheDir, "zip_grp_${System.nanoTime()}.pdf")
        val vTag = when (variant) {
            AnswerVariant.WITH_ANSWERS_RED -> "红标答案"
            AnswerVariant.WITH_ANSWERS_PLAIN -> "普通答案"
            AnswerVariant.WITHOUT_ANSWERS -> "无答案"
        }
        val ts = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.CHINA).format(Date())
        val fileName = "${Integrity.safeArchiveSegment(baseName)}_${vTag}_$ts.zip"
        val dir = File(context.filesDir, "exports").apply { mkdirs() }
        val localZip = File(dir, fileName)
        val manifestGroups = JSONArray()
        val usedPaths = HashSet<String>()

        try {
            ZipOutputStream(FileOutputStream(localZip)).use { zos ->
                var idx = 0
                for ((key, items) in groups) {
                    idx++
                    onProgress("正在打包分类 PDF ($idx/${groups.size})：${key.second} / ${key.third}")
                    val sDir = Integrity.safeArchiveSegment(key.first)
                    val cDir = Integrity.safeArchiveSegment(key.second)
                    val tName = Integrity.safeArchiveSegment(key.third)
                    var relPath = "$sDir/$cDir/$tName.pdf"
                    var suffix = 2
                    while (!usedPaths.add(relPath.lowercase())) {
                        relPath = "$sDir/$cDir/${tName}_$suffix.pdf"
                        suffix++
                    }
                    renderQuestionsChunkedToFile(
                        items,
                        variant,
                        "${key.first} / ${key.second} / ${key.third}",
                        tempPdf,
                        smartPagination,
                        onProgress
                    )
                    val pdfBytes = tempPdf.readBytes()
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
        } finally {
            tempPdf.delete()
        }

        mirrorToDownloads(fileName, "application/zip", localZip)
        return ExportedFileEntry(
            name = fileName,
            path = localZip.absolutePath,
            sizeBytes = localZip.length(),
            createdAt = ts,
            questionCount = questions.size,
            format = ExportFormat.CATEGORIZED_ZIP
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

    private fun decodeJsString(raw: String): String {
        val t = raw.trim()
        return if (t.startsWith("\"") && t.endsWith("\"")) {
            JSONObject("{\"v\":$t}").getString("v")
        } else {
            t
        }
    }
}
