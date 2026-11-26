package com.cctr.export.core

import org.json.JSONArray
import org.json.JSONObject
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.util.Base64

data class PlatformPreset(
    val key: String,
    val label: String,
    val url: String
)

/**
 * 超星学习通 / 雨课堂 内置浏览器抓包、TrueType cmap 解析与端侧加密字体解密还原。
 */
object WebPlatformExtractor {
    val PLATFORM_PRESETS = listOf(
        PlatformPreset("chaoxing", "超星学习通", "https://i.chaoxing.com"),
        PlatformPreset("yuketang", "雨课堂", "https://www.yuketang.cn/web"),
        PlatformPreset("yuketang_cj", "长江雨课堂", "https://changjiang.yuketang.cn/web"),
        PlatformPreset("yuketang_ht", "荷塘雨课堂", "https://hetang.yuketang.cn/web"),
        PlatformPreset("yuketang_hh", "黄河雨课堂", "https://huanghe.yuketang.cn/web")
    )

    const val DESKTOP_USER_AGENT =
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"

    private val TAG_SPLIT_RE = Regex("(<[^>]+>)")

    const val XHR_INTERCEPT_JS = """
        (function() {
          if (window.__cctrHooked) return;
          window.__cctrHooked = true;
          window.__cctrApiPayloads = window.__cctrApiPayloads || [];
          function pushPayload(url, data) {
            try {
              if (!data || typeof data !== 'object') return;
              const u = String(url || '');
              if (!/get_exercise_list|problem|exam|homework|quiz|work|paper|question/i.test(u)) return;
              window.__cctrApiPayloads.push({ url: u, ts: Date.now(), data: data });
              if (window.__cctrApiPayloads.length > 25) window.__cctrApiPayloads.shift();
            } catch (e) {}
          }
          const origFetch = window.fetch;
          if (typeof origFetch === 'function') {
            window.fetch = async function(...args) {
              const resp = await origFetch.apply(this, args);
              try {
                const u = (args[0] && args[0].url) ? args[0].url : String(args[0] || '');
                if (/get_exercise_list|problem|exam|homework|quiz|work|paper/i.test(u)) {
                  resp.clone().json().then(d => pushPayload(u, d)).catch(() => {});
                }
              } catch (e) {}
              return resp;
            };
          }
          const origOpen = XMLHttpRequest.prototype.open;
          const origSend = XMLHttpRequest.prototype.send;
          XMLHttpRequest.prototype.open = function(method, url) {
            this.__cctrUrl = String(url || '');
            return origOpen.apply(this, arguments);
          };
          XMLHttpRequest.prototype.send = function() {
            this.addEventListener('load', function() {
              try {
                if (this.__cctrUrl && /get_exercise_list|problem|exam|homework|quiz|work|paper/i.test(this.__cctrUrl)) {
                  const text = this.responseType === '' || this.responseType === 'text' ? this.responseText : '';
                  if (text && text.trim().startsWith('{')) pushPayload(this.__cctrUrl, JSON.parse(text));
                }
              } catch (e) {}
            });
            return origSend.apply(this, arguments);
          };
        })();
    """

