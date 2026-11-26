package com.cctr.export.core

import android.util.Base64
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.charset.CodingErrorAction
import java.nio.charset.StandardCharsets
import java.security.MessageDigest
import java.util.zip.GZIPInputStream

object Integrity {
    private val BASE64_RE = Regex("^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$")
    private val CHOICE_RE = Regex("选择|单选|多选")
    private val ZERO_WIDTH_RE = Regex("[\\s\\u200b\\u200c\\u200d\\ufeff]+")
    private val BLANK_ENTITY_RE = Regex("&(?:nbsp|ensp|emsp|thinsp|zwnj|zwj|#160|#xa0|#8194|#8195|#8201|#8203|#x200b|#65279|#xfeff);", RegexOption.IGNORE_CASE)

    private fun hasNonBlankText(raw: String): Boolean {
        val strippedEntities = BLANK_ENTITY_RE.replace(raw, "")
        return ZERO_WIDTH_RE.replace(strippedEntities, "").isNotEmpty()
    }
    private val IMG_DATA_RE = Regex("^data:image/(?:png|jpe?g|gif|webp|bmp|svg\\+xml|x-icon|ico|tiff|avif|apng)(?:;[^,]*)?,", RegexOption.IGNORE_CASE)
    private val IMG_HTTPS_RE = Regex(
        "^(?:https?:)?//(?:[a-z0-9-]+\\.)*(?:" +
            "cctrcloud\\.net|cctrcloud\\.com|aliyuncs\\.com|alicdn\\.com|tbcdn\\.cn|" +
            "chaoxing\\.com|xuexitong\\.com|ddfv2\\.com|" +
            "yuketang\\.cn|xuetangx\\.com|rainclassroom\\.com|myqcloud\\.com|qcloud\\.com|" +
            "icourse163\\.org|126\\.net|zhihuishu\\.com|icve\\.com\\.cn|ulearning\\.cn|" +
            "ketangpai\\.com|pintia\\.cn|educoder\\.net|bcebos\\.com|myhuaweicloud\\.com|" +
            "huaweicloud\\.com|ksyun\\.com|volces\\.com|qiniucdn\\.com|clouddn\\.com|" +
            "ufileos\\.com|edu\\.cn" +
            ")(?::(?:80|443))?(?:/|[?#]|$)",
        RegexOption.IGNORE_CASE
    )
    private val IMG_TAG_SRC_RE = Regex(
        "(<img\\b[^>]*?\\bsrc\\s*=\\s*)(?:\"([^\"]*)\"|'([^']*)'|([^\\s\"'>]+))",
        RegexOption.IGNORE_CASE
    )
    private val IMG_TAG_COUNT_RE = Regex("<img\\b", RegexOption.IGNORE_CASE)
    private val TAG_RE = Regex("<(/?)([a-zA-Z][a-zA-Z0-9_.:-]*)([^>]*)>", RegexOption.DOT_MATCHES_ALL)
    private val ATTR_RE = Regex("([a-zA-Z_:][-a-zA-Z0-9_.:]*)\\s*=\\s*(?:\"([^\"]*)\"|'([^']*)'|([^\\s\"'>]+))")
    private val ENTITY_RE = Regex("&(?:#\\d+|#x[0-9a-fA-F]+|[a-zA-Z][a-zA-Z0-9]{1,15});")
    private val COMMENT_RE = Regex("<!--.*?-->", RegexOption.DOT_MATCHES_ALL)
    private val MSO_COND_RE = Regex("<!\\[(?:if\\b[^\\]]*|endif)\\]>?", RegexOption.IGNORE_CASE)
    private val XML_PI_RE = Regex("<\\?xml\\b[^>]*\\?>", RegexOption.IGNORE_CASE)
    private val XML_BLOCK_RE = Regex("<xml\\b[^>]*>.*?</xml>", setOf(RegexOption.IGNORE_CASE, RegexOption.DOT_MATCHES_ALL))
    private val STYLE_BLOCK_RE = Regex("<style\\b[^>]*>.*?</style>", setOf(RegexOption.IGNORE_CASE, RegexOption.DOT_MATCHES_ALL))
    private val TITLE_BLOCK_RE = Regex("<title\\b[^>]*>.*?</title>", setOf(RegexOption.IGNORE_CASE, RegexOption.DOT_MATCHES_ALL))
    private val WORD_META_RE = Regex("<meta\\b[^>]*>", RegexOption.IGNORE_CASE)
    private val WORD_LINK_RE = Regex(
        "<link\\b[^>]*\\brel\\s*=\\s*[\"']?(?:File-List|Edit-Time-Data|themeData|colorSchemeMapping|dataStore|Original-File)\\b[^>]*>",
        RegexOption.IGNORE_CASE
    )
    private val GLUED_ATTR_RE = Regex(
        "<(/?)(p|div|span|font|td|th|tr|table|tbody|thead|tfoot|img|a|li|ul|ol|strong|em)" +
            "(style|align|class|src|href|width|height|color|size|face|colspan|rowspan)=",
        RegexOption.IGNORE_CASE
    )
    private val NS_TAG_RE = Regex("^[a-z0-9_-]+:[a-z0-9_.:-]+$")

