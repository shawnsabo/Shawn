package com.cctr.export.core

enum class AnswerVariant(val key: String, val label: String) {
    WITH_ANSWERS_RED("withAnswersRed", "红标答案"),
    WITH_ANSWERS_PLAIN("withAnswersPlain", "纯答案"),
    WITHOUT_ANSWERS("withoutAnswers", "无答案")
}

enum class ExportFormat(val label: String, val subtitle: String) {
    MERGED_PDF("合并单个 PDF", "A4 无损排版 · 跨页不截断"),
    CATEGORIZED_ZIP("分类打包 ZIP", "学科/章节/题型 + 校验清单")
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
