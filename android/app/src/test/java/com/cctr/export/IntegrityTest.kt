package com.cctr.export

import com.cctr.export.core.AnswerVariant
import com.cctr.export.core.Integrity
import com.cctr.export.core.QuestionItem
import com.cctr.export.core.QuestionOption
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class IntegrityTest {
    @Test
    fun sanitizeRejectsScriptAndUntrustedImages() {
        val clean = Integrity.sanitizeRichHtml("<p>题目内容</p><img src=\"data:image/png;base64,iVBORw0KGgo=\" />")
        assertTrue(clean.contains("<p>题目内容</p>"))

        var threwScript = false
        try {
            Integrity.sanitizeRichHtml("<script>alert(1)</script><p>x</p>")
        } catch (_: IllegalArgumentException) {
            threwScript = true
        }
        assertTrue(threwScript)

        var threwUntrusted = false
        try {
            Integrity.sanitizeRichHtml("<img src=\"https://evil.com/x.png\" />")
        } catch (_: IllegalArgumentException) {
            threwUntrusted = true
        }
        assertTrue(threwUntrusted)
    }

    @Test
    fun buildDocumentLabelsChoiceOnlyAndSupportsLongAnswers() {
        val qChoice = QuestionItem(
            id = "1:10",
            questionType = "单选题",
            subjectHtml = "<p>1+1=?</p>",
            answer = "A",
            hasOptions = true,
            options = listOf(QuestionOption(true, "2"), QuestionOption(false, "3")),
            isChoice = true
        )
        val qFill = QuestionItem(
            id = "1:11",
            questionType = "填空题",
            subjectHtml = "光速约为___",
            answer = "3e8 m/s",
            hasOptions = false,
            options = emptyList(),
            isChoice = false
        )
        val html = Integrity.buildExportDocumentHtml(listOf(qChoice, qFill), AnswerVariant.WITH_ANSWERS_RED)
        assertTrue(html.contains("<span class=\"option-label\">A.</span>"))
        assertTrue(html.contains("<span class=\"option-label\">B.</span>"))
        assertTrue(html.contains("3e8 m/s"))
        assertFalse(html.contains("<span class=\"option-label\">C.</span>"))
    }

    @Test
    fun safeArchiveSegmentSanitizesWindowsReserved() {
        assertEquals("_con", Integrity.safeArchiveSegment("con"))
        assertEquals("第一章_导论", Integrity.safeArchiveSegment("第一章:导论"))
    }

    @Test
    fun buildDocumentEnforcesUniformBodyFontAndImageScaler() {
        val q = QuestionItem(
            id = "1:99",
            questionType = "计算题",
            subjectHtml = "<p style=\"font-size:24pt;font-family:SimSun;\">求矢量场<sup>2</sup></p>",
            answer = "<p style=\"font-size:18pt;\">解答</p>",
            hasOptions = false,
            options = emptyList(),
            isChoice = false
        )
        val html = Integrity.buildExportDocumentHtml(listOf(q))
        assertTrue(html.contains("font-size: 10.5pt !important"))
        assertTrue(html.contains("font-size: 7.5pt !important"))
        assertFalse(html.contains("24pt"))
        assertFalse(html.contains("18pt"))
        assertTrue(Integrity.VERIFY_AND_SLICE_JS.contains("Math.round(natW * 0.45)"))
        assertTrue(Integrity.VERIFY_AND_SLICE_JS.contains("baseW * 0.86"))

        val chunk2 = Integrity.buildExportDocumentHtml(
            listOf(q),
            title = "物理",
            startIndex = 9,
            includeHeader = false,
            initialGroup = Triple("未分类学科", "未分类章节", "计算题")
        )
        assertTrue(chunk2.contains("第 9 题"))
        assertFalse(chunk2.contains("<h1>"))
        assertFalse(chunk2.contains("<h2>"))

        val entityClean = Integrity.sanitizeRichHtml("<p>A &nbsp; B &amp; C</p>")
        assertTrue(entityClean.contains("&nbsp;"))
        assertFalse(entityClean.contains("&amp;nbsp;"))

        assertTrue(Integrity.buildExportDocumentHtml(listOf(q), smartPagination = true).contains("data-smart-pagination=\"1\""))
        assertTrue(Integrity.buildExportDocumentHtml(listOf(q), smartPagination = false).contains("data-smart-pagination=\"0\""))
    }
}