    private val ALLOWED_TAGS = setOf(
        "p", "div", "span", "a", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6",
        "strong", "b", "em", "i", "u", "s", "sup", "sub", "code", "kbd", "samp",
        "var", "mark", "del", "ins", "small", "big", "q", "cite", "dfn", "abbr",
        "ol", "ul", "li", "dl", "dt", "dd", "table", "thead", "tbody", "tfoot",
        "tr", "td", "th", "caption", "colgroup", "col", "img", "blockquote",
        "pre", "section"
    )
    private val MATHML_TAGS = setOf(
        "math", "mrow", "mi", "mo", "mn", "msup", "msub", "msubsup", "mfrac",
        "msqrt", "mroot", "mtable", "mtr", "mtd", "mtext", "mspace", "mstyle",
        "mover", "munder", "munderover", "semantics", "annotation", "mfenced",
        "menclose", "mpadded", "mphantom", "merror", "mglyph", "mlabeledtr",
        "mmultiscripts", "mprescripts", "none"
    )
    private val SVG_TAGS = setOf(
        "svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline",
        "polygon", "text", "tspan", "defs", "lineargradient", "radialgradient",
        "stop", "clippath", "mask", "marker", "symbol", "use", "pattern",
        "title", "desc"
    )
    private val VOID_TAGS = setOf(
        "br", "img", "hr", "col", "path", "rect", "circle", "ellipse",
        "line", "polyline", "polygon", "stop", "use", "mspace", "mglyph",
        "mprescripts", "none"
    )
    private val FORBIDDEN_TAGS = setOf(
        "script", "iframe", "frame", "frameset", "object", "embed", "applet",
        "link", "meta", "base", "foreignobject"
    )
    private val ALIAS_TAGS = mapOf(
        "strike" to "s", "tt" to "code", "listing" to "pre", "xmp" to "pre", "plaintext" to "pre",
        "tabody" to "tbody", "tboday" to "tbody", "tbdoy" to "tbody", "tboyd" to "tbody", "tobody" to "tbody",
        "tahead" to "thead", "tehad" to "thead", "tafoot" to "tfoot", "tffot" to "tfoot",
        "big" to "span", "acronym" to "abbr", "dir" to "ul", "menu" to "ul", "nobr" to "span",
        "article" to "div", "header" to "div", "footer" to "div", "main" to "div", "nav" to "div", "aside" to "div",
        "h7" to "h6", "h8" to "h6",
        "label" to "span", "fieldset" to "div", "legend" to "strong", "details" to "div", "summary" to "strong",
        "address" to "div", "time" to "span", "data" to "span", "output" to "span", "progress" to "span", "meter" to "span",
        "ruby" to "span", "rt" to "span", "rp" to "span", "bdi" to "span", "bdo" to "span", "bgsound" to "span",
        "form" to "div", "button" to "span", "select" to "span", "optgroup" to "span", "textarea" to "span", "datalist" to "span"
    )
    private val UNWRAP_TAGS = setOf(
        "font", "center", "wbr", "figure", "figcaption", "picture",
        "html", "head", "body", "basefont", "marquee", "blink", "layer",
        "ilayer", "spacer", "source", "track", "param", "map", "area",
        "canvas", "o", "v", "w", "st1", "m"
    )
    private val CODE_LITERAL_TAGS = setOf(
        "int", "long", "short", "char", "float", "double", "bool", "boolean",
        "void", "byte", "string", "vector", "list", "map", "set", "pair",
        "queue", "stack", "deque", "iostream", "cstdio", "cstdlib", "cstring",
        "cmath", "algorithm", "fstream", "sstream", "iomanip", "t", "k", "v", "e", "r"
    )
    private val SAFE_MATHML_ATTRS = setOf(
        "xmlns", "display", "mathvariant", "mathcolor", "mathbackground", "mathsize",
        "stretchy", "symmetric", "maxsize", "minsize", "fence", "separator",
        "lspace", "rspace", "columnalign", "rowalign", "columnlines", "rowlines",
        "frame", "linethickness", "columnspan", "rowspan", "encoding"
    )
    private val SAFE_SVG_ATTRS = setOf(
        "xmlns", "viewbox", "width", "height", "fill", "stroke", "stroke-width",
        "stroke-linecap", "stroke-linejoin", "stroke-dasharray", "stroke-opacity",
        "fill-opacity", "opacity", "transform", "d", "cx", "cy", "r", "rx", "ry",
        "x", "y", "x1", "y1", "x2", "y2", "dx", "dy", "points", "offset",
        "stop-color", "stop-opacity", "text-anchor", "dominant-baseline",
        "font-size", "font-family", "font-weight", "font-style", "preserveaspectratio",
        "id", "class"
    )
    private const val MAX_GZIP_BYTES = 16 * 1024 * 1024

