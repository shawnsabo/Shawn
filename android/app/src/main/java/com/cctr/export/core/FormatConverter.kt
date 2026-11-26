package com.cctr.export.core

import org.json.JSONArray
import org.json.JSONObject
import org.w3c.dom.Element
import org.w3c.dom.Node
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.nio.charset.StandardCharsets
import java.util.zip.ZipEntry
import java.util.zip.ZipInputStream
import java.util.zip.ZipOutputStream
import javax.xml.parsers.DocumentBuilderFactory

/**
 * 纯 JVM/Kotlin 标准库实现的双向题库格式中心（零外部依赖，兼容 JUnit 本地单测）：
 * 导出：.xlsx（考试宝/磨题帮）、Anki .tsv、.md、.json
 * 导入：.xlsx、.docx、.txt/.md、.json（含超星/雨课堂）、.csv/.tsv
 */
object FormatConverter {
    private val XML_CTRL_RE = Regex("[\\x00-\\x08\\x0B\\x0C\\x0E-\\x1F]")
    private val TAG_BLOCK_RE = Regex("<(?:/?(?:p|div|li|tr|h[1-6]|blockquote)|br\\s*/?)>", RegexOption.IGNORE_CASE)
    private val IMG_TAG_RE = Regex("<img\\b[^>]*>", RegexOption.IGNORE_CASE)
    private val ALL_TAGS_RE = Regex("<[^>]+>")
    private val MULTI_NL_RE = Regex("\\n{3,}")
    private val COL_LETTERS_RE = Regex("^([A-Z]+)")

    private val HEADER_ALIASES = mapOf(
        "题干" to "stem", "题目" to "stem", "题目内容" to "stem", "试题内容" to "stem",
        "问题" to "stem", "stem" to "stem", "question" to "stem", "title" to "stem",
        "content" to "stem", "front" to "stem",
        "题型" to "qtype", "题目类型" to "qtype", "试题类型" to "qtype", "类型" to "qtype",
        "type" to "qtype", "qtype" to "qtype",
        "选项" to "options_blob", "选择项" to "options_blob", "供选项" to "options_blob", "options" to "options_blob",
        "答案" to "answer", "正确答案" to "answer", "标准答案" to "answer", "参考答案" to "answer",
        "answer" to "answer", "back" to "answer",
        "解析" to "analysis", "题目解析" to "analysis", "试题解析" to "analysis", "答案解析" to "analysis",
        "分析" to "analysis", "analysis" to "analysis", "explain" to "analysis", "explanation" to "analysis",
        "章节" to "chapter", "章" to "chapter", "chapter" to "chapter",
        "学科" to "subject", "科目" to "subject", "课程" to "subject", "课程名称" to "subject",
        "source" to "subject", "subject" to "subject"
    )

    private val SECTION_QTYPE_RE = Regex(
        "^(?:#{1,4}\\s*|[一二三四五六七八九十]+[、.．]\\s*|【|\\()(?:.*?(单选|多选|不定项|判断|填空|简答|计算|论述|问答|名词解释|综合).*?)$"
    )
    private val Q_START_RE = Regex(
        "^(?:###\\s*第\\s*\\d+\\s*题(?:\\s*[（(][^）)]*[）)])?\\s*|" +
            "(?:\\[\\s*([^\\]\\n]{1,12})\\s*]\\s*|【\\s*([^】\\n]{1,12})\\s*】\\s*)?" +
            "(?:(?:第\\s*\\d+\\s*题|\\d+)\\s*[.、．)）]\\s*|\\(\\d+\\)\\s*|（\\d+）\\s*))(.*)$"
    )
    private val INLINE_TYPE_RE = Regex("[（(\\[【](单选(?:题)?|多选(?:题)?|不定项(?:选择题)?|判断(?:题)?|填空(?:题)?|简答(?:题)?|计算(?:题)?|问答(?:题)?)[）)\\]】]")
    private val SINGLE_OPT_RE = Regex("^(?:[-*]\\s*)?(?:\\*\\*|__)?([A-H])(?:\\*\\*|__)?\\s*[.、．)）:：]\\s*(.+)$")
    private val ANS_LINE_RE = Regex("^(?:>\\s*)?(?:\\*\\*)?(?:【\\s*(?:正确|标准|参考)?答案\\s*】|(?:正确|标准|参考)?答案)(?:\\*\\*)?\\s*[:：]?\\s*(.*)$")
    private val ANA_LINE_RE = Regex("^(?:>\\s*)?(?:\\*\\*)?(?:【\\s*(?:题目|试题|答案)?解析\\s*】|(?:题目|试题|答案)?解析)(?:\\*\\*)?\\s*[:：]?\\s*(.*)$")

    fun htmlToPlainText(raw: String): String {
        if (raw.isEmpty()) return ""
        var s = raw.replace("\r\n", "\n").replace("\r", "\n")
        val hasImg = IMG_TAG_RE.containsMatchIn(s)
        s = TAG_BLOCK_RE.replace(s, "\n")
        s = IMG_TAG_RE.replace(s, " [图片] ")
        s = ALL_TAGS_RE.replace(s, "")
        s = unescapeHtml(s).replace('\u00A0', ' ')
        val joined = MULTI_NL_RE.replace(
            s.split("\n").joinToString("\n") { it.trim() },
            "\n\n"
        ).trim()
        return if (joined.isEmpty() && hasImg) "[图片]" else joined
    }

