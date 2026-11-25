package com.cctr.export.ui

import android.app.Application
import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.cctr.export.core.AnswerVariant
import com.cctr.export.core.CaptchaOcr
import com.cctr.export.core.CctrApiClient
import com.cctr.export.core.ChapterItem
import com.cctr.export.core.ExportFormat
import com.cctr.export.core.ExportedFileEntry
import com.cctr.export.core.PdfAndZipExporter
import com.cctr.export.core.PracticeItem
import com.cctr.export.core.QuestionItem
import com.cctr.export.core.QuestionTypeItem
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.sync.withPermit
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicLong

data class SavedAccount(
    val schoolCode: String,
    val username: String
)

data class LogEntry(
    val id: Long,
    val text: String
)

data class SavedFileUi(
    val file: File,
    val name: String,
    val ext: String,
    val sizeKb: Long,
    val path: String
)

data class MainUiState(
    val activeTab: Int = 0, // 0=导出工作台, 1=任务进度, 2=本地文件
    val wizardStep: Int = 1, // 1=登录, 2=选练习, 3=导出设置
    val ocrReady: Boolean = false,
    val schoolCode: String = "",
    val username: String = "",
    val password: String = "",
    val savedAccounts: List<SavedAccount> = emptyList(),
    val captchaCode: String = "",
    val captchaBitmap: Bitmap? = null,
    val captchaLoading: Boolean = false,
    val captchaStatus: String = "正在获取验证码…",
    val captchaAutoRecognized: Boolean = false,
    val captchaError: String? = null,
    val loginBusy: Boolean = false,
    val loginError: String? = null,
    val practices: List<PracticeItem> = emptyList(),
    val practiceSearch: String = "",
    val selectedPracticeIds: Set<Int> = emptySet(),
    val chapters: List<ChapterItem> = emptyList(),
    val questionTypes: List<QuestionTypeItem> = emptyList(),
    val selectedChapterIds: Set<String> = emptySet(),
    val selectedTypeIds: Set<String> = emptySet(),
    val practicedOnly: Boolean = false,
    val smartPagination: Boolean = true,
    val answerVariant: AnswerVariant = AnswerVariant.WITH_ANSWERS_RED,
    val exportFormat: ExportFormat = ExportFormat.MERGED_PDF,
    val exporting: Boolean = false,
    val exportProgress: Float? = null,
    val exportProgressText: String = "",
    val exportResult: ExportedFileEntry? = null,
    val exportError: String? = null,
    val logs: List<LogEntry> = emptyList(),
    val savedFiles: List<SavedFileUi> = emptyList()
)

class MainViewModel(application: Application) : AndroidViewModel(application) {
    private val api = CctrApiClient()
    private val exporter = PdfAndZipExporter(application)
    private val prefs = application.getSharedPreferences("cctr_atelier_prefs", Context.MODE_PRIVATE)

    private val ocrMutex = Mutex()
    @Volatile
    private var ocrInstance: CaptchaOcr? = null
    @Volatile
    private var ocrInitAttempted = false

    private val nextLogId = AtomicLong(1L)
    private var lastProgressPushMs = 0L

    private val _state = MutableStateFlow(MainUiState(savedAccounts = loadSavedAccounts()))
    val state: StateFlow<MainUiState> = _state.asStateFlow()

    init {
        refreshSavedFiles()
        loadCaptcha()
    }

    private suspend fun getOrInitOcr(): CaptchaOcr? {
        ocrInstance?.let { return it }
        if (ocrInitAttempted) return null
        return ocrMutex.withLock {
            ocrInstance?.let { return@withLock it }
            if (ocrInitAttempted) return@withLock null
            ocrInitAttempted = true
            val created = withContext(Dispatchers.IO) {
                runCatching { CaptchaOcr(getApplication()) }.getOrNull()
            }
            ocrInstance = created
            if (created != null) {
                _state.update { it.copy(ocrReady = true) }
            }
            created
        }
    }

    private fun loadSavedAccounts(): List<SavedAccount> {
        val raw = prefs.getString("saved_accounts", "[]") ?: "[]"
        val arr = runCatching { JSONArray(raw) }.getOrNull() ?: return emptyList()
        val out = mutableListOf<SavedAccount>()
        for (i in 0 until arr.length()) {
            val obj = arr.optJSONObject(i) ?: continue
            val sc = obj.optString("school").trim()
            val un = obj.optString("username").trim()
            if (sc.isNotEmpty() && un.isNotEmpty()) {
                out += SavedAccount(sc, un)
            }
        }
        return out.take(6)
    }