    const val VERIFY_AND_SLICE_JS = """
        (async function() {
          if (document.fonts && document.fonts.ready) {
            await document.fonts.ready;
          }
          const images = Array.from(document.images || []);
          const decodeResults = await Promise.all(images.map(async (image) => {
            let decoded = false;
            const origSrc = image.getAttribute('src') || '';
            for (let attempt = 0; attempt < 3; attempt++) {
              try {
                if (attempt > 0 && /^https?:/i.test(origSrc)) {
                  await new Promise(r => setTimeout(r, 250));
                  image.removeAttribute('src');
                  image.setAttribute('src', origSrc);
                }
                await image.decode();
                decoded = true;
                break;
              } catch (e) {
              }
            }
            if (!decoded) {
              return { ok: false, error: '图片或公式加载失败：' + origSrc.slice(0, 80) };
            }
            if (!image.naturalWidth || !image.naturalHeight) {
              return { ok: false, error: '图片或公式内容为空' };
            }
            return { ok: true };
          }));
          const failedDecode = decodeResults.find(r => !r.ok);
          if (failedDecode) {
            return JSON.stringify(failedDecode);
          }

          for (const image of images) {
            const src = image.getAttribute('src') || '';
            const isSvgData = /^data:image\/svg\+xml/i.test(src);
            const host = image.closest('article, .option-body, .content') || document.body;
            const availW = Math.max(220, Math.floor((host.getBoundingClientRect().width || document.body.getBoundingClientRect().width || 640) - 2));
            const natW = image.naturalWidth;
            const natH = image.naturalHeight;

            if (isSvgData) {
              const attrW = parseFloat(image.getAttribute('width') || '0');
              const attrH = parseFloat(image.getAttribute('height') || '0');
              const baseW = attrW > 0 ? attrW : natW;
              const baseH = attrH > 0 ? attrH : natH;
              if (baseW > 0 && baseH > 0) {
                let targetW = Math.round(baseW * 0.86 * 10) / 10;
                let targetH = Math.round(baseH * 0.86 * 10) / 10;
                if (targetW > availW) {
                  const ratio = availW / targetW;
                  targetW = availW;
                  targetH = Math.round(targetH * ratio * 10) / 10;
                }
                image.style.width = targetW + 'px';
                image.style.height = targetH + 'px';
                image.style.maxWidth = '100%';
                image.style.verticalAlign = 'middle';
              }
            } else if (natW >= 540 || (natW > 380 && natH <= 140)) {
              const targetW = Math.min(availW, Math.max(Math.min(natW, 240), Math.round(natW * 0.45)));
              image.style.width = targetW + 'px';
              image.style.height = 'auto';
              image.style.maxWidth = '100%';
              image.style.margin = '4px 0';
              if (image.parentElement && image.parentElement.childElementCount === 1 && !(image.parentElement.textContent || '').trim()) {
                image.parentElement.style.textAlign = 'left';
              }
            } else if (natW > availW) {
              image.style.width = availW + 'px';
              image.style.height = 'auto';
            } else {
              image.style.maxWidth = '100%';
            }

            const rect = image.getBoundingClientRect();
            if (!rect.width || !rect.height) {
              return JSON.stringify({ ok: false, error: '图片或公式渲染尺寸为 0' });
            }
            if (rect.height <= 900) continue;
            const container = document.createElement('span');
            container.style.display = 'block';
            for (let offset = 0; offset < rect.height; offset += 900) {
              const slice = document.createElement('span');
              const copy = image.cloneNode(false);
              Object.assign(slice.style, {
                display: 'block',
                position: 'relative',
                overflow: 'hidden',
                width: rect.width + 'px',
                height: Math.min(900, rect.height - offset) + 'px',
                breakInside: 'avoid',
                pageBreakInside: 'avoid'
              });
              Object.assign(copy.style, {
                position: 'absolute',
                left: '0',
                top: (-offset) + 'px',
                maxWidth: 'none',
                width: rect.width + 'px',
                height: rect.height + 'px'
              });
              slice.appendChild(copy);
              container.appendChild(slice);
            }
            image.replaceWith(container);
          }
          const bodyRect = document.body.getBoundingClientRect();
          const allEls = Array.from(document.body.querySelectorAll('*'));
          for (const el of allEls) {
            const b = el.getBoundingClientRect();
            if (b.width > 0 && (b.left < bodyRect.left - 1.5 || b.right > bodyRect.right + 1.5)) {
              return JSON.stringify({ ok: false, error: '题目内容超出页面宽度（可能存在过宽表格或公式）' });
            }
          }
          return JSON.stringify({ ok: true, imageCount: images.length });
        })()
    """