    const val EXTRACT_QUESTIONS_JS = """
        (async function() {
          function collectWins(win, depth, out) {
            if (!win || depth > 4) return;
            out.push(win);
            try {
              const frames = win.frames || [];
              for (let i = 0; i < frames.length; i++) {
                try { void frames[i].document.title; collectWins(frames[i], depth + 1, out); } catch (e) {}
              }
            } catch (e) {}
          }
          function parseTtfCmap(bytes) {
            const cps = new Set();
            try {
              const dv = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
              if (dv.byteLength < 12) return cps;
              const numTables = dv.getUint16(4, false);
              let cmapOff = -1;
              for (let i = 0; i < numTables; i++) {
                const rec = 12 + i * 16;
                if (rec + 16 > dv.byteLength) break;
                const tag = String.fromCharCode(dv.getUint8(rec), dv.getUint8(rec+1), dv.getUint8(rec+2), dv.getUint8(rec+3));
                if (tag === 'cmap') { cmapOff = dv.getUint32(rec + 8, false); break; }
              }
              if (cmapOff < 0 || cmapOff + 4 > dv.byteLength) return cps;
              const numSub = dv.getUint16(cmapOff + 2, false);
              for (let i = 0; i < numSub; i++) {
                const sRec = cmapOff + 4 + i * 8;
                if (sRec + 8 > dv.byteLength) break;
                const subOff = cmapOff + dv.getUint32(sRec + 4, false);
                if (subOff + 14 > dv.byteLength) continue;
                const fmt = dv.getUint16(subOff, false);
                if (fmt === 4) {
                  const segCount = dv.getUint16(subOff + 6, false) >> 1;
                  const endStart = subOff + 14;
                  const startStart = endStart + segCount * 2 + 2;
                  if (startStart + segCount * 2 > dv.byteLength) continue;
                  for (let s = 0; s < segCount; s++) {
                    const endC = dv.getUint16(endStart + s * 2, false);
                    const startC = dv.getUint16(startStart + s * 2, false);
                    if (startC === 0xFFFF && endC === 0xFFFF) continue;
                    const lim = Math.min(endC, startC + 12000);
                    for (let cp = startC; cp <= lim; cp++) if (cp > 0x20 && cp !== 0xFFFF) cps.add(cp);
                  }
                } else if (fmt === 12 && subOff + 16 <= dv.byteLength) {
                  const numGrp = dv.getUint32(subOff + 12, false);
                  for (let g = 0; g < numGrp; g++) {
                    const gOff = subOff + 16 + g * 12;
                    if (gOff + 12 > dv.byteLength) break;
                    const sc = dv.getUint32(gOff, false);
                    const ec = dv.getUint32(gOff + 4, false);
                    const lim = Math.min(ec, sc + 12000);
                    for (let cp = sc; cp <= lim; cp++) if (cp > 0x20) cps.add(cp);
                  }
                }
              }
            } catch (e) {}
            return cps;
          }
          function decodeBase64Bytes(b64) {
            const bin = atob(b64);
            const arr = new Uint8Array(bin.length);
            for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
            return arr;
          }
          function cleanHtmlNode(node, baseHref) {
            if (!node) return '';
            const clone = node.cloneNode(true);
            clone.querySelectorAll('script, style, iframe, button, input, select, textarea').forEach(x => x.remove());
            clone.querySelectorAll('img').forEach(img => {
              const rawSrc = img.getAttribute('src') || img.getAttribute('data-original') || img.getAttribute('data-src') || '';
              if (rawSrc && !/^data:/i.test(rawSrc)) {
                try { img.setAttribute('src', new URL(rawSrc, baseHref).href); } catch (e) {}
              }
            });
            return clone.innerHTML.trim();
          }
          function txtOf(el) { return (el && (el.innerText || el.textContent) || '').trim(); }

          const wins = [];
          collectWins(window, 0, wins);
          const host = (location.hostname || '').toLowerCase();
          const isCx = /chaoxing|xuexitong/.test(host);
          const isYkt = /yuketang|xuetangx/.test(host);
          const items = [];
          const secretFontFamilies = [];
          const secretCodepoints = new Set();
          const secretCharTexts = new Set();
          let apiFontUrl = '';
          let pageTitle = (document.title || '').replace(/\s*[-–|].*$/, '').trim();

          for (const w of wins) {
            let doc;
            try { doc = w.document; } catch (e) { continue; }
            const baseHref = doc.location ? doc.location.href : location.href;
            try { if (doc.fonts && doc.fonts.ready) await doc.fonts.ready; } catch (e) {}
            try {
              const styles = Array.from(doc.querySelectorAll('style')).map(s => s.textContent || '');
              for (const cssText of styles) {
                const ffBlocks = cssText.match(/@font-face\s*\{[^}]*\}/gi) || [];
                for (const blk of ffBlocks) {
                  const famM = blk.match(/font-family\s*:\s*['"]?([^'";}]+)['"]?/i);
                  const fam = famM ? famM[1].trim() : '';
                  const b64M = blk.match(/data:[^;]*font[^;]*;base64,([A-Za-z0-9+/=]+)/i);
                  const urlM = blk.match(/url\(['"]?(https?:[^'")\s]+\.ttf[^'")\s]*)['"]?\)/i);
                  if (/cxsecret|ykt|yuketang|encrypt|secret/i.test(fam) || b64M) {
                    if (fam && !secretFontFamilies.includes(fam)) secretFontFamilies.push(fam);
                    if (b64M) parseTtfCmap(decodeBase64Bytes(b64M[1])).forEach(cp => secretCodepoints.add(cp));
                    else if (urlM && !apiFontUrl) apiFontUrl = urlM[1];
                  }
                }
              }
            } catch (e) {}

            const apiPayloads = w.__cctrApiPayloads || [];
            let matchedApi = false;
            for (let pi = apiPayloads.length - 1; pi >= 0; pi--) {
              const p = apiPayloads[pi];
              const dt = (p.data && p.data.data) ? p.data.data : p.data;
              if (!dt || !Array.isArray(dt.problems) || !dt.problems.length) continue;
              if (dt.name) pageTitle = String(dt.name);
              if (dt.font && typeof dt.font === 'string' && !apiFontUrl) apiFontUrl = dt.font;
              for (const pr of dt.problems) {
                const qtype = String(pr.TypeText || pr.typeText || ({
                  0: '单选题', 1: '单选题', 2: '多选题', 3: '多选题', 4: '判断题', 5: '填空题', 6: '简答题'
                }[String(pr.Type ?? pr.type)] || '综合题'));
                const stem = String(pr.Body || pr.body || pr.question || pr.content || '').trim();
                if (!stem) continue;
                const opts = [];
                for (const o of (pr.Options || pr.options || [])) {
                  const val = typeof o === 'string' ? o : String(o.value || o.name || o.text || o.html || '');
                  if (val.trim()) opts.push({ isTrue: !!(o && (o.isCorrect || o.is_true)), html: val.trim() });
                }
                let ans = pr.Answer ?? pr.answer ?? '';
                if (Array.isArray(ans)) ans = ans.join('、');
                else if (ans && typeof ans === 'object') ans = Object.values(ans).join('；');
                items.push({
                  id: String(pr.ProblemID || pr.problem_id || pr.id || ('ykt:' + (items.length + 1))),
                  questionType: qtype, stemHtml: stem, options: opts,
                  answerHtml: String(ans || '').trim(),
                  analysisHtml: String(pr.Remark || pr.analysis || '').trim(),
                  chapterName: String(dt.name || '雨课堂作业')
                });
              }
              matchedApi = true;
              break;
            }
            if (matchedApi) continue;

            const cxNodes = Array.from(doc.querySelectorAll('.TiMu, .questionLi, .singleQuestion, div[id^="sigleQuestionDiv"]'));
            const topCx = cxNodes.filter(el => !cxNodes.some(other => other !== el && other.contains(el)));
            if (topCx.length > 0) {
              topCx.forEach((el, idx) => {
                el.querySelectorAll('.font-cxsecret, [style*="font-cxsecret"]').forEach(fn => {
                  for (const ch of txtOf(fn)) if (ch.codePointAt(0) > 127) secretCharTexts.add(ch);
                  if (!secretFontFamilies.includes('font-cxsecret')) secretFontFamilies.push('font-cxsecret');
                });
                const titleEl = el.querySelector('.Zy_TItle .clearfix, .Zy_TItle, .newZy_TItle, .mark_name, h3.mark_name');
                const stemHtml = cleanHtmlNode(titleEl || el.querySelector('.stem, .title'), baseHref);
                if (!stemHtml) return;
                let qtype = '';
                const typeEl = el.querySelector('.colorShallow, .newZy_TItle span, .type_tit, .mark_name span');
                if (typeEl) {
                  const m = txtOf(typeEl).match(/(单选(?:题)?|多选(?:题)?|判断(?:题)?|填空(?:题)?|简答(?:题)?|论述(?:题)?|计算(?:题)?)/);
                  if (m) qtype = m[1];
                }
                const opts = [];
                el.querySelectorAll('ul.mark_letter li, .qtDetail li, .Zy_ulTop li, .mark_answer .answer_p, .stem_answer .answerBg').forEach(o => {
                  const h = cleanHtmlNode(o, baseHref);
                  if (h) opts.push({ isTrue: false, html: h });
                });
                let ansHtml = '', anaHtml = '';
                el.querySelectorAll('.Py_answer, .mark_answer, .mark_key, .newAnswer, .analysisDiv').forEach(an => {
                  const rightEl = an.querySelector('.rightAnswerContent, .colorGreen, .mark_fill dd');
                  if (rightEl && !ansHtml) ansHtml = cleanHtmlNode(rightEl, baseHref);
                  const anaEl = an.querySelector('.analysisInfo, .Py_tk, .mark_jx, .answerAnalysis');
                  if (anaEl && !anaHtml) anaHtml = cleanHtmlNode(anaEl, baseHref);
                  const rawT = txtOf(an);
                  if (!ansHtml && /正确答案\s*[:：]/.test(rawT)) ansHtml = rawT.split(/正确答案\s*[:：]/)[1].split(/\n|我的答案|答案解析/)[0].trim();
                  if (!anaHtml && /答案解析\s*[:：]/.test(rawT)) anaHtml = rawT.split(/答案解析\s*[:：]/)[1].trim();
                });
                items.push({
                  id: String(el.getAttribute('data') || el.id || ('cx:' + (idx + 1))),
                  questionType: qtype || (opts.length > 0 ? '单选题' : '简答题'),
                  stemHtml, options: opts, answerHtml: ansHtml, analysisHtml: anaHtml,
                  chapterName: pageTitle || '超星学习通'
                });
              });
              continue;
            }

            const yktNodes = Array.from(doc.querySelectorAll('.subject-item, .problem-item, .question-item, .exam-item, .exercise-item, [class*="question-item"]'));
            const topYkt = yktNodes.filter(el => !yktNodes.some(other => other !== el && other.contains(el)));
            topYkt.forEach((el, idx) => {
              const stemEl = el.querySelector('.item-body, .problem-body, .stem, .title, [class*="stem"], [class*="title"]');
              const stemHtml = cleanHtmlNode(stemEl || el, baseHref);
              if (!stemHtml) return;
              const opts = [];
              el.querySelectorAll('.item-option, .option-item, [class*="option-item"], li').forEach(o => {
                const h = cleanHtmlNode(o, baseHref);
                if (h) opts.push({ isTrue: /correct|right|checked/i.test(o.className || ''), html: h });
              });
              const ansEl = el.querySelector('.correct-answer, .answer, [class*="answer"]');
              const anaEl = el.querySelector('.analysis, .remark, [class*="analysis"]');
              items.push({
                id: String(el.id || ('dom:' + (idx + 1))),
                questionType: opts.length > 0 ? '选择题' : '问答题',
                stemHtml, options: opts, answerHtml: cleanHtmlNode(ansEl, baseHref), analysisHtml: cleanHtmlNode(anaEl, baseHref),
                chapterName: pageTitle || '网页提取'
              });
            });
          }

          if (apiFontUrl && secretCodepoints.size === 0) {
            try {
              const r = await fetch(apiFontUrl);
              if (r.ok) parseTtfCmap(new Uint8Array(await r.arrayBuffer())).forEach(cp => secretCodepoints.add(cp));
            } catch (e) {}
          }

          const usedChars = new Set();
          const stripTags = (s) => String(s || '').replace(/<[^>]+>/g, '');
          for (const it of items) {
            const blobs = [stripTags(it.stemHtml), stripTags(it.answerHtml), stripTags(it.analysisHtml)];
            for (const o of (it.options || [])) blobs.push(stripTags(o.html));
            for (const b of blobs) {
              for (const ch of b) {
                const cp = ch.codePointAt(0);
                if (cp > 127 && (secretCodepoints.has(cp) || secretCharTexts.has(ch))) usedChars.add(ch);
              }
            }
          }
          const secretGlyphs = [];
          if (usedChars.size > 0 && secretFontFamilies.length > 0) {
            const cv = document.createElement('canvas');
            cv.width = 64; cv.height = 64;
            const ctx = cv.getContext('2d');
            const famStr = secretFontFamilies.map(f => '"' + f.replace(/"/g, '') + '"').join(', ') + ', serif';
            for (const ch of Array.from(usedChars).slice(0, 600)) {
              ctx.fillStyle = '#FFFFFF'; ctx.fillRect(0, 0, 64, 64);
              ctx.fillStyle = '#000000'; ctx.font = '42px ' + famStr;
              ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
              ctx.fillText(ch, 32, 34);
              const b64 = (cv.toDataURL('image/png').split(',')[1]) || '';
              if (b64) secretGlyphs.push({ char: ch, pngBase64: b64 });
            }
          }
          const platform = isCx ? '超星学习通' : (isYkt ? '雨课堂' : '网页捕获');
          return JSON.stringify({
            ok: items.length > 0,
            error: items.length > 0 ? '' : '当前页面未检测到题目节点，请进入具体的作业/测验详情页后再提取',
            title: pageTitle || (platform + '题库'),
            sourceLabel: platform,
            platform: platform,
            items: items,
            secretGlyphs: secretGlyphs
          });
        })()
    """

