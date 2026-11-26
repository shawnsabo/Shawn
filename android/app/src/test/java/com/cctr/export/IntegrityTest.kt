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

    @Test
    fun wordSmartTagsFontAndMsoCommentsAreSanitizedCleanly() {
        val rawWord = "<!--[if gte mso 9]><xml><w:WordDocument><w:View>Normal</w:View></w:WordDocument></xml><![endif]-->" +
            "<p>载频 <st1:chmetcnv UnitName=\"Hz\">3000Hz</st1:chmetcnv>，" +
            "信息码 <st1:chsdate year=\"2001\">1-1-1</st1:chsdate>，" +
            "<font size=\"4\" face=\"宋体\">基带系统</font><o:p></o:p></p>"
        val clean = Integrity.sanitizeRichHtml(rawWord)
        assertTrue(clean.contains("3000Hz"))
        assertTrue(clean.contains("1-1-1"))
        assertTrue(clean.contains("基带系统"))
        assertFalse(clean.contains("Normal"))
        assertFalse(clean.contains("st1:"))
        assertFalse(clean.contains("<font"))

        assertFalse(
            Integrity.hasVisibleRichContent(
                "<!--[if gte mso 9]><xml><w:WordDocument><w:View>Normal</w:View></w:WordDocument></xml><![endif]--><p> &nbsp; </p>"
            )
        )

        var threwObj = false
        try {
            Integrity.sanitizeRichHtml("<object data=\"x\"></object><p>x</p>")
        } catch (_: IllegalArgumentException) {
            threwObj = true
        }
        assertTrue(threwObj)
    }

    @Test
    fun extractAndApplyInlinedImagesPreservesOrderAndFiltersHosts() {
        val qs = listOf(
            QuestionItem(
                id = "1:1",
                questionType = "单选题",
                subjectHtml = "<p>图1 <img src=\"http://img.cctrcloud.net/a.png?k=1&amp;v=2\" /></p>",
                answer = "<p>见图 <img src='https://oss.aliyuncs.com/b.jpg' /></p>",
                hasOptions = true,
                options = listOf(
                    QuestionOption(true, "<img src=\"https://img.cctrcloud.net/a.png?k=1&v=2\" />"),
                    QuestionOption(false, "<img src=\"https://evil.example.com/c.png\" />")
                ),
                analysisHtml = "<p>已有内联 <img src=\"data:image/png;base64,AAAA\" /></p>",
                isChoice = true
            )
        )
        val urls = Integrity.extractAllowedRemoteImageUrls(qs)
        assertEquals(
            setOf(
                "https://img.cctrcloud.net/a.png?k=1&v=2",
                "https://oss.aliyuncs.com/b.jpg"
            ),
            urls
        )
        val replaced = Integrity.applyInlinedImages(
            qs,
            mapOf(
                "https://img.cctrcloud.net/a.png?k=1&v=2" to "data:image/png;base64,IMG1",
                "https://oss.aliyuncs.com/b.jpg" to "data:image/jpeg;base64,IMG2"
            )
        )
        assertTrue(replaced[0].subjectHtml.contains("data:image/png;base64,IMG1"))
        assertTrue(replaced[0].answer.contains("data:image/jpeg;base64,IMG2"))
        assertTrue(replaced[0].options[0].html.contains("data:image/png;base64,IMG1"))
        assertTrue(replaced[0].options[1].html.contains("https://evil.example.com/c.png"))
        assertTrue(replaced[0].analysisHtml.contains("data:image/png;base64,AAAA"))
    }

    @Test
    fun adaptiveQuestionChunksPreserveAllItemsAndSplitHeavyOnes() {
        val light = (1..30).map { i ->
            QuestionItem(
                id = "1:$i",
                questionType = "单选题",
                subjectHtml = "<p>题干 $i</p>",
                answer = "A",
                hasOptions = false,
                options = emptyList()
            )
        }
        val chunks = Integrity.buildAdaptiveQuestionChunks(light, maxQuestions = 12, maxHtmlChars = 50_000, maxImages = 50)
        assertEquals(3, chunks.size)
        assertEquals(listOf(12, 12, 6), chunks.map { it.size })
        assertEquals(light.map { it.id }, chunks.flatten().map { it.id })

        val heavy = (1..5).map { i ->
            val bigImg = "<img src=\"data:image/png;base64,${"A".repeat(8000)}\" />"
            QuestionItem(
                id = "2:$i",
                questionType = "简答题",
                subjectHtml = "<p>$bigImg $bigImg</p>",
                answer = "解",
                hasOptions = false,
                options = emptyList()
            )
        }
        val heavyChunks = Integrity.buildAdaptiveQuestionChunks(heavy, maxQuestions = 24, maxHtmlChars = 20_000, maxImages = 3)
        assertEquals(5, heavyChunks.size)
        assertEquals(heavy.map { it.id }, heavyChunks.flatten().map { it.id })
    }

    @Test
    fun tabodyTypoAliasIsNormalizedToTbody() {
        val cleaned = Integrity.sanitizeRichHtml("<table><tabody><tr><td>ERP行</td></tr></tabody></table>")
        assertEquals("<table><tbody><tr><td>ERP行</td></tr></tbody></table>", cleaned)
        assertFalse(cleaned.contains("<tabody"))
    }

    @Test
    fun comprehensiveRichTextEdgeCasesWorkOnAndroid() {
        val mixed = "<meta name=\"Generator\" content=\"Word\"><palign=\"center\"><spanstyle=\"font-weight:bold\">题干</span>" +
            "<input type=\"text\" placeholder=\"填空\" /><audio src=\"a.mp3\"></audio>" +
            "#include <stdio.h> vector<int> 若 a<b 且 b>0</p>"
        val clean = Integrity.sanitizeRichHtml(mixed)
        assertTrue(clean.contains("题干"))
        assertTrue(clean.contains("[填空]"))
        assertTrue(clean.contains("[音频]"))
        assertTrue(clean.contains("&lt;stdio.h&gt;"))
        assertTrue(clean.contains("&lt;int&gt;"))
        assertTrue(clean.contains("a&lt;b 且 b&gt;0"))

        val mathSvg = Integrity.sanitizeRichHtml(
            "<math xmlns=\"http://www.w3.org/1998/Math/MathML\"><mfrac><mi>x</mi><mi>y</mi></mfrac></math>" +
                "<svg viewBox=\"0 0 20 20\"><circle cx=\"10\" cy=\"10\" r=\"8\" onclick=\"evil()\"/></svg>"
        )
        assertTrue(mathSvg.contains("<math") && mathSvg.contains("<svg") && !mathSvg.contains("onclick"))
        var threwSvgScript = false
        try {
            Integrity.sanitizeRichHtml("<svg><script>alert(1)</script></svg>")
        } catch (_: IllegalArgumentException) {
            threwSvgScript = true
        }
        assertTrue(threwSvgScript)
        assertTrue(Integrity.sanitizeRichHtml("<img src=\"//cdn.tsinghua.edu.cn/pic/1.png\" />").contains("https://cdn.tsinghua.edu.cn/pic/1.png"))
    }
}