    private fun persistSavedAccounts(list: List<SavedAccount>) {
        val arr = JSONArray()
        list.take(6).forEach { acc ->
            arr.put(JSONObject().apply {
                put("school", acc.schoolCode)
                put("username", acc.username)
            })
        }
        prefs.edit().putString("saved_accounts", arr.toString()).apply()
    }

    fun applySavedAccount(acc: SavedAccount) {
        _state.update { it.copy(schoolCode = acc.schoolCode, username = acc.username, loginError = null) }
    }

    fun removeSavedAccount(acc: SavedAccount) {
        val updated = _state.value.savedAccounts.filterNot { it.schoolCode == acc.schoolCode && it.username == acc.username }
        persistSavedAccounts(updated)
        _state.update { it.copy(savedAccounts = updated) }
    }

    private fun rememberAccount(school: String, username: String) {
        val s = school.trim()
        val u = username.trim()
        if (s.isEmpty() || u.isEmpty()) return
        val updated = (listOf(SavedAccount(s, u)) + _state.value.savedAccounts.filterNot {
            it.schoolCode == s && it.username == u
        }).take(6)
        persistSavedAccounts(updated)
        _state.update { it.copy(savedAccounts = updated) }
    }

    private fun appendLog(msg: String) {
        val ts = SimpleDateFormat("HH:mm:ss", Locale.CHINA).format(Date())
        val entry = LogEntry(id = nextLogId.getAndIncrement(), text = "[$ts] $msg")
        _state.update { s -> s.copy(logs = (s.logs + entry).takeLast(120)) }
    }

    private fun updateExportProgressThrottled(text: String, fraction: Float?, force: Boolean = false) {
        val now = System.currentTimeMillis()
        if (!force && now - lastProgressPushMs < 80L) return
        lastProgressPushMs = now
        _state.update { s ->
            s.copy(
                exportProgressText = text,
                exportProgress = fraction?.coerceIn(0f, 1f) ?: s.exportProgress
            )
        }
    }

    fun setTab(tab: Int) {
        if (tab == 2) refreshSavedFiles()
        _state.update { it.copy(activeTab = tab) }
    }

    fun setWizardStep(step: Int) {
        if (step > 1 && _state.value.practices.isEmpty()) return
        if (step == 3 && _state.value.selectedPracticeIds.isEmpty()) return
        _state.update { it.copy(wizardStep = step) }
    }

    fun signOut() {
        _state.update {
            it.copy(
                wizardStep = 1,
                password = "",
                captchaCode = "",
                practices = emptyList(),
                practiceSearch = "",
                selectedPracticeIds = emptySet(),
                chapters = emptyList(),
                questionTypes = emptyList(),
                selectedChapterIds = emptySet(),
                selectedTypeIds = emptySet(),
                exportResult = null,
                exportError = null,
                exportProgress = null,
                exportProgressText = "",
                loginError = null
            )
        }
        loadCaptcha()
    }

    fun clearLogs() = _state.update { it.copy(logs = emptyList()) }

    fun updateSchoolCode(v: String) = _state.update { it.copy(schoolCode = v) }
    fun updateUsername(v: String) = _state.update { it.copy(username = v) }
    fun updatePassword(v: String) = _state.update { it.copy(password = v) }
    fun updateCaptchaCode(v: String) = _state.update { it.copy(captchaCode = v) }
    fun updatePracticeSearch(q: String) = _state.update { it.copy(practiceSearch = q) }
    fun setAnswerVariant(v: AnswerVariant) = _state.update { it.copy(answerVariant = v) }
    fun setExportFormat(f: ExportFormat) = _state.update { it.copy(exportFormat = f) }
    fun setPracticedOnly(only: Boolean) = _state.update { it.copy(practicedOnly = only) }
    fun setSmartPagination(enabled: Boolean) = _state.update { it.copy(smartPagination = enabled) }