    fun parseTtfCmapCodepoints(ttfBytes: ByteArray): Set<Int> {
        val cps = HashSet<Int>()
        if (ttfBytes.size < 12) return cps
        val buf = ByteBuffer.wrap(ttfBytes).order(ByteOrder.BIG_ENDIAN)
        val numTables = buf.getShort(4).toInt() and 0xFFFF
        var cmapOff = -1
        for (i in 0 until numTables) {
            val rec = 12 + i * 16
            if (rec + 16 > ttfBytes.size) break
            val tag = String(ttfBytes, rec, 4, Charsets.US_ASCII)
            if (tag == "cmap") {
                cmapOff = buf.getInt(rec + 8)
                break
            }
        }
        if (cmapOff < 0 || cmapOff + 4 > ttfBytes.size) return cps
        val numSub = buf.getShort(cmapOff + 2).toInt() and 0xFFFF
        for (i in 0 until numSub) {
            val sRec = cmapOff + 4 + i * 8
            if (sRec + 8 > ttfBytes.size) break
            val subOff = cmapOff + buf.getInt(sRec + 4)
            if (subOff + 14 > ttfBytes.size) continue
            val fmt = buf.getShort(subOff).toInt() and 0xFFFF
            if (fmt == 4) {
                val segCount = (buf.getShort(subOff + 6).toInt() and 0xFFFF) shr 1
                val endStart = subOff + 14
                val startStart = endStart + segCount * 2 + 2
                if (startStart + segCount * 2 > ttfBytes.size) continue
                for (s in 0 until segCount) {
                    val endC = buf.getShort(endStart + s * 2).toInt() and 0xFFFF
                    val startC = buf.getShort(startStart + s * 2).toInt() and 0xFFFF
                    if (startC == 0xFFFF && endC == 0xFFFF) continue
                    val lim = minOf(endC, startC + 12000)
                    for (cp in startC..lim) {
                        if (cp > 0x20 && cp != 0xFFFF) cps.add(cp)
                    }
                }
            } else if (fmt == 12 && subOff + 16 <= ttfBytes.size) {
                val numGrp = buf.getInt(subOff + 12)
                for (g in 0 until numGrp) {
                    val gOff = subOff + 16 + g * 12
                    if (gOff + 12 > ttfBytes.size) break
                    val sc = buf.getInt(gOff)
                    val ec = buf.getInt(gOff + 4)
                    val lim = minOf(ec, sc + 12000)
                    for (cp in sc..lim) {
                        if (cp > 0x20) cps.add(cp)
                    }
                }
            }
        }
        return cps
    }