    fun isChoiceQuestion(questionType: String?): Boolean {
        return CHOICE_RE.containsMatchIn(questionType.orEmpty())
    }

    fun sniffImageMime(bytes: ByteArray): String? {
        if (bytes.size < 8) return null
        if (bytes[0] == 0x89.toByte() && bytes[1] == 0x50.toByte() && bytes[2] == 0x4E.toByte() && bytes[3] == 0x47.toByte()) {
            return "image/png"
        }
        if (bytes[0] == 0xFF.toByte() && bytes[1] == 0xD8.toByte() && bytes[2] == 0xFF.toByte()) {
            return "image/jpeg"
        }
        val head6 = String(bytes, 0, 6, StandardCharsets.US_ASCII)
        if (head6 == "GIF87a" || head6 == "GIF89a") return "image/gif"
        if (bytes.size >= 12) {
            val riff = String(bytes, 0, 4, StandardCharsets.US_ASCII)
            val webp = String(bytes, 8, 4, StandardCharsets.US_ASCII)
            if (riff == "RIFF" && webp == "WEBP") return "image/webp"
        }
        return null
    }

    fun decodeRichContent(raw: String?): String {
        if (raw.isNullOrBlank()) return ""
        val compact = raw.replace(Regex("\\s+"), "")
        if (compact.isEmpty()) return ""
        require(BASE64_RE.matches(compact)) { "题目内容 Base64 编码无效，无法确认内容完整" }
        val compressed = try {
            Base64.decode(compact, Base64.DEFAULT)
        } catch (e: Exception) {
            throw IllegalArgumentException("题目内容 Base64 解码失败", e)
        }
        val out = ByteArrayOutputStream()
        try {
            GZIPInputStream(ByteArrayInputStream(compressed)).use { gz ->
                val buf = ByteArray(8192)
                var total = 0
                while (true) {
                    val n = gz.read(buf)
                    if (n <= 0) break
                    total += n
                    require(total <= MAX_GZIP_BYTES) { "题目内容体积超出安全上限" }
                    out.write(buf, 0, n)
                }
            }
        } catch (e: IllegalArgumentException) {
            throw e
        } catch (e: Exception) {
            throw IllegalArgumentException("题目内容 Gzip 解压失败", e)
        }
        val decoder = StandardCharsets.UTF_8.newDecoder()
            .onMalformedInput(CodingErrorAction.REPORT)
            .onUnmappableCharacter(CodingErrorAction.REPORT)
        return try {
            decoder.decode(ByteBuffer.wrap(out.toByteArray())).toString()
        } catch (e: Exception) {
            throw IllegalArgumentException("题目内容不是有效的 UTF-8，无法保证内容完整", e)
        }
    }

    private fun precleanOfficeHtml(rawHtml: String): String {
        var cleaned = COMMENT_RE.replace(rawHtml, "")
        cleaned = MSO_COND_RE.replace(cleaned, "")
        cleaned = XML_PI_RE.replace(cleaned, "")
        cleaned = XML_BLOCK_RE.replace(cleaned, "")
        cleaned = STYLE_BLOCK_RE.replace(cleaned, "")
        cleaned = TITLE_BLOCK_RE.replace(cleaned, "")
        cleaned = WORD_META_RE.replace(cleaned, "")
        cleaned = WORD_LINK_RE.replace(cleaned, "")
        cleaned = GLUED_ATTR_RE.replace(cleaned) { m -> "<${m.groupValues[1]}${m.groupValues[2]} ${m.groupValues[3]}=" }
        return cleaned
    }