    private fun unescapeHtml(s: String): String {
        return s.replace("&nbsp;", " ")
            .replace("&ensp;", " ")
            .replace("&emsp;", " ")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
            .replace("&quot;", "\"")
            .replace("&#39;", "'")
            .replace("&amp;", "&")
    }

    private fun escapeXml(s: String): String {
        val clean = XML_CTRL_RE.replace(s, "")
        return clean.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace("\"", "&quot;")
            .replace("'", "&apos;")
    }

    private fun colIndexToLetters(idx: Int): String {
        val sb = StringBuilder()
        var n = idx + 1
        while (n > 0) {
            val rem = (n - 1) % 26
            sb.append(('A'.code + rem).toChar())
            n = (n - 1) / 26
        }
        return sb.reverse().toString()
    }

    private fun colLettersToIndex(ref: String): Int {
        val m = COL_LETTERS_RE.find(ref.uppercase()) ?: return 0
        var v = 0
        for (ch in m.groupValues[1]) {
            v = v * 26 + (ch.code - 'A'.code + 1)
        }
        return (v - 1).coerceAtLeast(0)
    }

    private fun normalizeChoiceLetters(ans: String): String {
        val plain = htmlToPlainText(ans)
        val letters = Regex("[A-Z]").findAll(plain.uppercase()).map { it.value }.toSortedSet()
        return if (letters.isNotEmpty()) letters.joinToString("") else plain
    }

    // ── Exporters ──────────────────────────────────────────────────────────────

    fun exportToXlsx(questions: List<QuestionItem>, variant: AnswerVariant, title: String): ByteArray {
        Integrity.validateQuestions(questions)
        val headers = listOf("题型", "题干", "选项A", "选项B", "选项C", "选项D", "选项E", "选项F", "选项G", "选项H", "答案", "解析", "章节", "学科")
        val rows = ArrayList<List<String>>(questions.size + 1)
        rows.add(headers)
        val hideAns = (variant == AnswerVariant.WITHOUT_ANSWERS)

        for (q in questions) {
            val optCells = List(8) { idx ->
                if (idx < q.options.size) htmlToPlainText(q.options[idx].html) else ""
            }
            val ansCell = if (hideAns) "" else {
                if (q.isChoice || Integrity.isChoiceQuestion(q.questionType)) {
                    val ltrs = normalizeChoiceLetters(q.answer)
                    ltrs.ifBlank {
                        q.options.mapIndexedNotNull { i, o -> if (o.isTrue) "${'A' + i}" else null }.joinToString("")
                    }
                } else {
                    htmlToPlainText(q.answer)
                }
            }
            val anaCell = if (hideAns) "" else htmlToPlainText(q.analysisHtml)
            rows.add(
                listOf(q.questionType.ifBlank { "未分类题型" }, htmlToPlainText(q.subjectHtml)) +
                    optCells +
                    listOf(
                        ansCell,
                        anaCell,
                        q.chapterName.ifBlank { "未分类章节" },
                        q.subjectName.ifBlank { title.ifBlank { "未分类学科" } }
                    )
            )
        }

        val sheetRows = StringBuilder()
        rows.forEachIndexed { r0, row ->
            val rIdx = r0 + 1
            sheetRows.append("<row r=\"$rIdx\">")
            row.forEachIndexed { cIdx, cell ->
                if (cell.isNotEmpty()) {
                    val ref = "${colIndexToLetters(cIdx)}$rIdx"
                    val styleAttr = if (rIdx == 1) " s=\"1\"" else ""
                    sheetRows.append("<c r=\"$ref\" t=\"inlineStr\"$styleAttr><is><t xml:space=\"preserve\">${escapeXml(cell)}</t></is></c>")
                }
            }
            sheetRows.append("</row>")
        }

        val sheetXml = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>" +
            "<worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">" +
            "<sheetData>$sheetRows</sheetData></worksheet>"
        val contentTypes = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>" +
            "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\">" +
            "<Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/>" +
            "<Default Extension=\"xml\" ContentType=\"application/xml\"/>" +
            "<Override PartName=\"/xl/workbook.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/>" +
            "<Override PartName=\"/xl/worksheets/sheet1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/>" +
            "<Override PartName=\"/xl/styles.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml\"/>" +
            "</Types>"
        val rootRels = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>" +
            "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">" +
            "<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"xl/workbook.xml\"/>" +
            "</Relationships>"
        val workbookXml = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>" +
            "<workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\">" +
            "<sheets><sheet name=\"题库导出\" sheetId=\"1\" r:id=\"rId1\"/></sheets></workbook>"
        val workbookRels = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>" +
            "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">" +
            "<Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" Target=\"worksheets/sheet1.xml\"/>" +
            "<Relationship Id=\"rId2\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles\" Target=\"styles.xml\"/>" +
            "</Relationships>"
        val stylesXml = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>" +
            "<styleSheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\">" +
            "<fonts count=\"2\"><font><sz val=\"11\"/><name val=\"Microsoft YaHei\"/></font>" +
            "<font><b/><sz val=\"11\"/><name val=\"Microsoft YaHei\"/></font></fonts>" +
            "<fills count=\"2\"><fill><patternFill patternType=\"none\"/></fill>" +
            "<fill><patternFill patternType=\"solid\"><fgColor rgb=\"FFF4F3EF\"/></patternFill></fill></fills>" +
            "<borders count=\"1\"><border><left/><right/><top/><bottom/><diagonal/></border></borders>" +
            "<cellStyleXfs count=\"1\"><xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\"/></cellStyleXfs>" +
            "<cellXfs count=\"2\"><xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\" xfId=\"0\"/>" +
            "<xf numFmtId=\"0\" fontId=\"1\" fillId=\"1\" borderId=\"0\" xfId=\"0\" applyFont=\"1\" applyFill=\"1\"/></cellXfs>" +
            "</styleSheet>"

        val baos = ByteArrayOutputStream()
        ZipOutputStream(baos).use { zos ->
            fun put(name: String, content: String) {
                zos.putNextEntry(ZipEntry(name))
                zos.write(content.toByteArray(StandardCharsets.UTF_8))
                zos.closeEntry()
            }
            put("[Content_Types].xml", contentTypes)
            put("_rels/.rels", rootRels)
            put("xl/workbook.xml", workbookXml)
            put("xl/_rels/workbook.rels", workbookRels)
            put("xl/styles.xml", stylesXml)
            put("xl/worksheets/sheet1.xml", sheetXml)
        }
        return baos.toByteArray()
    }