    fun applyGlyphMapToHtml(rawHtml: String, mapping: Map<String, String>): String {
        if (rawHtml.isEmpty() || mapping.isEmpty()) return rawHtml
        val sb = StringBuilder(rawHtml.length)
        var last = 0
        for (m in TAG_SPLIT_RE.findAll(rawHtml)) {
            if (m.range.first > last) {
                val txt = rawHtml.substring(last, m.range.first)
                for (ch in txt) sb.append(mapping[ch.toString()] ?: ch)
            }
            sb.append(m.value)
            last = m.range.last + 1
        }
        if (last < rawHtml.length) {
            for (ch in rawHtml.substring(last)) sb.append(mapping[ch.toString()] ?: ch)
        }
        return sb.toString()
    }

    private fun cleanCapturedHtml(raw: String): String {
        val t = raw.trim()
        if (t.isEmpty()) return ""
        if ('<' !in t) return t
        return try {
            Integrity.sanitizeRichHtml(t)
        } catch (e: IllegalArgumentException) {
            if (e.message?.contains("图片来源不在允许域") == true) throw e
            t.replace(Regex("<(?!img\\b)[^>]+>", RegexOption.IGNORE_CASE), "").trim()
        }
    }

    private fun stripLeadingOptPrefix(optHtml: String): String {
        return optHtml.replaceFirst(
            Regex("^\\s*(?:<span[^>]*>\\s*)?[A-H]\\s*[.、．)）:：]?\\s*(?:</span>\\s*)?", RegexOption.IGNORE_CASE),
            ""
        ).trim()
    }

