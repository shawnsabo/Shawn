package com.cctr.export.ui

import android.app.Application
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
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

data class MainUiState(
    val activeTab: Int = 0, // 0=导出工作台, 1=任务进度, 2=本地文件
    val wizardStep: Int = 1, // 1=登录, 2=选练习, 3=导出设置
    val schoolCode: String = "",
    val username: String = "",
    val password: String = "",
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
    val exportProgressText: String = "",
    val exportResult: ExportedFileEntry? = null,
    val exportError: String? = null,
    val logs: List<String> = emptyList(),
    val savedFiles: List<File> = emptyList()
)

class MainViewModel(application: Application) : AndroidViewModel(application) {
    private val api = CctrApiClient()
    private val exporter = PdfAndZipExporter(application)
    private val ocr: CaptchaOcr? = runCatching { CaptchaOcr(application) }.getOrNull()

    private val _state = MutableStateFlow(MainUiState())
    val state: StateFlow<MainUiState> = _state.asStateFlow()

    init {
        refreshSavedFiles()
        loadCaptcha()
    }

    private fun appendLog(msg: String) {
        val ts = SimpleDateFormat("HH:mm:ss", Locale.CHINA).format(Date())
        _state.update { s -> s.copy(logs = (s.logs + "[$ts] $msg").takeLast(120)) }
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
        val selected = s.practices.filter { it.id in s.selectedPracticeIds }
        if (selected.isEmpty()) return

        val filterChapters = s.chapters.filter { it.id in s.selectedChapterIds }
        val filterTypes = s.questionTypes.filter { (it.questionTypeId.ifBlank { it.id }) in s.selectedTypeIds }

        _state.update {
            it.copy(
                exporting = true,
                exportError = null,
                exportResult = null,
                exportProgressText = "正在分页读取题目与核对题数…"
            )
        }
        appendLog("开始导出 ${selected.size} 个练习（已启用题数核对与图像/页宽校验）")

        viewModelScope.launch {
            try {
                val allQuestions = withContext(Dispatchers.IO) {
                    val out = mutableListOf<QuestionItem>()
                    for (p in selected) {
                        appendLog("正在拉取：「${p.practiceName}」")
                        val qs = api.queryQuestions(p, filterChapters, filterTypes, s.practicedOnly)
                        appendLog("✓ 「${p.practiceName}」核对通过：${qs.size} 题")
                        out.addAll(qs)
                    }
                    out
                }
                val baseName = if (selected.size == 1) selected.first().practiceName else "融智云考批量导出_${selected.size}份"
                val result = when (s.exportFormat) {
                    ExportFormat.MERGED_PDF -> exporter.exportMergedPdf(allQuestions, s.answerVariant, baseName, s.smartPagination) { msg ->
                        _state.update { it.copy(exportProgressText = msg) }
                        appendLog(msg)
                    }
                    ExportFormat.CATEGORIZED_ZIP -> exporter.exportCategorizedZip(allQuestions, s.answerVariant, baseName, s.smartPagination) { msg ->
                        _state.update { it.copy(exportProgressText = msg) }
                        appendLog(msg)
                    }
                }
                refreshSavedFiles()
                _state.update {
                    it.copy(
                        exporting = false,
                        exportProgressText = "导出完成：${result.name}（共 ${result.questionCount} 题）",
                        exportResult = result
                    )
                }
                appendLog("✓ 导出成功：${result.name}（${result.sizeBytes / 1024} KB）")
            } catch (e: Exception) {
                _state.update {
                    it.copy(
                        exporting = false,
                        exportError = e.message ?: "导出失败",
                        exportProgressText = "导出失败：${e.message}"
                    )
                }
                appendLog("✗ 导出失败：${e.message}")
            }
        }
    }

    fun refreshSavedFiles() {
        _state.update { it.copy(savedFiles = exporter.listSavedExports()) }
    }

    override fun onCleared() {
        ocr?.close()
        super.onCleared()
    }
}