    private fun ankiClean(s: String): String =
        s.replace("\t", "    ").replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>")

    fun exportToAnkiTsv(questions: List<QuestionItem>, title: String): ByteArray {
        Integrity.validateQuestions(questions)
        val deck = title.replace("\t", " ").replace("\n", " ").trim().ifBlank { "题库" }
        val sb = StringBuilder()
        sb.append("#separator:tab\n#html:true\n#deck:").append(deck).append("\n#tags column:4\n")
        for (q in questions) {
            val frontParts = mutableListOf("<b>[${q.questionType}]</b> ${q.subjectHtml}")
            if (q.hasOptions && q.options.isNotEmpty()) {
                q.options.forEachIndexed { idx, opt ->
                    val lbl = if (q.isChoice || Integrity.isChoiceQuestion(q.questionType)) "${'A' + idx}. " else ""
                    frontParts += "$lbl${opt.html}"
                }
            }
            val backParts = mutableListOf("<b>答案：</b>${q.answer}")
            if (q.analysisHtml.isNotBlank()) backParts += "<b>解析：</b>${q.analysisHtml}"
            val tags = listOf(q.subjectName, q.chapterName, q.questionType)
                .map { it.trim().replace(Regex("\\s+"), "_") }
                .filter { it.isNotEmpty() }
                .joinToString(" ")
            sb.append(ankiClean(frontParts.joinToString("<br>"))).append('\t')
                .append(ankiClean(backParts.joinToString("<br>"))).append('\t')
                .append(ankiClean("${q.subjectName} / ${q.chapterName}")).append('\t')
                .append(tags).append('\n')
        }
        return sb.toString().toByteArray(StandardCharsets.UTF_8)
    }

    fun exportToMarkdown(questions: List<QuestionItem>, variant: AnswerVariant, title: String): ByteArray {
        Integrity.validateQuestions(questions)
        val sb = StringBuilder("# ").append(title).append("\n\n")
        var prevGrp: Triple<String, String, String>? = null
        val hideAns = (variant == AnswerVariant.WITHOUT_ANSWERS)
        questions.forEachIndexed { idx, q ->
            val grp = Triple(q.subjectName, q.chapterName, q.questionType)
            if (grp != prevGrp) {
                sb.append("## ${grp.first} / ${grp.second} / ${grp.third}\n\n")
                prevGrp = grp
            }
            sb.append("### 第 ${idx + 1} 题（${q.questionType}）\n\n")
            sb.append(htmlToPlainText(q.subjectHtml)).append("\n\n")
            if (q.hasOptions && q.options.isNotEmpty()) {
                q.options.forEachIndexed { oIdx, opt ->
                    val lbl = if (q.isChoice || Integrity.isChoiceQuestion(q.questionType)) "${'A' + oIdx}. " else "- "
                    val text = htmlToPlainText(opt.html)
                    if (variant == AnswerVariant.WITH_ANSWERS_RED && opt.isTrue) {
                        sb.append("- **$lbl$text** ✓\n")
                    } else {
                        sb.append("- $lbl$text\n")
                    }
                }
                sb.append("\n")
            }
            if (!hideAns) {
                sb.append("> **答案**：${htmlToPlainText(q.answer)}\n")
                val ana = htmlToPlainText(q.analysisHtml)
                if (ana.isNotEmpty()) sb.append("> **解析**：$ana\n")
                sb.append("\n")
            }
        }
        return sb.toString().toByteArray(StandardCharsets.UTF_8)
    }