    fun parseCapturedPayload(
        rawJson: String,
        glyphRecognizer: (ByteArray) -> String
    ): Pair<String, List<QuestionItem>> {
        val payload = JSONObject(rawJson)
        require(payload.optBoolean("ok", false)) {
            payload.optString("error").ifBlank { "当前页面未提取到题目" }
        }
        val mapping = HashMap<String, String>()
        val glyphs = payload.optJSONArray("secretGlyphs")
        if (glyphs != null) {
            for (i in 0 until glyphs.length()) {
                val g = glyphs.optJSONObject(i) ?: continue
                val ch = g.optString("char")
                val b64 = g.optString("pngBase64")
                if (ch.isNotEmpty() && b64.isNotEmpty() && ch !in mapping) {
                    runCatching {
                        val bytes = Base64.getDecoder().decode(b64)
                        val decoded = glyphRecognizer(bytes)
                        if (decoded.isNotEmpty()) mapping[ch] = decoded
                    }
                }
            }
        }

        val title = payload.optString("title").trim().ifBlank { "网页捕获题库" }
        val sourceLabel = payload.optString("sourceLabel")
            .ifBlank { payload.optString("platform") }
            .trim().ifBlank { "网页捕获" }
        val items = payload.optJSONArray("items") ?: JSONArray()
        val questions = mutableListOf<QuestionItem>()

        for (i in 0 until items.length()) {
            val it = items.optJSONObject(i) ?: continue
            val stemDec = applyGlyphMapToHtml(it.optString("stemHtml"), mapping)
            val stemClean = cleanCapturedHtml(stemDec)
            if (stemClean.isEmpty()) continue

            val rawType = applyGlyphMapToHtml(it.optString("questionType"), mapping).trim()
            val rawOpts = it.optJSONArray("options")
            val opts = mutableListOf<QuestionOption>()
            if (rawOpts != null) {
                for (k in 0 until rawOpts.length()) {
                    val oObj = rawOpts.optJSONObject(k)
                    val oh = oObj?.optString("html") ?: rawOpts.optString(k)
                    val dec = applyGlyphMapToHtml(oh, mapping)
                    val cleaned = cleanCapturedHtml(stripLeadingOptPrefix(dec))
                    if (cleaned.isNotEmpty()) {
                        opts.add(QuestionOption(isTrue = oObj?.optBoolean("isTrue", false) ?: false, html = cleaned))
                    }
                }
            }

            var ansClean = cleanCapturedHtml(applyGlyphMapToHtml(it.optString("answerHtml"), mapping))
            if (ansClean.isEmpty() && opts.any { it.isTrue }) {
                ansClean = opts.mapIndexedNotNull { idx, o -> if (o.isTrue) "${'A' + idx}" else null }.joinToString("、")
            }
            if (ansClean.isEmpty()) ansClean = "略（当前页面未显示答案）"
            val anaClean = cleanCapturedHtml(applyGlyphMapToHtml(it.optString("analysisHtml"), mapping))

            val qtype = rawType.ifBlank {
                if (opts.isNotEmpty()) "选择题" else "简答题"
            }
            val choice = Integrity.isChoiceQuestion(qtype) || opts.isNotEmpty()
            val finalOpts = if (choice && opts.isNotEmpty() && opts.none { it.isTrue }) {
                val ltrs = Regex("[A-H]").findAll(ansClean.replace(Regex("<[^>]+>"), "").uppercase()).map { it.value }.toSet()
                if (ltrs.isNotEmpty()) opts.mapIndexed { idx, o -> o.copy(isTrue = "${'A' + idx}" in ltrs) } else opts
            } else opts

            val chap = applyGlyphMapToHtml(it.optString("chapterName", title), mapping).trim().ifBlank { title }
            questions.add(
                QuestionItem(
                    id = it.optString("id", "web:${i + 1}"),
                    questionType = qtype,
                    subjectHtml = stemClean,
                    answer = ansClean,
                    hasOptions = finalOpts.isNotEmpty(),
                    options = finalOpts,
                    subjectName = sourceLabel,
                    chapterName = chap,
                    analysisHtml = anaClean,
                    isChoice = choice
                )
            )
        }
        Integrity.validateQuestions(questions)
        return title to questions
    }
}