    fun sanitizeRichHtml(rawHtml: String): String {
        val trimmed = rawHtml.trim()
        require(trimmed.isNotEmpty()) { "富文本内容为空" }
        val cleaned = precleanOfficeHtml(trimmed)
        val cleanedLower = cleaned.lowercase()

        var hasVisibleContent = false
        val sb = StringBuilder()
        val escapedUnknownStack = mutableListOf<String>()
        var lastIdx = 0

        for (match in TAG_RE.findAll(cleaned)) {
            if (match.range.first > lastIdx) {
                val textPart = cleaned.substring(lastIdx, match.range.first)
                if (hasNonBlankText(textPart)) {
                    hasVisibleContent = true
                }
                sb.append(escapeHtmlPreservingEntities(textPart))
            }
            val isClosing = match.groupValues[1] == "/"
            val rawTagOrig = match.groupValues[2]
            val rawTag = rawTagOrig.lowercase()
            val rawAttrs = match.groupValues[3]
            require(rawTag !in FORBIDDEN_TAGS) {
                "暂不支持富文本标签：<${if (isClosing) "/" else ""}$rawTag>"
            }

            if (rawTag !in UNWRAP_TAGS && !NS_TAG_RE.matches(rawTag)) {
                val nonAsciiBareToken = !isClosing && rawAttrs.any { it.code > 127 } && !ATTR_RE.containsMatchIn(rawAttrs)
                if (nonAsciiBareToken) {
                    hasVisibleContent = true
                    sb.append(escapeText(match.value))
                } else if (!isClosing && rawTag == "input") {
                    val attrMap = ATTR_RE.findAll(rawAttrs).associate { am ->
                        am.groupValues[1].lowercase() to am.groupValues[2].ifEmpty { am.groupValues[3].ifEmpty { am.groupValues[4] } }
                    }
                    val itype = attrMap["type"]?.trim()?.lowercase().orEmpty()
                    if (itype != "hidden") {
                        val label = when (itype) {
                            "checkbox" -> if (rawAttrs.contains("checked", ignoreCase = true)) "☑" else "□"
                            "radio" -> if (rawAttrs.contains("checked", ignoreCase = true)) "◉" else "○"
                            else -> {
                                val v = (attrMap["value"] ?: attrMap["placeholder"] ?: "______").trim().ifEmpty { "______" }
                                "[$v]"
                            }
                        }
                        hasVisibleContent = true
                        sb.append("<span class=\"inline-ctrl\">${escapeText(label)}</span>")
                    }
                } else if (rawTag == "option") {
                    sb.append(if (isClosing) "]</span> " else "<span class=\"inline-ctrl\">[")
                } else if (rawTag == "audio" || rawTag == "video") {
                    if (isClosing) {
                        sb.append("</span>")
                    } else {
                        hasVisibleContent = true
                        val lbl = if (rawTag == "audio") "音频" else "视频"
                        sb.append("<span class=\"inline-ctrl\">[$lbl]")
                    }
                } else {
                    val tag = ALIAS_TAGS[rawTag] ?: rawTag
                    val isMath = tag in MATHML_TAGS
                    val isSvg = tag in SVG_TAGS
                    if (tag !in ALLOWED_TAGS && !isMath && !isSvg) {
                        if (isClosing) {
                            val idx = escapedUnknownStack.lastIndexOf(rawTag)
                            if (idx >= 0) {
                                escapedUnknownStack.removeAt(idx)
                                hasVisibleContent = true
                                sb.append(escapeText(match.value))
                            }
                        } else {
                            val hasClose = cleanedLower.contains("</$rawTag>")
                            val looksLikeCode = rawTag in CODE_LITERAL_TAGS || rawTag.endsWith(".h") || rawTag.endsWith(".hpp") || !hasClose
                            if (looksLikeCode) {
                                hasVisibleContent = true
                                sb.append(escapeText(match.value))
                                if (hasClose) escapedUnknownStack.add(rawTag)
                            }
                        }
                    } else if (isClosing) {
                        if (tag !in VOID_TAGS) sb.append("</$tag>")
                    } else {
                        val cleanAttrs = mutableListOf<String>()
                        var imgSrcHandled = false
                        var skipEmptyImg = false
                        for (am in ATTR_RE.findAll(rawAttrs)) {
                            val k = am.groupValues[1].lowercase()
                            val v = am.groupValues[2].ifEmpty { am.groupValues[3].ifEmpty { am.groupValues[4] } }
                            when {
                                tag == "img" && k == "src" -> {
                                    var s = v.trim()
                                    if (s.isEmpty()) {
                                        skipEmptyImg = true
                                        break
                                    }
                                    if (s.startsWith("//")) s = "https:$s"
                                    require(IMG_DATA_RE.containsMatchIn(s) || IMG_HTTPS_RE.containsMatchIn(s)) {
                                        "图片来源不在允许域（仅支持内嵌图片或 cctrcloud.net / aliyuncs.com 等教育云域名）"
                                    }
                                    if (s.startsWith("http://", ignoreCase = true)) {
                                        s = "https://" + s.substring(7)
                                    }
                                    imgSrcHandled = true
                                    hasVisibleContent = true
                                    cleanAttrs += "src=\"${escapeAttr(s)}\""
                                }
                                tag == "img" && k in setOf("alt", "width", "height", "align") && v.isNotBlank() -> {
                                    cleanAttrs += "$k=\"${escapeAttr(v)}\""
                                }
                                (tag == "td" || tag == "th") && k in setOf("colspan", "rowspan") && v.all { it.isDigit() } -> {
                                    cleanAttrs += "$k=\"$v\""
                                }
                                isMath && k in SAFE_MATHML_ATTRS -> {
                                    cleanAttrs += "$k=\"${escapeAttr(v)}\""
                                }
                                isSvg -> {
                                    if (k == "href" || k == "xlink:href") {
                                        if (v.trim().startsWith("#")) cleanAttrs += "$k=\"${escapeAttr(v.trim())}\""
                                    } else if (k in SAFE_SVG_ATTRS) {
                                        val outName = if (k == "viewbox") "viewBox" else k
                                        cleanAttrs += "$outName=\"${escapeAttr(v)}\""
                                    }
                                }
                            }
                        }
                        if (isMath || (isSvg && tag in setOf("path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text"))) {
                            hasVisibleContent = true
                        }
                        if (tag == "img" && (skipEmptyImg || !imgSrcHandled)) {
                            // 忽略无 src 的空图片占位符
                        } else {
                            val attrStr = if (cleanAttrs.isEmpty()) "" else " " + cleanAttrs.joinToString(" ")
                            if (tag in VOID_TAGS) sb.append("<$tag$attrStr />") else sb.append("<$tag$attrStr>")
                        }
                    }
                }
            }
            lastIdx = match.range.last + 1
        }
        if (lastIdx < cleaned.length) {
            val tail = cleaned.substring(lastIdx)
            if (hasNonBlankText(tail)) {
                hasVisibleContent = true
            }
            sb.append(escapeHtmlPreservingEntities(tail))
        }
        require(hasVisibleContent) { "富文本没有可见内容，无法确认题目或答案完整" }
        return sb.toString()
    }