    fun exportToJson(questions: List<QuestionItem>, variant: AnswerVariant, title: String): ByteArray {
        Integrity.validateQuestions(questions)
        val hideAns = (variant == AnswerVariant.WITHOUT_ANSWERS)
        val arr = JSONArray()
        for (q in questions) {
            val opts = JSONArray()
            for (o in q.options) {
                opts.put(JSONObject().apply {
                    put("is_true", if (hideAns) false else o.isTrue)
                    put("html", o.html)
                })
            }
            arr.put(JSONObject().apply {
                put("id", q.id)
                put("question_type", q.questionType)
                put("subject_html", q.subjectHtml)
                put("answer", if (hideAns) "" else q.answer)
                put("has_options", q.hasOptions)
                put("options", opts)
                put("subject_name", q.subjectName)
                put("chapter_name", q.chapterName)
                put("analysis_html", if (hideAns) "" else q.analysisHtml)
                put("is_choice", q.isChoice)
            })
        }
        val root = JSONObject().apply {
            put("version", 1)
            put("title", title)
            put("variant", variant.key)
            put("questionCount", questions.size)
            put("questions", arr)
        }
        return root.toString(2).toByteArray(StandardCharsets.UTF_8)
    }

    // ── Importers ──────────────────────────────────────────────────────────────

    private fun guessType(rawType: String, hasOptions: Boolean, ans: String, stem: String): String {
        val t = rawType.trim()
        if (t.isNotEmpty()) return t
        if (hasOptions) {
            val ltrs = Regex("[A-H]").findAll(ans.uppercase()).map { it.value }.toSet()
            return if (ltrs.size > 1) "多选题" else "单选题"
        }
        if (ans.trim() in setOf("对", "错", "正确", "错误", "√", "×", "T", "F", "True", "False")) return "判断题"
        if ("___" in stem || "（）" in stem || "(  )" in stem || "（  ）" in stem) return "填空题"
        return "简答题"
    }

    private fun buildImportedQuestion(
        idx: Int,
        stem: String,
        rawType: String,
        optTexts: List<String>,
        ans: String,
        analysis: String = "",
        subjectName: String = "导入题库",
        chapterName: String = "全部题目",
        optFlags: List<Boolean>? = null,
        qid: String? = null
    ): QuestionItem? {
        val cleanStem = stem.trim()
        if (cleanStem.isEmpty()) return null
        val opts = mutableListOf<QuestionOption>()
        optTexts.forEachIndexed { i, txt ->
            val t = txt.trim()
            if (t.isNotEmpty()) {
                val f = optFlags?.getOrNull(i) ?: false
                opts.add(QuestionOption(isTrue = f, html = t))
            }
        }
        var cleanAns = ans.trim()
        if (cleanAns.isEmpty() && opts.any { it.isTrue }) {
            cleanAns = opts.mapIndexedNotNull { i, o -> if (o.isTrue) "${'A' + i}" else null }.joinToString("、")
        }
        val qtype = guessType(rawType, opts.isNotEmpty(), cleanAns, cleanStem)
        val choice = Integrity.isChoiceQuestion(qtype) || (opts.isNotEmpty() && qtype in setOf("单选题", "多选题", "不定项选择题"))
        val markedOpts = if (choice && opts.isNotEmpty()) {
            val ltrs = Regex("[A-Z]").findAll(htmlToPlainText(cleanAns).uppercase()).map { it.value }.toSet()
            if (ltrs.isNotEmpty() || opts.any { it.isTrue }) {
                opts.mapIndexed { i, o -> o.copy(isTrue = o.isTrue || ("${'A' + i}" in ltrs)) }
            } else opts
        } else opts
        if (cleanAns.isEmpty()) cleanAns = "略（原题未附答案）"
        return QuestionItem(
            id = qid ?: "import:$idx",
            questionType = qtype,
            subjectHtml = cleanStem,
            answer = cleanAns,
            hasOptions = markedOpts.isNotEmpty(),
            options = markedOpts,
            subjectName = subjectName.trim().ifBlank { "导入题库" },
            chapterName = chapterName.trim().ifBlank { "全部题目" },
            analysisHtml = analysis.trim(),
            isChoice = choice
        )
    }

    private fun splitOptionBlob(blob: String): List<String> {
        val text = blob.trim()
        if (text.isEmpty()) return emptyList()
        val lines = text.split(Regex("[\\r\\n]+")).map { it.trim() }.filter { it.isNotEmpty() }
        if (lines.size > 1) {
            return lines.map { ln -> SINGLE_OPT_RE.find(ln)?.groupValues?.get(2)?.trim() ?: ln }
        }
        val pipes = text.split(Regex("\\s*\\|\\|\\s*|\\^\\^")).map { it.trim() }.filter { it.isNotEmpty() }
        if (pipes.size > 1) return pipes
        val inline = text.split(Regex("\\s+(?=[A-H][.、．)）:：])")).filter { it.isNotBlank() }
        if (inline.size > 1) {
            return inline.map { p -> SINGLE_OPT_RE.find(p.trim())?.groupValues?.get(2)?.trim() ?: p.trim() }
        }
        return listOf(text)
    }

