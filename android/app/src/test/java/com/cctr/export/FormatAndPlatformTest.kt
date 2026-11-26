package com.cctr.export

import com.cctr.export.core.AnswerVariant
import com.cctr.export.core.FormatConverter
import com.cctr.export.core.QuestionItem
import com.cctr.export.core.QuestionOption
import com.cctr.export.core.WebPlatformExtractor
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

class FormatAndPlatformTest {
    private fun sampleQuestions(): List<QuestionItem> = listOf(
        QuestionItem(
            id = "t:1",
            questionType = "单选题",
            subjectHtml = "<p>香农公式带宽与信道容量成什么关系？</p>",
            answer = "A",
            hasOptions = true,
            options = listOf(
                QuestionOption(true, "正比"),
                QuestionOption(false, "反比")
            ),
            subjectName = "通信原理",
            chapterName = "第一章",
            analysisHtml = "<p>C = B log2(1 + S/N)</p>",
            isChoice = true
        ),
        QuestionItem(
            id = "t:2",
            questionType = "多选题",
            subjectHtml = "<p>下列属于数字调制的有？</p>",
            answer = "A、C",
            hasOptions = true,
            options = listOf(
                QuestionOption(true, "ASK"),
                QuestionOption(false, "FM"),
                QuestionOption(true, "PSK")
            ),
            subjectName = "通信原理",
            chapterName = "第三章",
            analysisHtml = "",
            isChoice = true
        )
    )

    @Test
    fun xlsxRoundTripPreservesQuestionsAndOptions() {
        val qs = sampleQuestions()
        val xlsxBytes = FormatConverter.exportToXlsx(qs, AnswerVariant.WITH_ANSWERS_RED, "通信原理")
        assertTrue(xlsxBytes.size > 200)

        val (title, imported) = FormatConverter.importFromBytes("通信原理题库.xlsx", xlsxBytes)
        assertEquals("通信原理题库", title)
        assertEquals(2, imported.size)
        assertEquals("单选题", imported[0].questionType)
        assertTrue(imported[0].options[0].isTrue)
        assertEquals("AC", imported[1].answer)
        assertTrue(imported[1].options[2].isTrue)

        val blankBytes = FormatConverter.exportToXlsx(qs, AnswerVariant.WITHOUT_ANSWERS, "空白卷")
        val (_, blankImported) = FormatConverter.importFromBytes("blank.xlsx", blankBytes)
        assertEquals("略（原题未附答案）", blankImported[0].answer)
    }