    fun hasVisibleRichContent(rawHtml: String): Boolean {
        val trimmed = rawHtml.trim()
        if (trimmed.isEmpty()) return false
        val cleaned = precleanOfficeHtml(trimmed)
        return if ('<' in cleaned && '>' in cleaned) {
            try {
                sanitizeRichHtml(cleaned)
                true
            } catch (e: IllegalArgumentException) {
                val msg = e.message.orEmpty()
                if ("没有可见内容" in msg || "内容为空" in msg) {
                    false
                } else {
                    throw e
                }
            }
        } else {
            hasNonBlankText(cleaned)
        }
    }

    private fun renderContent(value: String): Pair<String, Boolean> {
        val t = value.trim()
        require(t.isNotEmpty()) { "内容为空" }
        return if ('<' in t && '>' in t) sanitizeRichHtml(t) to true else escapeText(t) to false
    }

    fun validateQuestions(items: List<QuestionItem>) {
        require(items.isNotEmpty()) { "没有可导出的题目" }
        val seen = HashSet<String>(items.size)
        items.forEachIndexed { idx, q ->
            require(q.id.isNotBlank()) { "第 ${idx + 1} 题缺少 ID" }
            require(seen.add(q.id)) { "题目 ID 重复：${q.id}" }
            require(q.subjectHtml.isNotBlank()) { "第 ${idx + 1} 题（${q.id}）缺少题干" }
            require(q.answer.isNotBlank()) { "第 ${idx + 1} 题（${q.id}）缺少答案" }
            if (q.isChoice) require(q.options.size <= 26) { "第 ${idx + 1} 题选项超过 26 个" }
            q.options.forEachIndexed { oIdx, opt ->
                require(opt.html.isNotBlank()) { "第 ${idx + 1} 题第 ${oIdx + 1} 个选项为空" }
            }
        }
    }