    private fun rowsToQuestions(rows: List<List<String>>, title: String): List<QuestionItem> {
        if (rows.isEmpty()) return emptyList()
        val header = rows[0].map { it.trim() }
        val colMap = mutableMapOf<String, Int>()
        val optionCols = mutableListOf<Pair<String, Int>>()

        header.forEachIndexed { idx, rawCol ->
            val norm = rawCol.replace(Regex("[\\s_\\-*（）()]+"), "").lowercase()
            val optM = Regex("^(?:选项|option|choice)?([a-z])$").matchEntire(norm)
            if (optM != null && norm !in HEADER_ALIASES) {
                optionCols.add(optM.groupValues[1].uppercase() to idx)
            } else {
                val mapped = HEADER_ALIASES[rawCol] ?: HEADER_ALIASES[norm]
                if (mapped != null && mapped !in colMap) colMap[mapped] = idx
            }
        }
        optionCols.sortBy { it.first }
        val hasHeader = ("stem" in colMap || "answer" in colMap || optionCols.isNotEmpty())
        val dataStart = if (hasHeader) 1 else 0
        if (!hasHeader) {
            colMap["qtype"] = 0
            colMap["stem"] = 1
            colMap["answer"] = 6
            colMap["analysis"] = 7
            optionCols.addAll(listOf("A" to 2, "B" to 3, "C" to 4, "D" to 5))
        }

        val out = mutableListOf<QuestionItem>()
        for (rIdx in dataStart until rows.size) {
            val row = rows[rIdx]
            fun cell(key: String): String {
                val ci = colMap[key] ?: return ""
                return if (ci < row.size) row[ci].trim() else ""
            }
            val stem = cell("stem")
            val ans = cell("answer")
            if (stem.isEmpty() && ans.isEmpty()) continue
            var opts = optionCols.mapNotNull { (_, ci) -> row.getOrNull(ci)?.trim()?.takeIf { it.isNotEmpty() } }
            if (opts.isEmpty() && "options_blob" in colMap) {
                opts = splitOptionBlob(cell("options_blob"))
            }
            buildImportedQuestion(
                idx = out.size + 1,
                stem = stem,
                rawType = cell("qtype"),
                optTexts = opts,
                ans = ans,
                analysis = cell("analysis"),
                subjectName = cell("subject").ifBlank { title },
                chapterName = cell("chapter").ifBlank { "导入章节" }
            )?.let { out.add(it) }
        }
        return out
    }

    fun importXlsxBytes(bytes: ByteArray, title: String): List<QuestionItem> {
        val entries = HashMap<String, ByteArray>()
        ZipInputStream(ByteArrayInputStream(bytes)).use { zis ->
            var entry = zis.nextEntry
            while (entry != null) {
                if (!entry.isDirectory) {
                    entries[entry.name] = zis.readBytes()
                }
                entry = zis.nextEntry
            }
        }
        val dbf = DocumentBuilderFactory.newInstance().apply { isNamespaceAware = true }
        val sharedStrings = mutableListOf<String>()
        entries["xl/sharedStrings.xml"]?.let { ssBytes ->
            val doc = dbf.newDocumentBuilder().parse(ByteArrayInputStream(ssBytes))
            val siNodes = doc.getElementsByTagNameNS("*", "si")
            for (i in 0 until siNodes.length) {
                val el = siNodes.item(i) as? Element ?: continue
                val tNodes = el.getElementsByTagNameNS("*", "t")
                val sb = StringBuilder()
                for (j in 0 until tNodes.length) sb.append(tNodes.item(j).textContent.orEmpty())
                sharedStrings.add(sb.toString())
            }
        }
        val sheetKey = entries.keys.filter { it.startsWith("xl/worksheets/sheet") && it.endsWith(".xml") }.sorted().firstOrNull()
            ?: return emptyList()
        val wsDoc = dbf.newDocumentBuilder().parse(ByteArrayInputStream(entries[sheetKey]!!))
        val rowNodes = wsDoc.getElementsByTagNameNS("*", "row")
        val rows = mutableListOf<List<String>>()
        for (i in 0 until rowNodes.length) {
            val rowEl = rowNodes.item(i) as? Element ?: continue
            val map = mutableMapOf<Int, String>()
            var maxCol = -1
            var cursor = 0
            val children = rowEl.childNodes
            for (j in 0 until children.length) {
                val cEl = children.item(j) as? Element ?: continue
                if (cEl.localName != "c") continue
                val ref = cEl.getAttribute("r")
                val cIdx = if (ref.isNotEmpty()) colLettersToIndex(ref) else cursor
                cursor = cIdx + 1
                if (cIdx > maxCol) maxCol = cIdx
                val cType = cEl.getAttribute("t")
                val text = when (cType) {
                    "inlineStr" -> {
                        val tNodes = cEl.getElementsByTagNameNS("*", "t")
                        val sb = StringBuilder()
                        for (k in 0 until tNodes.length) sb.append(tNodes.item(k).textContent.orEmpty())
                        sb.toString()
                    }
                    else -> {
                        val vNodes = cEl.getElementsByTagNameNS("*", "v")
                        val rawV = if (vNodes.length > 0) vNodes.item(0).textContent.orEmpty() else ""
                        if (cType == "s") {
                            rawV.toIntOrNull()?.let { sharedStrings.getOrNull(it) }.orEmpty()
                        } else rawV
                    }
                }
                map[cIdx] = text
            }
            if (maxCol >= 0) {
                rows.add(List(maxCol + 1) { idx -> map[idx].orEmpty() })
            }
        }
        return rowsToQuestions(rows, title)
    }