    @Test
    fun docxMarkdownAndAnkiTsvImportsWork() {
        val docXml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
            <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              <w:body>
                <w:p><w:r><w:t>一、单选题</w:t></w:r></w:p>
                <w:p><w:r><w:t>1. HTTP 默认端口是？</w:t></w:r></w:p>
                <w:p><w:r><w:t>A. 80</w:t></w:r></w:p>
                <w:p><w:r><w:t>B. 443</w:t></w:r></w:p>
                <w:p><w:r><w:t>答案：A</w:t></w:r></w:p>
                <w:p><w:r><w:t>解析：HTTPS 默认 443</w:t></w:r></w:p>
              </w:body>
            </w:document>""".trimIndent()
        val baos = ByteArrayOutputStream()
        ZipOutputStream(baos).use { zos ->
            zos.putNextEntry(ZipEntry("word/document.xml"))
            zos.write(docXml.toByteArray(Charsets.UTF_8))
            zos.closeEntry()
        }
        val (_, docxQs) = FormatConverter.importFromBytes("test.docx", baos.toByteArray())
        assertEquals(1, docxQs.size)
        assertTrue(docxQs[0].options[0].isTrue)

        val mdBytes = FormatConverter.exportToMarkdown(sampleQuestions(), AnswerVariant.WITH_ANSWERS_RED, "讲义")
        val (_, mdQs) = FormatConverter.importFromBytes("notes.md", mdBytes)
        assertEquals(2, mdQs.size)

        val tsvBytes = FormatConverter.exportToAnkiTsv(sampleQuestions(), "卡片包")
        assertTrue(String(tsvBytes, Charsets.UTF_8).contains("#separator:tab"))
        val (_, tsvQs) = FormatConverter.importFromBytes("deck.tsv", tsvBytes)
        assertEquals(2, tsvQs.size)
    }

    @Test
    fun chaoxingAndYuketangJsonImportsWork() {
        val yktJson = """
            {
              "code": 0,
              "data": {
                "name": "雨课堂章节练习",
                "problems": [
                  {
                    "ProblemID": 501,
                    "Type": 0,
                    "Body": "<p>TCP 建立连接需要几次握手？</p>",
                    "Options": [{"key": "A", "value": "两次"}, {"key": "B", "value": "三次"}],
                    "Answer": ["B"],
                    "Remark": "三次握手"
                  }
                ]
              }
            }
        """.trimIndent()
        val (title, qs) = FormatConverter.importFromBytes("yuketang.json", yktJson.toByteArray(Charsets.UTF_8))
        assertEquals("雨课堂章节练习", title)
        assertEquals(1, qs.size)
        assertEquals("单选题", qs[0].questionType)
        assertTrue(qs[0].options[1].isTrue)
    }

    @Test
    fun webPlatformExtractorDecryptsGlyphsAndSanitizesSafeDomains() {
        // 构造最小 SFNT cmap Format 4
        val cps = listOf(0x4E2D, 0xE123, 0xFFFF)
        val segCountX2 = cps.size * 2
        val subLen = 14 + segCountX2 * 2 + 2
        val totalLen = 12 + 16 + 12 + subLen
        val buf = ByteBuffer.allocate(totalLen).order(ByteOrder.BIG_ENDIAN)
        buf.putInt(0x00010000); buf.putShort(1); buf.putShort(16); buf.putShort(0); buf.putShort(0)
        buf.put("cmap".toByteArray(Charsets.US_ASCII)); buf.putInt(0); buf.putInt(28); buf.putInt(12 + subLen)
        buf.putShort(0); buf.putShort(1); buf.putShort(3); buf.putShort(1); buf.putInt(12)
        buf.putShort(4); buf.putShort(subLen.toShort()); buf.putShort(0); buf.putShort(segCountX2.toShort())
        buf.putShort(0); buf.putShort(0); buf.putShort(0)
        cps.forEach { buf.putShort(it.toShort()) }
        buf.putShort(0)
        cps.forEach { buf.putShort(it.toShort()) }

        val parsed = WebPlatformExtractor.parseTtfCmapCodepoints(buf.array())
        assertTrue(0x4E2D in parsed && 0xE123 in parsed)

        val mapped = WebPlatformExtractor.applyGlyphMapToHtml(
            """<p>\uE001\uE002</p><img src="https://p.ananas.chaoxing.com/x.png" />""".replace("\\uE001", "\uE001").replace("\\uE002", "\uE002"),
            mapOf("\uE001" to "信", "\uE002" to "号")
        )
        assertEquals("""<p>信号</p><img src="https://p.ananas.chaoxing.com/x.png" />""", mapped)

        val capJson = """
            {
              "ok": true,
              "title": "学习通随堂测",
              "sourceLabel": "超星学习通",
              "secretGlyphs": [{"char": "\uE001", "pngBase64": "AQID"}],
              "items": [
                {
                  "id": "cx:1",
                  "questionType": "单选题",
                  "stemHtml": "<p>\uE001道容量公式</p><img src='https://qn-st0.yuketang.cn/eq.png' />",
                  "options": [{"isTrue": false, "html": "A. 带宽"}],
                  "answerHtml": "A",
                  "analysisHtml": ""
                }
              ]
            }
        """.trimIndent()
        val (title, items) = WebPlatformExtractor.parseCapturedPayload(capJson) { "信" }
        assertEquals("学习通随堂测", title)
        assertTrue(items[0].subjectHtml.contains("信道容量公式"))
        assertFalse(items[0].subjectHtml.contains("\uE001"))

        var blocked = false
        try {
            WebPlatformExtractor.parseCapturedPayload(
                """{"ok":true,"title":"evil","items":[{"id":"1","questionType":"单选题","stemHtml":"<img src='https://evil.com/x.png'/>","options":[],"answerHtml":"A"}]}"""
            ) { "" }
        } catch (_: IllegalArgumentException) {
            blocked = true
        }
        assertTrue(blocked)
    }
}