    fun loadCaptcha() {
        if (_state.value.captchaLoading) return
        _state.update {
            it.copy(
                captchaLoading = true,
                captchaStatus = "正在获取并自动识别…",
                captchaAutoRecognized = false,
                captchaError = null
            )
        }
        viewModelScope.launch {
            try {
                val (bmp, recognized) = withContext(Dispatchers.IO) {
                    val ocr = getOrInitOcr()
                    var bestBytes = ByteArray(0)
                    var bestCode = ""
                    val tries = if (ocr != null) 3 else 1
                    for (attempt in 1..tries) {
                        val bytes = api.fetchCaptcha()
                        bestBytes = bytes
                        val code = ocr?.recognize(bytes).orEmpty()
                        if (code.length == 4) {
                            bestCode = code
                            break
                        }
                    }
                    val decodedBmp = BitmapFactory.decodeByteArray(bestBytes, 0, bestBytes.size)
                        ?: error("验证码图片解码失败")
                    decodedBmp to bestCode
                }
                _state.update {
                    it.copy(
                        captchaBitmap = bmp,
                        captchaCode = recognized,
                        captchaLoading = false,
                        captchaAutoRecognized = recognized.length == 4,
                        captchaStatus = if (recognized.length == 4) "✓ 已自动识别" else "请手动输入右侧字符"
                    )
                }
                appendLog(
                    if (recognized.length == 4) "✓ 验证码已获取并自动识别为 $recognized"
                    else "✓ 验证码图片已显示（等待手动输入）"
                )
            } catch (e: Exception) {
                _state.update {
                    it.copy(
                        captchaLoading = false,
                        captchaError = e.message ?: "获取验证码失败",
                        captchaStatus = "获取失败，点击重试"
                    )
                }
                appendLog("✗ 验证码获取失败：${e.message}")
            }
        }
    }

    fun loginAndLoadPractices() {
        val s = _state.value
        if (s.schoolCode.isBlank() || s.username.isBlank() || s.password.isBlank() || s.captchaCode.isBlank()) {
            _state.update { it.copy(loginError = "请填写学校代码、账号、密码和验证码") }
            return
        }
        _state.update { it.copy(loginBusy = true, loginError = null) }
        viewModelScope.launch {
            try {
                val list = withContext(Dispatchers.IO) {
                    api.login(s.schoolCode, s.username, s.password, s.captchaCode)
                    api.getPracticeList()
                }
                val unique = list.distinctBy { "${it.lessonName}|${it.practiceName}" }
                    .sortedWith(compareBy({ it.lessonName }, { it.practiceName }))
                rememberAccount(s.schoolCode, s.username)
                _state.update {
                    it.copy(
                        loginBusy = false,
                        practices = unique,
                        selectedPracticeIds = unique.map { p -> p.id }.toSet(),
                        wizardStep = 2
                    )
                }
                appendLog("✓ 登录成功，共读取 ${unique.size} 个练习")
            } catch (e: Exception) {
                _state.update { it.copy(loginBusy = false, loginError = e.message ?: "登录失败", captchaCode = "") }
                appendLog("✗ 登录失败：${e.message}")
                loadCaptcha()
            }
        }
    }

    fun togglePractice(id: Int) {
        _state.update { s ->
            val next = s.selectedPracticeIds.toMutableSet()
            if (!next.add(id)) next.remove(id)
            s.copy(selectedPracticeIds = next)
        }
    }

    fun toggleSelectAllPractices() {
        _state.update { s ->
            val allIds = s.practices.map { it.id }.toSet()
            val next = if (s.selectedPracticeIds.size == allIds.size) emptySet() else allIds
            s.copy(selectedPracticeIds = next)
        }
    }

    fun proceedToExportSettings() {
        val s = _state.value
        val selected = s.practices.filter { it.id in s.selectedPracticeIds }
        if (selected.isEmpty()) {
            _state.update { it.copy(exportError = "请至少选择一个练习") }
            return
        }
        viewModelScope.launch {
            val (chapters, qtypes) = withContext(Dispatchers.IO) {
                runCatching { api.getChapterAndQuestionTypes(selected.first()) }
                    .getOrElse { emptyList<ChapterItem>() to emptyList<QuestionTypeItem>() }
            }
            _state.update {
                it.copy(
                    chapters = chapters,
                    questionTypes = qtypes,
                    selectedChapterIds = emptySet(),
                    selectedTypeIds = emptySet(),
                    exportError = null,
                    wizardStep = 3
                )
            }
        }
    }