    private fun docxBytesToText(bytes: ByteArray): String {
        var docXml: ByteArray? = null
        ZipInputStream(ByteArrayInputStream(bytes)).use { zis ->
            var entry = zis.nextEntry
            while (entry != null) {
                if (entry.name == "word/document.xml") {
                    docXml = zis.readBytes()
                    break
                }
                entry = zis.nextEntry
            }
        }
        val xmlBytes = docXml ?: return ""
        val dbf = DocumentBuilderFactory.newInstance().apply { isNamespaceAware = true }
        val doc = dbf.newDocumentBuilder().parse(ByteArrayInputStream(xmlBytes))
        val pNodes = doc.getElementsByTagNameNS("*", "p")
        val lines = mutableListOf<String>()

        fun collectText(node: Node, sb: StringBuilder) {
            when (node.localName) {
                "t" -> sb.append(node.textContent.orEmpty())
                "tab" -> sb.append('\t')
                "br", "cr" -> sb.append('\n')
                else -> {
                    val ch = node.childNodes
                    for (k in 0 until ch.length) collectText(ch.item(k), sb)
                }
            }
        }

        for (i in 0 until pNodes.length) {
            val sb = StringBuilder()
            collectText(pNodes.item(i), sb)
            val txt = sb.toString().trim()
            if (txt.isNotEmpty()) lines.add(txt)
        }
        return lines.joinToString("\n")
    }

    fun parseStructuredTextQuestions(text: String, title: String = "文档题库"): List<QuestionItem> {
        val lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        val out = mutableListOf<QuestionItem>()
        var currentChapter = "全部题目"
        var currentSectionType = ""
        val curStem = mutableListOf<String>()
        var curType = ""
        val curOpts = mutableListOf<String>()
        val curFlags = mutableListOf<Boolean>()
        val curAns = mutableListOf<String>()
        val curAna = mutableListOf<String>()
        var mode = ""

        fun flush() {
            buildImportedQuestion(
                idx = out.size + 1,
                stem = curStem.joinToString("\n"),
                rawType = curType.ifBlank { currentSectionType },
                optTexts = curOpts,
                ans = curAns.joinToString("\n"),
                analysis = curAna.joinToString("\n"),
                subjectName = title,
                chapterName = currentChapter,
                optFlags = curFlags
            )?.let { out.add(it) }
            curStem.clear(); curType = ""; curOpts.clear(); curFlags.clear()
            curAns.clear(); curAna.clear(); mode = ""
        }

        for (raw in lines) {
            val ln = raw.trim()
            if (ln.isEmpty()) continue
            if (ln.startsWith("## ")) {
                flush()
                val parts = ln.removePrefix("## ").split("/").map { it.trim() }.filter { it.isNotEmpty() }
                if (parts.size >= 2) currentChapter = parts[1]
                if (parts.size >= 3) currentSectionType = parts[2]
                continue
            }
            if (ln.startsWith("# ") && out.isEmpty() && curStem.isEmpty()) continue

            val secM = SECTION_QTYPE_RE.matchEntire(ln)
            if (secM != null && ln.length <= 32 && Q_START_RE.matchEntire(ln) == null) {
                flush()
                val rawT = secM.groupValues[1]
                currentSectionType = if (rawT.endsWith("题")) rawT else "${rawT}题"
                continue
            }

            val ansM = ANS_LINE_RE.matchEntire(ln)
            if (ansM != null && (curStem.isNotEmpty() || curOpts.isNotEmpty())) {
                mode = "ans"
                curAns.add(ansM.groupValues[1].trim())
                continue
            }
            val anaM = ANA_LINE_RE.matchEntire(ln)
            if (anaM != null && (curStem.isNotEmpty() || curAns.isNotEmpty())) {
                mode = "ana"
                curAna.add(anaM.groupValues[1].trim())
                continue
            }
            val optM = SINGLE_OPT_RE.matchEntire(ln)
            if (optM != null && (curStem.isNotEmpty() || curOpts.isNotEmpty())) {
                mode = "opt"
                val chunks = ln.split(Regex("\\s{2,}(?=[A-H][.、．)）:：])|\\t+(?=[A-H][.、．)）:：])"))
                for (ch in chunks) {
                    val chS = ch.trim()
                    var marked = chS.endsWith("✓") || chS.startsWith("- **")
                    var chClean = chS.removeSuffix("✓").trim()
                    if (chClean.startsWith("**") && chClean.endsWith("**") && chClean.length > 4) {
                        chClean = chClean.substring(2, chClean.length - 2).trim()
                        marked = true
                    }
                    val sm = SINGLE_OPT_RE.matchEntire(chClean)
                    curOpts.add((sm?.groupValues?.get(2) ?: chClean).trim())
                    curFlags.add(marked)
                }
                continue
            }
            val qM = Q_START_RE.matchEntire(ln)
            if (qM != null) {
                if (curStem.isNotEmpty()) flush()
                var body = qM.groupValues[3].trim()
                var tag = qM.groupValues[1].ifEmpty { qM.groupValues[2] }.trim()
                val inT = INLINE_TYPE_RE.find(body)
                if (tag.isEmpty() && inT != null) {
                    tag = inT.groupValues[1]
                    body = INLINE_TYPE_RE.replaceFirst(body, "").trim()
                }
                val inAns = Regex("[（(\\[【](?:答案|正确答案)\\s*[:：]\\s*([^）)\\]】]+)[）)\\]】]\\s*$").find(body)
                if (inAns != null) {
                    curAns.add(inAns.groupValues[1].trim())
                    body = body.substring(0, inAns.range.first).trim()
                }
                curType = tag
                curStem.add(body.ifEmpty { ln })
                mode = "stem"
                continue
            }
            when (mode) {
                "ans" -> curAns.add(ln)
                "ana" -> curAna.add(ln)
                "opt" -> if (curOpts.isNotEmpty()) curOpts[curOpts.lastIndex] = (curOpts.last() + "\n" + ln).trim()
                else -> { curStem.add(ln); mode = "stem" }
            }
        }
        flush()
        return out
    }