    fun buildExportDocumentHtml(
        questions: List<QuestionItem>,
        variant: AnswerVariant = AnswerVariant.WITH_ANSWERS_RED,
        title: String = "题目与答案",
        startIndex: Int = 1,
        includeHeader: Boolean = true,
        initialGroup: Triple<String, String, String>? = null,
        smartPagination: Boolean = true
    ): String {
        validateQuestions(questions)
        val body = StringBuilder()
        var prevGroup: Triple<String, String, String>? = initialGroup

        questions.forEachIndexed { idx, q ->
            val qNum = startIndex + idx
            val grp = Triple(q.subjectName, q.chapterName, q.questionType)
            if (grp != prevGroup) {
                val grpLabel = "${grp.first} / ${grp.second} / ${grp.third}"
                if (grpLabel != title) {
                    body.append("<h2>${escapeText(grpLabel)}</h2>")
                }
                prevGroup = grp
            }
            val (stemRendered, stemRich) = renderContent(q.subjectHtml)
            body.append("<article><h3>第 $qNum 题 <span>（${escapeText(q.id)}）</span></h3>")
            body.append("<div class=\"${if (stemRich) "content rich" else "content"}\">$stemRendered</div>")

            if (q.hasOptions && q.options.isNotEmpty()) {
                q.options.forEachIndexed { oIdx, opt ->
                    val (optRendered, optRich) = renderContent(opt.html)
                    val isCorrect = opt.isTrue && variant == AnswerVariant.WITH_ANSWERS_RED
                    val label = if (q.isChoice) "<span class=\"option-label\">${'A' + oIdx}.</span>" else ""
                    val cls = if (isCorrect) "option correct" else "option"
                    val bodyCls = "option-body" + (if (label.isNotEmpty()) " labeled" else "") + (if (optRich) " rich" else "")
                    body.append("<div class=\"$cls\">$label<div class=\"$bodyCls\">$optRendered</div></div>")
                }
            }

            if (variant != AnswerVariant.WITHOUT_ANSWERS) {
                val (ansRendered, ansRich) = renderContent(q.answer)
                body.append("<div class=\"label\">答案</div>")
                body.append("<div class=\"${if (ansRich) "content rich" else "content"}\">$ansRendered</div>")
                if (hasVisibleRichContent(q.analysisHtml)) {
                    val (anaRendered, anaRich) = renderContent(q.analysisHtml)
                    body.append("<div class=\"label\">解析</div>")
                    body.append("<div class=\"${if (anaRich) "content rich" else "content"}\">$anaRendered</div>")
                }
            }
            body.append("</article>")
        }

        return """
            <!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><style>
            @page { size: A4; margin: 18mm 18mm; }
            @media screen { html, body { width: 658px; max-width: 658px; margin: 0; padding: 0; } }
            * { box-sizing: border-box; }
            body { margin: 0; font-family: "Noto Sans SC", "PingFang SC", sans-serif; font-size: 10.5pt; line-height: 1.72; color: #111827; overflow-wrap: anywhere; background: #fff; }
            h1 { font-size: 15pt; font-weight: 700; margin: 0 0 12pt; padding-bottom: 8pt; border-bottom: 1.5px solid #e5e7eb; color: #0f172a; }
            h2 { font-size: 12pt; font-weight: 700; margin: 14pt 0 8pt; color: #1e293b; background: #f8fafc; border-left: 3px solid #2563eb; padding: 4.5pt 8pt; border-radius: 4px; break-after: avoid; }
            h3 { font-size: 10.5pt; font-weight: 700; margin: 10pt 0 4pt; break-after: avoid; color: #0f172a; }
            h3 span { color: #64748b; font-weight: normal; font-size: 8.5pt; }
            .content, .option { white-space: pre-wrap; font-size: 10.5pt; line-height: 1.72; }
            .rich, .rich *:not(sub):not(sup), .content *:not(sub):not(sup), .option-body, .option-body *:not(sub):not(sup) { font-family: inherit !important; font-size: 10.5pt !important; line-height: 1.72 !important; }
            sub, sup { font-size: 7.5pt !important; line-height: 0 !important; }
            .rich { white-space: normal; }
            .rich p { margin: 0 0 4pt; }
            .option { margin: 3.5pt 0 3.5pt 0.8em; padding: 2pt 6pt; border-radius: 4px; }
            .option.correct { color: #b91c1c; font-weight: 600; background: #fef2f2; border-left: 2.5px solid #ef4444; }
            .option-label { display: inline-block; min-width: 1.8em; font-weight: 600; }
            .option-body { display: inline; }
            .option-body.rich p:first-child { display: inline; }
            img { max-width: 100%; height: auto; vertical-align: middle; }
            svg { max-width: 100%; height: auto; vertical-align: middle; }
            .inline-ctrl { display: inline-block; padding: 0 3px; border: 1px solid #cbd5e1; border-radius: 3px; background: #f8fafc; font-size: 9.5pt; margin: 0 2px; }
            table { border-collapse: collapse; max-width: 100%; margin: 6pt 0; font-size: 9.5pt; }
            td, th { border: 1px solid #cbd5e1; padding: 4px 7px; font-size: 9.5pt !important; }
            .label { display: block; width: fit-content; margin: 7pt 0 3pt; padding: 1pt 6pt; border-radius: 4px; background: #ecfdf5; border: 1px solid #a7f3d0; font-weight: 700; font-size: 9pt; color: #047857; break-after: avoid; page-break-after: avoid; }
            article { margin-bottom: 12pt; padding-bottom: 8pt; border-bottom: 1px dashed #e2e8f0; }
            article:last-child { border-bottom: none; }
            </style></head><body data-smart-pagination="${if (smartPagination) "1" else "0"}">${if (includeHeader) "<h1>${escapeText(title)}</h1>" else ""}$body</body></html>
        """.trimIndent()
    }

    fun normalizeAllowedImageUrl(url: String): String? {
        var decoded = url.trim().replace("&amp;", "&")
        if (!IMG_HTTPS_RE.containsMatchIn(decoded)) return null
        if (decoded.startsWith("//")) return "https:$decoded"
        return if (decoded.startsWith("http://", ignoreCase = true)) {
            "https://" + decoded.substring(7)
        } else {
            decoded
        }
    }

