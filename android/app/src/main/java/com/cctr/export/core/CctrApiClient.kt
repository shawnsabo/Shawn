package com.cctr.export.core

import android.util.Base64
import okhttp3.Cookie
import okhttp3.CookieJar
import okhttp3.FormBody
import okhttp3.HttpUrl
import okhttp3.OkHttpClient
import okhttp3.Request
import org.json.JSONObject
import java.security.KeyFactory
import java.security.spec.X509EncodedKeySpec
import java.util.concurrent.TimeUnit
import javax.crypto.Cipher

class CctrApiClient {
    companion object {
        private const val BASE_URL = "https://api.cctrcloud.net/mobile/index.php"
        private const val RSA_PUB_B64 =
            "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDO3r40irpueBqKoCSh01YG8qhX" +
            "XH10pgZje98q7ZvjOWad/da8Eejrbs3uyNOEwYmFJckUA8X0MiGOr3Mlv1VAXTA9" +
            "T9YxbBObkLNUMj2VWLbjgZNiDzZwqeprLVvIbQSLSEUseVf/EmdCeEgMOzxnahsK" +
            "KIs7u+iN13xPFBY0kwIDAQAB"
    }

    private val cookieStore = HashMap<String, MutableList<Cookie>>()

    private val http = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(45, TimeUnit.SECONDS)
        .cookieJar(object : CookieJar {
            override fun saveFromResponse(url: HttpUrl, cookies: List<Cookie>) {
                val list = cookieStore.getOrPut(url.host) { mutableListOf() }
                for (c in cookies) {
                    list.removeAll { it.name == c.name }
                    list.add(c)
                }
            }

            override fun loadForRequest(url: HttpUrl): List<Cookie> {
                val now = System.currentTimeMillis()
                return cookieStore[url.host]?.filter { it.expiresAt >= now } ?: emptyList()
            }
        })
        .build()

    var authKey: String = ""
        private set