    fun parseJsonQuestions(rawJson: String, title: String = "JSON题库"): Pair<String, List<QuestionItem>> {
        val trimmed = rawJson.trim().removePrefix("\uFEFF")
        var docTitle = title
        val items = when {
            trimmed.startsWith("[") -> JSONArray(trimmed)
            else -> {
                val obj = JSONObject(trimmed)
                docTitle = obj.optString("title").ifBlank { obj.optString("name") }.ifBlank { title }
                val dataObj = obj.optJSONObject("data")
                if (dataObj != null) {
                    docTitle = dataObj.optString("name").ifBlank { dataObj.optString("title") }.ifBlank { docTitle }
                    dataObj.optJSONArray("problems") ?: dataObj.optJSONArray("questions") ?: JSONArray()
                } else {
                    obj.optJSONArray("questions") ?: obj.optJSONArray("problems")
                        ?: obj.optJSONArray("items") ?: obj.optJSONArray("data") ?: JSONArray()
                }
            }
        }

        val out = mutableListOf<QuestionItem>()
        for (i in 0 until items.length()) {
            val it = items.optJSONObject(i) ?: continue
            if (it.has("subject_html")) {
                val rawOpts = it.optJSONArray("options")
                val opts = mutableListOf<QuestionOption>()
                if (rawOpts != null) {
                    for (k in 0 until rawOpts.length()) {
                        val o = rawOpts.optJSONObject(k) ?: continue
                        val h = o.optString("html")
                        if (h.isNotBlank()) opts.add(QuestionOption(o.optBoolean("is_true", false), h))
                    }
                }
                val qtype = it.optString("question_type", "未分类题型")
                out.add(
                    QuestionItem(
                        id = it.optString("id", "json:${i + 1}"),
                        questionType = qtype,
                        subjectHtml = it.optString("subject_html"),
                        answer = it.optString("answer").ifBlank { "略（原题未附答案）" },
                        hasOptions = it.optBoolean("has_options", opts.isNotEmpty()),
                        options = opts,
                        subjectName = it.optString("subject_name", docTitle),
                        chapterName = it.optString("chapter_name", "全部题目"),
                        analysisHtml = it.optString("analysis_html", ""),
                        isChoice = it.optBoolean("is_choice", Integrity.isChoiceQuestion(qtype))
                    )
                )
                continue
            }

            val stem = it.optString("Body").ifBlank { it.optString("body") }
                .ifBlank { it.optString("question") }.ifBlank { it.optString("stem") }
                .ifBlank { it.optString("title") }.ifBlank { it.optString("content") }
            var rawType = it.optString("TypeText").ifBlank { it.optString("typeText") }
                .ifBlank { it.optString("questionType") }.ifBlank { it.optString("qtype") }
                .ifBlank { it.optString("type") }
            if (rawType in setOf("0", "1", "2", "3", "4", "5", "6")) {
                rawType = mapOf(
                    "0" to "单选题", "1" to "单选题", "2" to "多选题",
                    "3" to "多选题", "4" to "判断题", "5" to "填空题", "6" to "简答题"
                )[rawType] ?: rawType
            }

            val optTexts = mutableListOf<String>()
            val optFlags = mutableListOf<Boolean>()
            val optArr = it.optJSONArray("Options") ?: it.optJSONArray("options") ?: it.optJSONArray("choices")
            val optObj = it.optJSONObject("Options") ?: it.optJSONObject("options")
            if (optArr != null) {
                for (k in 0 until optArr.length()) {
                    val oObj = optArr.optJSONObject(k)
                    if (oObj != null) {
                        val t = oObj.optString("value").ifBlank { oObj.optString("name") }
                            .ifBlank { oObj.optString("text") }.ifBlank { oObj.optString("html") }
                            .ifBlank { oObj.optString("content") }
                        if (t.isNotBlank()) {
                            optTexts.add(t)
                            optFlags.add(
                                oObj.optBoolean("isCorrect", false) ||
                                    oObj.optBoolean("is_true", false) ||
                                    oObj.optBoolean("isAnswer", false) ||
                                    oObj.optBoolean("correct", false)
                            )
                        }
                    } else {
                        val s = optArr.optString(k).trim()
                        if (s.isNotEmpty()) {
                            optTexts.add(s)
                            optFlags.add(false)
                        }
                    }
                }
            } else if (optObj != null) {
                val keys = optObj.keys().asSequence().toList().sorted()
                for (k in keys) {
                    optTexts.add(optObj.optString(k))
                    optFlags.add(false)
                }
            }

            val ansAny = it.opt("Answer") ?: it.opt("answer") ?: it.opt("correctAnswer") ?: it.opt("rightAnswer")
            val ansStr = when (ansAny) {
                is JSONArray -> (0 until ansAny.length()).map { idx -> ansAny.optString(idx) }.joinToString("、")
                is JSONObject -> ansAny.keys().asSequence().map { k -> "$k: ${ansAny.optString(k)}" }.joinToString("；")
                else -> ansAny?.toString().orEmpty()
            }
            val ana = it.optString("Remark").ifBlank { it.optString("analysis") }
                .ifBlank { it.optString("explain") }.ifBlank { it.optString("explanation") }
            val chap = it.optString("chapter").ifBlank { it.optString("chapterName") }.ifBlank { "导入章节" }
            val subj = it.optString("subject").ifBlank { it.optString("courseName") }.ifBlank { docTitle }

            buildImportedQuestion(
                idx = out.size + 1,
                stem = stem,
                rawType = rawType,
                optTexts = optTexts,
                ans = ansStr,
                analysis = ana,
                subjectName = subj,
                chapterName = chap,
                optFlags = optFlags,
                qid = it.optString("id").ifBlank { it.optString("problem_id") }.ifBlank { "json:${i + 1}" }
            )?.let { out.add(it) }
        }
        return docTitle to out
    }