    fun extractAllowedRemoteImageUrls(questions: List<QuestionItem>): Set<String> {
        val urls = LinkedHashSet<String>()
        fun scan(html: String) {
            if (!html.contains("<img", ignoreCase = true)) return
            for (m in IMG_TAG_SRC_RE.findAll(html)) {
                val raw = m.groupValues[2].ifEmpty { m.groupValues[3].ifEmpty { m.groupValues[4] } }
                normalizeAllowedImageUrl(raw)?.let { urls.add(it) }
            }
        }
        for (q in questions) {
            scan(q.subjectHtml)
            scan(q.answer)
            scan(q.analysisHtml)
            q.options.forEach { scan(it.html) }
        }
        return urls
    }

    fun applyInlinedImages(
        questions: List<QuestionItem>,
        urlToDataUri: Map<String, String>
    ): List<QuestionItem> {
        if (urlToDataUri.isEmpty()) return questions
        fun replaceField(html: String): String {
            if (!html.contains("<img", ignoreCase = true)) return html
            return IMG_TAG_SRC_RE.replace(html) { m ->
                val raw = m.groupValues[2].ifEmpty { m.groupValues[3].ifEmpty { m.groupValues[4] } }
                val norm = normalizeAllowedImageUrl(raw)
                val dataUri = norm?.let { urlToDataUri[it] }
                if (dataUri != null) {
                    "${m.groupValues[1]}\"$dataUri\""
                } else {
                    m.value
                }
            }
        }
        return questions.map { q ->
            q.copy(
                subjectHtml = replaceField(q.subjectHtml),
                answer = replaceField(q.answer),
                analysisHtml = replaceField(q.analysisHtml),
                options = q.options.map { opt -> opt.copy(html = replaceField(opt.html)) }
            )
        }
    }

    fun buildAdaptiveQuestionChunks(
        questions: List<QuestionItem>,
        maxQuestions: Int = 24,
        maxHtmlChars: Int = 24_000,
        maxImages: Int = 28
    ): List<List<QuestionItem>> {
        if (questions.isEmpty()) return emptyList()
        val chunks = ArrayList<List<QuestionItem>>()
        var current = ArrayList<QuestionItem>(maxQuestions.coerceAtLeast(1))
        var curChars = 0
        var curImages = 0

        for (q in questions) {
            var qChars = q.subjectHtml.length + q.answer.length + q.analysisHtml.length
            var qImgs = IMG_TAG_COUNT_RE.findAll(q.subjectHtml).count() +
                IMG_TAG_COUNT_RE.findAll(q.answer).count() +
                IMG_TAG_COUNT_RE.findAll(q.analysisHtml).count()
            for (opt in q.options) {
                qChars += opt.html.length
                qImgs += IMG_TAG_COUNT_RE.findAll(opt.html).count()
            }

            if (current.isNotEmpty() && (
                    current.size >= maxQuestions ||
                    curChars + qChars > maxHtmlChars ||
                    curImages + qImgs > maxImages
                )
            ) {
                chunks.add(current)
                current = ArrayList(maxQuestions.coerceAtLeast(1))
                curChars = 0
                curImages = 0
            }
            current.add(q)
            curChars += qChars
            curImages += qImgs
        }
        if (current.isNotEmpty()) {
            chunks.add(current)
        }
        return chunks
    }

    fun safeArchiveSegment(value: String): String {
        var cleaned = value.trim().replace(Regex("[<>:\"/\\\\|?*\\x00-\\x1f]"), "_")
            .trimEnd('.', ' ').take(60).trim()
        if (cleaned.isEmpty() || cleaned == "." || cleaned == "..") cleaned = "未命名"
        if (Regex("^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\\.|$)", RegexOption.IGNORE_CASE).containsMatchIn(cleaned)) {
            cleaned = "_$cleaned"
        }
        return cleaned
    }

    fun sha256Hex(bytes: ByteArray): String {
        return MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
    }

    private fun escapeHtmlPreservingEntities(s: String): String {
        val sb = StringBuilder(s.length)
        var last = 0
        for (m in ENTITY_RE.findAll(s)) {
            if (m.range.first > last) {
                sb.append(escapeText(s.substring(last, m.range.first)))
            }
            sb.append(m.value)
            last = m.range.last + 1
        }
        if (last < s.length) {
            sb.append(escapeText(s.substring(last)))
        }
        return sb.toString()
    }

    private fun escapeText(s: String): String {
        return s.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    }

    private fun escapeAttr(s: String): String {
        return escapeText(s).replace("\"", "&quot;").replace("'", "&#39;")
    }
}