    fun fetchCaptcha(): ByteArray {
        val req = Request.Builder()
            .url("$BASE_URL?act=seccode&op=makecode&t=${System.currentTimeMillis()}")
            .header("User-Agent", "Mozilla/5.0")
            .get()
            .build()
        http.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful) error("获取验证码失败（HTTP ${resp.code}）")
            val bytes = resp.body?.bytes() ?: ByteArray(0)
            require(Integrity.sniffImageMime(bytes) != null) { "验证码接口未返回有效图片" }
            return bytes
        }
    }

    fun login(schoolCode: String, username: String, password: String, captcha: String): String {
        val schoolJson = postForm(
            "$BASE_URL?act=login&op=getschoolData",
            mapOf("number" to schoolCode.trim())
        )
        val realSchoolId = schoolJson.getJSONObject("datas").getString("ID")

        val loginJson = postForm(
            "$BASE_URL?act=login",
            mapOf(
                "username" to username.trim(),
                "password" to rsaEncrypt(password),
                "schoolid" to realSchoolId,
                "client" to "web",
                "captcha" to captcha.trim()
            )
        )
        authKey = loginJson.getJSONObject("datas").getString("key")
        return authKey
    }

    fun getPracticeList(): List<PracticeItem> {
        val d = postForm(
            "$BASE_URL?act=studentpracticeapi&op=getPractiseCourseList",
            mapOf("key" to authKey)
        )
        val arr = d.getJSONArray("datas")
        return List(arr.length()) { i ->
            val o = arr.getJSONObject(i)
            val rawCount = o.optString("questioncount", o.optString("studentpractisequestioncount", ""))
            PracticeItem(
                id = o.optInt("id", o.optInt("ID", 0)),
                courseId = o.optString("courseid", o.optString("courseId", "0")),
                practiseId = o.optString("practiseid", o.optString("practiseId", "")),
                teacherId = o.optString("teacherid", o.optString("teacherId", "")),
                lessonName = o.optString("lessonname", o.optString("lessonName", "")),
                practiceName = o.optString("practicename", o.optString("practiceName", "")),
                teacherName = o.optString("teachernumber", ""),
                finishTime = o.optString("finishtime", ""),
                questionCount = rawCount.toIntOrNull()
            )
        }
    }

    fun getChapterAndQuestionTypes(practice: PracticeItem): Pair<List<ChapterItem>, List<QuestionTypeItem>> {
        val d = postForm(
            "$BASE_URL?act=studentpracticeapi&op=getChapterListAndQuestionTypeList",
            mapOf(
                "key" to authKey,
                "courseid" to practice.courseId,
                "practiseid" to practice.practiseId
            )
        )
        val datas = d.getJSONObject("datas")
        val chArr = datas.optJSONArray("chapterList")
        val qtArr = datas.optJSONArray("questionTypeList")
        val chapters = if (chArr != null) List(chArr.length()) { i ->
            val o = chArr.getJSONObject(i)
            ChapterItem(o.optString("id"), o.optString("courseid"), o.optString("name"))
        } else emptyList()
        val qtypes = if (qtArr != null) List(qtArr.length()) { i ->
            val o = qtArr.getJSONObject(i)
            QuestionTypeItem(o.optString("questiontypeid"), o.optString("id"), o.optString("cname"))
        } else emptyList()
        return chapters to qtypes
    }

    fun queryQuestions(
        practice: PracticeItem,
        chapters: List<ChapterItem> = emptyList(),
        questionTypes: List<QuestionTypeItem> = emptyList(),
        practicedOnly: Boolean = false
    ): List<QuestionItem> {
        val (catChapters, catTypes) = runCatching { getChapterAndQuestionTypes(practice) }
            .getOrElse { emptyList<ChapterItem>() to emptyList<QuestionTypeItem>() }
        val chapterMap = catChapters.associate { it.id to it.name }
        val chapterOrder = catChapters.mapIndexed { idx, c -> c.id to idx }.toMap()
        val typeMap = catTypes.associate { (it.questionTypeId.ifBlank { it.id }) to it.name }
        val typeOrder = catTypes.mapIndexed { idx, t -> (t.questionTypeId.ifBlank { t.id }) to idx }.toMap()

        val practiceTypes = if (practicedOnly) listOf(1) else listOf(0, 1)
        val rawAll = mutableListOf<JSONObject>()
        val seenIds = HashSet<String>()
        var observedReportedCount: Int? = null

        for (pt in practiceTypes) {
            val (firstRaw, split, reportedCount) = fetchPage(practice, 1, 100, chapters, questionTypes, pt, "")
            if (reportedCount != null && observedReportedCount == null) {
                observedReportedCount = reportedCount
            }
            if (firstRaw.isEmpty() && split.isEmpty()) continue

            val bucket = mutableListOf<JSONObject>().apply { addAll(firstRaw) }
            val splitCounts = split.filter { it.isNotBlank() }
                .map { s -> s.split(",").count { it.isNotBlank() } }
            val expectedBucketCount = if (splitCounts.isNotEmpty()) splitCounts.sum() else null

            if (split.isEmpty() && practiceTypes.size == 1 && reportedCount != null && firstRaw.size < reportedCount) {
                error("平台未提供完整分页游标（${firstRaw.size}/$reportedCount）")
            }
            for (i in 1 until split.size) {
                val cursor = split[i]
                require(cursor.isNotBlank()) { "第 ${i + 1} 页游标无效" }
                val (pageRaw, _, _) = fetchPage(practice, i + 1, 100, chapters, questionTypes, pt, cursor)
                require(pageRaw.isNotEmpty()) { "第 ${i + 1} 页为空，无法确认完整" }
                bucket.addAll(pageRaw)
            }
            val bucketIds = HashSet<String>()
            for (item in bucket) {
                val qid = item.optString("questionid", "").trim()
                require(qid.isNotBlank() && bucketIds.add(qid)) { "题目 ID 缺失或同页内重复：$qid" }
            }
            if (expectedBucketCount != null && bucket.size != expectedBucketCount) {
                error("分页题数不匹配：分片游标预期 $expectedBucketCount，实际获取 ${bucket.size}")
            }
            if (practiceTypes.size == 1 && reportedCount != null && bucket.size != reportedCount) {
                error("题数不匹配：平台报告 $reportedCount，实际获取 ${bucket.size}")
            }
            for (item in bucket) {
                val qid = item.optString("questionid", "").trim()
                require(seenIds.add(qid)) { "题目 $qid 在不同状态中重复" }
                rawAll.add(item)
            }
        }

        if (!practicedOnly) {
            if (observedReportedCount != null && rawAll.size != observedReportedCount) {
                error("练习「${practice.practiceName}」题数不匹配：接口报告 $observedReportedCount，实际获取 ${rawAll.size}")
            }
            if (chapters.isEmpty() && questionTypes.isEmpty() &&
                practice.questionCount != null && rawAll.size != practice.questionCount
            ) {
                error("练习「${practice.practiceName}」总题数不匹配：平台报告 ${practice.questionCount}，实际获取 ${rawAll.size}")
            }
        }

        rawAll.sortWith(
            compareBy(
                { chapterOrder[it.optString("chapterid", "")] ?: chapterOrder.size },
                { typeOrder[it.optString("questiontypeid", "")] ?: typeOrder.size }
            )
        )

        return rawAll.map { raw -> parseQuestion(raw, practice, chapterMap, typeMap) }
    }

    private fun fetchPage(
        practice: PracticeItem,
        pageIndex: Int,
        pageCount: Int,
        chapters: List<ChapterItem>,
        questionTypes: List<QuestionTypeItem>,
        practiceType: Int,
        idParam: String
    ): Triple<List<JSONObject>, List<String>, Int?> {
        val params = linkedMapOf(
            "key" to authKey,
            "courseid" to practice.courseId,
            "practiseid" to practice.practiseId,
            "studentpractiseid" to practice.id.toString(),
            "teacherid" to practice.teacherId,
            "pagecount" to pageCount.toString(),
            "pageindex" to pageIndex.toString(),
            "practisetype" to practiceType.toString(),
            "statenum" to "0",
            "id" to idParam,
            "list" to "true",
            "studentpractisequestioncount" to (practice.questionCount ?: 0).toString()
        )
        if (chapters.isNotEmpty()) params["chapterid"] = chapters.joinToString(",") { it.id }
        if (questionTypes.isNotEmpty()) params["questiontypeid"] = questionTypes.joinToString(",") { it.questionTypeId.ifBlank { it.id } }

        val d = postForm("$BASE_URL?act=studentpracticeapi&op=getStudentPractiseQuestionList", params)
        val datas = d.getJSONObject("datas")
        val qArr = datas.getJSONArray("questionlist")
        val list = List(qArr.length()) { i -> qArr.getJSONObject(i) }
        val spArr = datas.optJSONArray("split")
        val split = if (spArr != null) List(spArr.length()) { i -> spArr.optString(i, "") } else emptyList()
        val reported = datas.optString("questioncount", "").toIntOrNull()
        return Triple(list, split, reported)
    }

    private fun parseQuestion(
        raw: JSONObject,
        practice: PracticeItem,
        chapterMap: Map<String, String>,
        typeMap: Map<String, String>
    ): QuestionItem {
        val qid = raw.optString("questionid", "").trim()
        require(qid.isNotBlank()) { "题目缺少 questionid" }
        val subArr = raw.optJSONArray("subquestions")
        val subStr = raw.optString("subquestions", "").trim()
        val hasSub = (subArr != null && subArr.length() > 0) ||
            (subStr.isNotEmpty() && subStr != "[]" && subStr != "null" && subStr != "None")
        require(!hasSub) { "题目 $qid 包含子题，暂不支持导出" }

        val stem = Integrity.decodeRichContent(raw.optString("subjecthtml_svg", ""))
        require(stem.isNotBlank()) { "题目 $qid 缺少题干" }
        val answerHtml = Integrity.decodeRichContent(raw.optString("answerhtml_svg", ""))
        val rawAnalysisHtml = Integrity.decodeRichContent(raw.optString("analysishtml_svg", ""))
        val analysisHtml = if (Integrity.hasVisibleRichContent(rawAnalysisHtml)) rawAnalysisHtml else ""

        val qtId = raw.optString("questiontypeid", "").trim()
        val qtName = typeMap[qtId] ?: raw.optString("questiontypename", "未分类题型").ifBlank { "未分类题型" }
        val choice = Integrity.isChoiceQuestion(qtName)

        val optArr = raw.optJSONArray("options")
        var options = mutableListOf<QuestionOption>()
        var hasOptions = optArr != null
        if (optArr != null) {
            if (choice) require(optArr.length() <= 26) { "题目 $qid 选项超过 26 个" }
            for (i in 0 until optArr.length()) {
                val o = optArr.getJSONObject(i)
                val html = Integrity.decodeRichContent(o.optString("questionoptionhtml_svg", ""))
                require(html.isNotBlank()) { "题目 $qid 存在空选项" }
                val isTrue = o.optString("istrue", o.optInt("istrue", 0).toString()) == "1"
                options += QuestionOption(isTrue = isTrue, html = html)
            }
        }
        val derived = if (choice && options.isNotEmpty()) {
            options.mapIndexedNotNull { idx, opt -> if (opt.isTrue) "${'A' + idx}" else null }.joinToString("、")
        } else ""

        var answer = answerHtml.ifBlank { raw.optString("answer", "").trim() }.ifBlank { derived }
        if (answer.isBlank() && !choice && options.isNotEmpty()) {
            answer = if (options.size == 1) {
                options[0].html
            } else {
                "<div>" + options.mapIndexed { idx, opt ->
                    "<div><strong>（空 ${idx + 1}）</strong>${opt.html}</div>"
                }.joinToString("") + "</div>"
            }
            options = mutableListOf()
            hasOptions = false
        }
        require(answer.isNotBlank()) { "题目 $qid 缺少答案" }

        val chapId = raw.optString("chapterid", "").trim()
        val chapName = if (chapId.isNotBlank() && chapId != "0") chapterMap[chapId] ?: "未分类章节" else "未分类章节"

        return QuestionItem(
            id = "${practice.id}:$qid",
            questionType = qtName,
            subjectHtml = stem,
            answer = answer,
            hasOptions = hasOptions,
            options = options,
            subjectName = practice.lessonName.ifBlank { practice.practiceName.ifBlank { "未分类学科" } },
            chapterName = chapName,
            analysisHtml = analysisHtml,
            isChoice = choice
        )
    }

    private fun postForm(url: String, params: Map<String, String>): JSONObject {
        val body = FormBody.Builder().apply {
            params.forEach { (k, v) -> add(k, v) }
        }.build()
        val req = Request.Builder()
            .url(url)
            .header("User-Agent", "Mozilla/5.0")
            .post(body)
            .build()
        http.newCall(req).execute().use { resp ->
            if (!resp.isSuccessful) error("平台请求失败（HTTP ${resp.code}）")
            val text = resp.body?.string().orEmpty()
            val json = JSONObject(text)
            if (json.optInt("code", -1) != 200) {
                val err = json.optJSONObject("datas")?.optString("error").orEmpty()
                error(err.ifBlank { "接口返回错误 code=${json.optInt("code")}" })
            }
            return json
        }
    }

    private fun rsaEncrypt(plainText: String): String {
        val keyBytes = Base64.decode(RSA_PUB_B64, Base64.DEFAULT)
        val spec = X509EncodedKeySpec(keyBytes)
        val pubKey = KeyFactory.getInstance("RSA").generatePublic(spec)
        val cipher = Cipher.getInstance("RSA/ECB/PKCS1Padding")
        cipher.init(Cipher.ENCRYPT_MODE, pubKey)
        val encrypted = cipher.doFinal(plainText.toByteArray(Charsets.UTF_8))
        return Base64.encodeToString(encrypted, Base64.NO_WRAP)
    }
}