    private fun parseDelimitedLine(line: String, delim: Char): List<String> {
        if (delim == '\t') return line.split('\t')
        val out = mutableListOf<String>()
        val cur = StringBuilder()
        var inQuotes = false
        var i = 0
        while (i < line.length) {
            val c = line[i]
            if (inQuotes) {
                if (c == '"' && i + 1 < line.length && line[i + 1] == '"') {
                    cur.append('"'); i += 2; continue
                } else if (c == '"') {
                    inQuotes = false
                } else cur.append(c)
            } else {
                when (c) {
                    '"' -> inQuotes = true
                    delim -> { out.add(cur.toString()); cur.clear() }
                    else -> cur.append(c)
                }
            }
            i++
        }
        out.add(cur.toString())
        return out
    }

    private fun importDelimitedText(raw: String, title: String, delim: Char): List<QuestionItem> {
        val allLines = raw.removePrefix("\uFEFF").replace("\r\n", "\n").replace("\r", "\n").split("\n")
        val filtered = allLines.filter { !it.startsWith("#") && it.isNotBlank() }
        if (filtered.isEmpty()) return emptyList()
        val rows = filtered.map { parseDelimitedLine(it, delim) }
        if (allLines.firstOrNull()?.startsWith("#separator:tab") == true && rows[0].size >= 2) {
            return rows.mapIndexedNotNull { idx, r ->
                buildImportedQuestion(
                    idx = idx + 1,
                    stem = r.getOrNull(0).orEmpty(),
                    rawType = "卡片",
                    optTexts = emptyList(),
                    ans = r.getOrNull(1).orEmpty(),
                    subjectName = r.getOrNull(2).orEmpty().ifBlank { title },
                    chapterName = "Anki 卡片"
                )
            }
        }
        return rowsToQuestions(rows, title)
    }

    fun importFromBytes(fileName: String, bytes: ByteArray): Pair<String, List<QuestionItem>> {
        val dot = fileName.lastIndexOf('.')
        val stem = if (dot > 0) fileName.substring(0, dot) else fileName
        val ext = if (dot >= 0) fileName.substring(dot + 1).lowercase() else "txt"
        val title = stem.ifBlank { "导入题库" }
        var outTitle = title

        val items = when (ext) {
            "xlsx" -> importXlsxBytes(bytes, title)
            "docx" -> parseStructuredTextQuestions(docxBytesToText(bytes), title)
            "json" -> {
                val (t, qs) = parseJsonQuestions(String(bytes, StandardCharsets.UTF_8), title)
                outTitle = t
                qs
            }
            "csv", "tsv" -> {
                val raw = String(bytes, StandardCharsets.UTF_8)
                val delim = if (ext == "tsv" || raw.startsWith("#separator:tab")) '\t' else ','
                importDelimitedText(raw, title, delim)
            }
            "txt", "md", "markdown" -> parseStructuredTextQuestions(String(bytes, StandardCharsets.UTF_8), title)
            else -> throw IllegalArgumentException("暂不支持的文件格式 .$ext（支持 xlsx/docx/txt/md/json/csv/tsv）")
        }
        require(items.isNotEmpty()) { "未能从「$fileName」识别到有效题目，请核对格式" }
        Integrity.validateQuestions(items)
        return outTitle to items
    }
}
