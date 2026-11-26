package com.cctr.export.core

enum class AnswerVariant(val key: String, val label: String) {
    WITH_ANSWERS_RED("withAnswersRed", "红标答案"),
    WITH_ANSWERS_PLAIN("withAnswersPlain", "纯答案"),
    WITHOUT_ANSWERS("withoutAnswers", "无答案")
}

enum class ExportFormat(val label: String, val subtitle: String, val ext: String, val mimeType: String) {
    MERGED_PDF("合并单个 PDF", "A4 无损排版 · 跨页不截断", "pdf", "application/pdf"),
    CATEGORIZED_ZIP("分类打包 ZIP", "学科/章节/题型 + 校验清单", "zip", "application/zip"),
    EXCEL_XLSX("刷题 Excel (.xlsx)", "适配考试宝 / 磨题帮导入", "xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ANKI_TSV("Anki 记忆卡 (.tsv)", "直接导入 Anki 卡片", "tsv", "text/tab-separated-values"),
    MARKDOWN_MD("Markdown (.md)", "Notion / Obsidian 笔记", "md", "text/markdown"),
    STANDARD_JSON("标准 JSON (.json)", "完整结构无损归档", "json", "application/json")
}

data class PracticeItem(
    val id: Int,
    val courseId: String,
    val practiseId: String,
    val teacherId: String,
    val lessonName: String,
    val practiceName: String,
    val teacherName: String,
    val finishTime: String,
    val questionCount: Int? = null
)

data class ChapterItem(
    val id: String,
    val courseId: String,
    val name: String
)

data class QuestionTypeItem(
    val questionTypeId: String,
    val id: String,
    val name: String
)

data class QuestionOption(
    val isTrue: Boolean,
    val html: String
)

data class QuestionItem(
    val id: String,
    val questionType: String,
    val subjectHtml: String,
    val answer: String,
    val hasOptions: Boolean,
    val options: List<QuestionOption>,
    val subjectName: String = "未分类学科",
    val chapterName: String = "未分类章节",
    val analysisHtml: String = "",
    val isChoice: Boolean = false
)

data class ExportedFileEntry(
    val name: String,
    val path: String,
    val sizeBytes: Long,
    val createdAt: String,
    val questionCount: Int,
    val format: ExportFormat
)