    fun toggleChapter(id: String) {
        _state.update { s ->
            val next = s.selectedChapterIds.toMutableSet()
            if (!next.add(id)) next.remove(id)
            s.copy(selectedChapterIds = next)
        }
    }

    fun toggleType(id: String) {
        _state.update { s ->
            val next = s.selectedTypeIds.toMutableSet()
            if (!next.add(id)) next.remove(id)
            s.copy(selectedTypeIds = next)
        }
    }

    fun startExport() {
        val s = _state.value
        if (s.exporting) return
        val selected = s.practices.filter { it.id in s.selectedPracticeIds }
        if (selected.isEmpty()) return

        val filterChapters = s.chapters.filter { it.id in s.selectedChapterIds }
        val filterTypes = s.questionTypes.filter { (it.questionTypeId.ifBlank { it.id }) in s.selectedTypeIds }

        lastProgressPushMs = 0L
        _state.update {
            it.copy(
                exporting = true,
                exportError = null,
                exportResult = null,
                exportProgress = 0.02f,
                exportProgressText = "正在并发拉取 ${selected.size} 项练习题库…"
            )
        }
        appendLog("开始导出 ${selected.size} 个练习（多线程并发拉取、图片预取与防隔页制版）")

        viewModelScope.launch {
            try {
                val allQuestions = withContext(Dispatchers.IO) {
                    val sem = Semaphore(4)
                    val done = AtomicInteger(0)
                    val totalPractices = selected.size.coerceAtLeast(1)
                    coroutineScope {
                        selected.map { p ->
                            async(Dispatchers.IO) {
                                sem.withPermit {
                                    val qs = api.queryQuestions(p, filterChapters, filterTypes, s.practicedOnly)
                                    val finishedCount = done.incrementAndGet()
                                    appendLog("✓ 「${p.practiceName}」核对通过：${qs.size} 题")
                                    updateExportProgressThrottled(
                                        "已完成 $finishedCount/$totalPractices 项题库拉取与核对…",
                                        0.02f + 0.25f * finishedCount / totalPractices,
                                        force = finishedCount == totalPractices
                                    )
                                    qs
                                }
                            }
                        }.awaitAll().flatten()
                    }
                }
                val baseName = if (selected.size == 1) selected.first().practiceName else "融智云考批量导出_${selected.size}份"
                val result = when (s.exportFormat) {
                    ExportFormat.MERGED_PDF -> exporter.exportMergedPdf(allQuestions, s.answerVariant, baseName, s.smartPagination) { msg, frac ->
                        updateExportProgressThrottled(msg, frac, force = frac != null && frac >= 0.94f)
                    }
                    ExportFormat.CATEGORIZED_ZIP -> exporter.exportCategorizedZip(allQuestions, s.answerVariant, baseName, s.smartPagination) { msg, frac ->
                        updateExportProgressThrottled(msg, frac, force = frac != null && frac >= 0.90f)
                    }
                }
                refreshSavedFiles()
                _state.update {
                    it.copy(
                        exporting = false,
                        exportProgress = 1f,
                        exportProgressText = "导出完成：${result.name}（共 ${result.questionCount} 题）",
                        exportResult = result
                    )
                }
                appendLog("✓ 导出成功：${result.name}（${result.sizeBytes / 1024} KB）")
            } catch (e: Exception) {
                _state.update {
                    it.copy(
                        exporting = false,
                        exportProgress = null,
                        exportError = e.message ?: "导出失败",
                        exportProgressText = "导出失败：${e.message}"
                    )
                }
                appendLog("✗ 导出失败：${e.message}")
            }
        }
    }

    fun refreshSavedFiles() {
        viewModelScope.launch {
            val items = withContext(Dispatchers.IO) {
                exporter.listSavedExports().map { file ->
                    SavedFileUi(
                        file = file,
                        name = file.name,
                        ext = file.extension.uppercase().ifBlank { "FILE" },
                        sizeKb = file.length() / 1024L,
                        path = file.absolutePath
                    )
                }
            }
            _state.update { it.copy(savedFiles = items) }
        }
    }

    override fun onCleared() {
        ocrInstance?.close()
        super.onCleared()
    }
}
