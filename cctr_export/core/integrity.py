"""内容完整性校验、安全富文本净化与 A4 无损 PDF/HTML 构建"""
from __future__ import annotations

import base64
import gzip
import hashlib
import html as html_lib
import re
from html.parser import HTMLParser
from typing import Iterable

from .models import Question

_BASE64_RE = re.compile(r"^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$")
_CHOICE_RE = re.compile(r"选择|单选|多选")
_ZERO_WIDTH_RE = re.compile(r"[\s\u200b\u200c\u200d\ufeff]+")
_BLANK_ENTITY_NAMES = frozenset({"nbsp", "ensp", "emsp", "thinsp", "zwnj", "zwj"})
_BLANK_CODEPOINTS = frozenset({0x00A0, 0x2002, 0x2003, 0x2009, 0x200B, 0x200C, 0x200D, 0xFEFF})
_IMG_SRC_DATA_RE = re.compile(
    r"^data:image/(?:png|jpe?g|gif|webp|bmp|svg\+xml|x-icon|ico|tiff|avif|apng)(?:;[^,]*)?,",
    re.I,
)
_ALLOWED_IMG_HOSTS = (
    r"cctrcloud\.net|cctrcloud\.com|aliyuncs\.com|alicdn\.com|tbcdn\.cn|"
    r"chaoxing\.com|xuexitong\.com|ddfv2\.com|"
    r"yuketang\.cn|xuetangx\.com|rainclassroom\.com|myqcloud\.com|qcloud\.com|"
    r"icourse163\.org|126\.net|zhihuishu\.com|icve\.com\.cn|ulearning\.cn|"
    r"ketangpai\.com|pintia\.cn|educoder\.net|bcebos\.com|myhuaweicloud\.com|"
    r"huaweicloud\.com|ksyun\.com|volces\.com|qiniucdn\.com|clouddn\.com|"
    r"ufileos\.com|edu\.cn"
)
_IMG_SRC_HTTPS_RE = re.compile(
    rf"^(?:https?:)?//(?:[a-z0-9-]+\.)*(?:{_ALLOWED_IMG_HOSTS})(?::(?:80|443))?(?:/|[?#]|$)",
    re.I,
)

_ALLOWED_TAGS = frozenset({
    "p", "div", "span", "a", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6",
    "strong", "b", "em", "i", "u", "s", "sup", "sub", "code", "kbd", "samp",
    "var", "mark", "del", "ins", "small", "big", "q", "cite", "dfn", "abbr",
    "ol", "ul", "li", "dl", "dt", "dd", "table", "thead", "tbody", "tfoot",
    "tr", "td", "th", "caption", "colgroup", "col", "img", "blockquote",
    "pre", "section",
})
_MATHML_TAGS = frozenset({
    "math", "mrow", "mi", "mo", "mn", "msup", "msub", "msubsup", "mfrac",
    "msqrt", "mroot", "mtable", "mtr", "mtd", "mtext", "mspace", "mstyle",
    "mover", "munder", "munderover", "semantics", "annotation", "mfenced",
    "menclose", "mpadded", "mphantom", "merror", "mglyph", "mlabeledtr",
    "mmultiscripts", "mprescripts", "none",
})
_SVG_TAGS = frozenset({
    "svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline",
    "polygon", "text", "tspan", "defs", "lineargradient", "radialgradient",
    "stop", "clippath", "mask", "marker", "symbol", "use", "pattern",
    "title", "desc",
})
_VOID_TAGS = frozenset({
    "br", "img", "hr", "col", "path", "rect", "circle", "ellipse",
    "line", "polyline", "polygon", "stop", "use", "mspace", "mglyph",
    "mprescripts", "none",
})
_FORBIDDEN_TAGS = frozenset({
    "script", "iframe", "frame", "frameset", "object", "embed", "applet",
    "link", "meta", "base", "foreignobject",
})
_ALIAS_TAGS = {
    "strike": "s", "tt": "code", "listing": "pre", "xmp": "pre", "plaintext": "pre",
    "tabody": "tbody", "tboday": "tbody", "tbdoy": "tbody", "tboyd": "tbody", "tobody": "tbody",
    "tahead": "thead", "tehad": "thead", "tafoot": "tfoot", "tffot": "tfoot",
    "big": "span", "acronym": "abbr", "dir": "ul", "menu": "ul", "nobr": "span",
    "article": "div", "header": "div", "footer": "div", "main": "div", "nav": "div", "aside": "div",
    "h7": "h6", "h8": "h6",
    "label": "span", "fieldset": "div", "legend": "strong", "details": "div", "summary": "strong",
    "address": "div", "time": "span", "data": "span", "output": "span", "progress": "span", "meter": "span",
    "ruby": "span", "rt": "span", "rp": "span", "bdi": "span", "bdo": "span", "bgsound": "span",
    "form": "div", "button": "span", "select": "span", "optgroup": "span", "textarea": "span", "datalist": "span",
}
_UNWRAP_TAGS = frozenset({
    "font", "center", "wbr", "figure", "figcaption", "picture",
    "html", "head", "body", "basefont", "marquee", "blink", "layer",
    "ilayer", "spacer", "source", "track", "param", "map", "area",
    "canvas", "o", "v", "w", "st1", "m",
})
_CODE_LITERAL_TAGS = frozenset({
    "int", "long", "short", "char", "float", "double", "bool", "boolean",
    "void", "byte", "string", "vector", "list", "map", "set", "pair",
    "queue", "stack", "deque", "iostream", "cstdio", "cstdlib", "cstring",
    "cmath", "algorithm", "fstream", "sstream", "iomanip", "t", "k", "v", "e", "r",
})
_NS_TAG_RE = re.compile(r"^[a-z0-9_-]+:[a-z0-9_.:-]+$")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_MSO_COND_RE = re.compile(r"<!\[(?:if\b[^\]]*|endif)\]>?", re.I)
_XML_PI_RE = re.compile(r"<\?xml\b[^>]*\?>", re.I)
_XML_BLOCK_RE = re.compile(r"<xml\b[^>]*>.*?</xml>", re.I | re.S)
_STYLE_BLOCK_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.I | re.S)
_TITLE_BLOCK_RE = re.compile(r"<title\b[^>]*>.*?</title>", re.I | re.S)
_WORD_META_RE = re.compile(r"<meta\b[^>]*>", re.I)
_WORD_LINK_RE = re.compile(
    r"""<link\b[^>]*\brel\s*=\s*["']?(?:File-List|Edit-Time-Data|themeData|colorSchemeMapping|dataStore|Original-File)\b[^>]*>""",
    re.I,
)
_GLUED_ATTR_RE = re.compile(
    r"<(/?)(p|div|span|font|td|th|tr|table|tbody|thead|tfoot|img|a|li|ul|ol|strong|em)"
    r"(style|align|class|src|href|width|height|color|size|face|colspan|rowspan)=",
    re.I,
)
_ALLOWED_STYLE_RULES = {
    "font-weight": re.compile(r"^(?:normal|bold|[1-9]00)$"),
    "font-style": re.compile(r"^(?:normal|italic)$"),
    "text-align": re.compile(r"^(?:left|right|center|justify|start|end)$"),
    "text-decoration": re.compile(r"^(?:none|underline|line-through)$"),
    "vertical-align": re.compile(r"^(?:baseline|middle|top|bottom|sub|super|-?\d+(?:\.\d+)?(?:px|pt|em|%))$"),
}

_MAX_GZIP_BYTES = 16 * 1024 * 1024

# 在浏览器/WebEngine 渲染阶段执行的完整性检查与超长图像切片脚本
VERIFY_AND_SLICE_JS = r"""
(async () => {
  if (document.fonts && document.fonts.ready) {
    await document.fonts.ready;
  }
  const images = Array.from(document.images || []);
  for (const image of images) {
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

    const src = image.getAttribute('src') || '';
    const isSvgData = /^data:image\/svg\+xml/i.test(src);
    const host = image.closest('article, .option-body, .content') || document.body;
    const availW = Math.max(220, Math.floor((host.getBoundingClientRect().width || document.body.getBoundingClientRect().width || 640) - 2));
    const natW = image.naturalWidth;
    const natH = image.naturalHeight;

    if (isSvgData) {
      // Wiris SVG 公式按 12pt(16px) 设计，按 0.86 倍缩放到与 10.5pt(14px) 正文严格等高
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
      // 高分辨率 Word/WPS 截屏公式或整行文字截图通常在 600-1050px（约 2.1x DPI），按 0.45 倍还原为正常阅读字号
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
      // 保持小图/几何示意图 1:1 清晰尺寸
      image.style.maxWidth = '100%';
    }

    const rect = image.getBoundingClientRect();
    if (!rect.width || !rect.height) {
      return { ok: false, error: '图片或公式渲染尺寸为 0' };
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
        pageBreakInside: 'avoid',
      });
      Object.assign(copy.style, {
        position: 'absolute',
        left: '0',
        top: (-offset) + 'px',
        maxWidth: 'none',
        width: rect.width + 'px',
        height: rect.height + 'px',
      });
      slice.appendChild(copy);
      container.appendChild(slice);
    }
    image.replaceWith(container);
  }

  // 分页完整保护（由用户选择开关）：开启时常规单题（<= 920px）不跨页拆散，超长单题页内接续且后续题另起一页
  if (document.body.getAttribute('data-smart-pagination') !== '0') {
    const PAGE_SAFE_H = 920;
    const articles = Array.from(document.querySelectorAll('article'));
    for (const art of articles) {
      const h = Math.ceil(art.getBoundingClientRect().height);
      if (h <= PAGE_SAFE_H) {
        art.style.breakInside = 'avoid';
        art.style.pageBreakInside = 'avoid';
      } else {
        art.style.breakInside = 'auto';
        art.style.pageBreakInside = 'auto';
        if (art.nextElementSibling) {
          art.nextElementSibling.style.breakBefore = 'page';
          art.nextElementSibling.style.pageBreakBefore = 'always';
        }
      }
    }
  }

  const bodyRect = document.body.getBoundingClientRect();
  const allEls = Array.from(document.body.querySelectorAll('*'));
  for (const el of allEls) {
    const b = el.getBoundingClientRect();
    if (b.width > 0 && (b.left < bodyRect.left - 1.5 || b.right > bodyRect.right + 1.5)) {
      return { ok: false, error: '题目内容超出页面宽度（可能存在过宽表格或公式），请检查后重试' };
    }
  }
  return { ok: true, imageCount: images.length };
})();
"""


def is_choice_question(question_type: str) -> bool:
    return bool(_CHOICE_RE.search(str(question_type or "")))


def decode_rich_content(value: object) -> str:
    """严格解码 base64(gzip(utf8))，损坏或无效编码直接抛出异常，绝不静默丢弃内容。"""
    if value is None or value == "":
        return ""
    if not isinstance(value, str):
        raise ValueError("平台返回的题目富文本格式不支持（非字符串）")
    compact = re.sub(r"\s+", "", value)
    if not compact:
        return ""
    if not _BASE64_RE.match(compact):
        raise ValueError("题目内容 Base64 编码无效，无法确认内容完整")
    try:
        compressed = base64.b64decode(compact, validate=True)
        raw = gzip.decompress(compressed)
    except Exception as exc:
        raise ValueError(f"题目内容解压失败: {exc}") from exc
    if len(raw) > _MAX_GZIP_BYTES:
        raise ValueError("题目内容体积超出安全上限")
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ValueError("题目内容不是有效的 UTF-8，无法保证内容完整") from exc


def _sanitize_style(raw_style: str) -> str:
    kept = []
    for part in raw_style.split(";"):
        if ":" not in part:
            continue
        prop, val = part.split(":", 1)
        prop_l = prop.strip().lower()
        val_s = val.strip()
        pattern = _ALLOWED_STYLE_RULES.get(prop_l)
        if pattern and pattern.match(val_s):
            kept.append(f"{prop_l}:{val_s}")
    return ";".join(kept)


def _preclean_office_html(raw_html: str) -> str:
    """剥离 MS Word/WPS 粘贴残留的条件注释、XML 元数据与内联样式块，修复常见粘连标签并保留正文内容。"""
    cleaned = _COMMENT_RE.sub("", raw_html)
    cleaned = _MSO_COND_RE.sub("", cleaned)
    cleaned = _XML_PI_RE.sub("", cleaned)
    cleaned = _XML_BLOCK_RE.sub("", cleaned)
    cleaned = _STYLE_BLOCK_RE.sub("", cleaned)
    cleaned = _TITLE_BLOCK_RE.sub("", cleaned)
    cleaned = _WORD_META_RE.sub("", cleaned)
    cleaned = _WORD_LINK_RE.sub("", cleaned)
    cleaned = _GLUED_ATTR_RE.sub(lambda m: f"<{m.group(1)}{m.group(2)} {m.group(3)}=", cleaned)
    return cleaned


_SAFE_MATHML_ATTRS = frozenset({
    "xmlns", "display", "mathvariant", "mathcolor", "mathbackground", "mathsize",
    "stretchy", "symmetric", "maxsize", "minsize", "fence", "separator",
    "lspace", "rspace", "columnalign", "rowalign", "columnlines", "rowlines",
    "frame", "linethickness", "columnspan", "rowspan", "encoding",
})
_SAFE_SVG_ATTRS = frozenset({
    "xmlns", "viewbox", "width", "height", "fill", "stroke", "stroke-width",
    "stroke-linecap", "stroke-linejoin", "stroke-dasharray", "stroke-opacity",
    "fill-opacity", "opacity", "transform", "d", "cx", "cy", "r", "rx", "ry",
    "x", "y", "x1", "y1", "x2", "y2", "dx", "dy", "points", "offset",
    "stop-color", "stop-opacity", "text-anchor", "dominant-baseline",
    "font-size", "font-family", "font-weight", "font-style", "preserveaspectratio",
    "id", "class",
})


class _StrictHtmlSanitizer(HTMLParser):
    def __init__(self, source_lower: str = ""):
        super().__init__(convert_charrefs=False)
        self.out: list[str] = []
        self.has_visible_content = False
        self._source_lower = source_lower
        self._escaped_unknown_stack: list[str] = []

    def _emit_literal(self, text: str) -> None:
        if _ZERO_WIDTH_RE.sub("", text):
            self.has_visible_content = True
        self.out.append(html_lib.escape(text, quote=False))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        raw_t = tag.lower()
        if raw_t in _FORBIDDEN_TAGS:
            raise ValueError(f"暂不支持富文本标签：<{raw_t}>")
        if raw_t in _UNWRAP_TAGS or _NS_TAG_RE.match(raw_t):
            return
        # 若 <tag ...> 含非 ASCII 裸属性（如数学公式 "a<b 且 b>0" 被误解析为 <b 且 b>），按字面比较表达式转义保留
        if attrs and any((not k.isascii() and v is None) for k, v in attrs):
            self._emit_literal(self.get_starttag_text() or f"<{tag}>")
            return

        attr_map = {k.lower(): (v or "") for k, v in attrs}
        if raw_t == "input":
            itype = attr_map.get("type", "").strip().lower()
            if itype == "hidden":
                return
            if itype == "checkbox":
                label = "☑" if "checked" in attr_map else "□"
            elif itype == "radio":
                label = "◉" if "checked" in attr_map else "○"
            else:
                val = (attr_map.get("value") or attr_map.get("placeholder") or "______").strip() or "______"
                label = f"[{val}]"
            self.has_visible_content = True
            self.out.append(f'<span class="inline-ctrl">{html_lib.escape(label, quote=False)}</span>')
            return
        if raw_t == "option":
            self.out.append('<span class="inline-ctrl">[')
            return
        if raw_t in ("audio", "video"):
            tag_label = "音频" if raw_t == "audio" else "视频"
            self.has_visible_content = True
            self.out.append(f'<span class="inline-ctrl">[{tag_label}]')
            return

        t = _ALIAS_TAGS.get(raw_t, raw_t)
        is_math = t in _MATHML_TAGS
        is_svg = t in _SVG_TAGS
        if t not in _ALLOWED_TAGS and not is_math and not is_svg:
            # 未知非危险标签：区分 C++/Java 头文件与泛型代码文本（如 <stdio.h>、<int>、未闭合 <T>） vs 纯包裹容器标签
            has_close = f"</{raw_t}>" in self._source_lower
            looks_like_code = (
                raw_t in _CODE_LITERAL_TAGS
                or raw_t.endswith((".h", ".hpp"))
                or (not has_close)
            )
            if looks_like_code:
                self._emit_literal(self.get_starttag_text() or f"<{tag}>")
                if has_close:
                    self._escaped_unknown_stack.append(raw_t)
            return

        clean_attrs: list[str] = []
        if "style" in attr_map and attr_map["style"].strip():
            st = _sanitize_style(attr_map["style"])
            if st:
                clean_attrs.append(f'style="{html_lib.escape(st, quote=True)}"')
        if t == "img":
            src = attr_map.get("src", "").strip()
            if not src:
                return
            if src.startswith("//"):
                src = "https:" + src
            if not (_IMG_SRC_DATA_RE.match(src) or _IMG_SRC_HTTPS_RE.match(src)):
                raise ValueError("图片来源不在允许域（仅支持内嵌图片或 cctrcloud.net / aliyuncs.com 等教育云域名）")
            if src.lower().startswith("http://"):
                src = "https://" + src[len("http://"):]
            self.has_visible_content = True
            clean_attrs.append(f'src="{html_lib.escape(src, quote=True)}"')
            for k in ("alt", "width", "height", "align"):
                if k in attr_map and attr_map[k]:
                    clean_attrs.append(f'{k}="{html_lib.escape(attr_map[k], quote=True)}"')
        elif t in ("td", "th"):
            for k in ("colspan", "rowspan"):
                if k in attr_map and attr_map[k].isdigit():
                    clean_attrs.append(f'{k}="{attr_map[k]}"')
        elif is_math:
            self.has_visible_content = True
            for k, v in attrs:
                kl = k.lower()
                if kl in _SAFE_MATHML_ATTRS and v is not None:
                    clean_attrs.append(f'{kl}="{html_lib.escape(v, quote=True)}"')
        elif is_svg:
            if t in ("path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "text"):
                self.has_visible_content = True
            for k, v in attrs:
                kl = k.lower()
                val = v or ""
                if kl == "href" or kl == "xlink:href":
                    if val.strip().startswith("#"):
                        clean_attrs.append(f'{kl}="{html_lib.escape(val.strip(), quote=True)}"')
                    continue
                if kl in _SAFE_SVG_ATTRS:
                    clean_attrs.append(f'{k if kl != "viewbox" else "viewBox"}="{html_lib.escape(val, quote=True)}"')

        attr_str = (" " + " ".join(clean_attrs)) if clean_attrs else ""
        if t in _VOID_TAGS:
            self.out.append(f"<{t}{attr_str} />")
        else:
            self.out.append(f"<{t}{attr_str}>")

    def handle_endtag(self, tag: str):
        raw_t = tag.lower()
        if raw_t in _FORBIDDEN_TAGS:
            raise ValueError(f"暂不支持富文本标签：</{raw_t}>")
        if raw_t in _UNWRAP_TAGS or _NS_TAG_RE.match(raw_t) or raw_t == "input":
            return
        if raw_t == "option":
            self.out.append("]</span> ")
            return
        if raw_t in ("audio", "video"):
            self.out.append("</span>")
            return
        t = _ALIAS_TAGS.get(raw_t, raw_t)
        if t not in _ALLOWED_TAGS and t not in _MATHML_TAGS and t not in _SVG_TAGS:
            if raw_t in self._escaped_unknown_stack:
                self._escaped_unknown_stack.remove(raw_t)
                self._emit_literal(f"</{tag}>")
            return
        if t not in _VOID_TAGS:
            self.out.append(f"</{t}>")

    def handle_data(self, data: str):
        if _ZERO_WIDTH_RE.sub("", data):
            self.has_visible_content = True
        self.out.append(html_lib.escape(data, quote=False))

    def handle_entityref(self, name: str):
        if name.lower() not in _BLANK_ENTITY_NAMES:
            self.has_visible_content = True
        self.out.append(f"&{name};")

    def handle_charref(self, name: str):
        try:
            cp = int(name[1:], 16) if name.lower().startswith("x") else int(name, 10)
        except ValueError:
            cp = -1
        if cp not in _BLANK_CODEPOINTS and not (cp >= 0 and chr(cp).isspace()):
            self.has_visible_content = True
        self.out.append(f"&#{name};")


def sanitize_rich_html(raw_html: str) -> str:
    """校验并净化受限富文本 HTML；空内容或危险标签/未授权外链图片会直接抛错。"""
    if not isinstance(raw_html, str) or not raw_html.strip():
        raise ValueError("富文本内容为空")
    cleaned = _preclean_office_html(raw_html)
    parser = _StrictHtmlSanitizer(cleaned.lower())
    parser.feed(cleaned)
    parser.close()
    if not parser.has_visible_content:
        raise ValueError("富文本没有可见内容，无法确认题目或答案完整")
    return "".join(parser.out)


def has_visible_rich_content(raw_html: str) -> bool:
    """判断可选富文本字段（如解析）是否包含可见正文或图片，排除纯换行/空格占位。"""
    stripped = (raw_html or "").strip()
    if not stripped:
        return False
    cleaned = _preclean_office_html(stripped)
    if "<" in cleaned and ">" in cleaned:
        try:
            sanitize_rich_html(cleaned)
            return True
        except ValueError as exc:
            msg = str(exc)
            if "没有可见内容" in msg or "内容为空" in msg:
                return False
            raise
    return bool(_ZERO_WIDTH_RE.sub("", cleaned))


def _render_text_or_html(val: str) -> tuple[str, bool]:
    """若含受限 HTML 标签则按富文本净化，否则按纯文本转义。"""
    stripped = (val or "").strip()
    if not stripped:
        raise ValueError("内容为空")
    if "<" in stripped and ">" in stripped:
        return sanitize_rich_html(stripped), True
    return html_lib.escape(stripped), False


def validate_questions(questions: Iterable[Question]) -> list[Question]:
    items = list(questions)
    if not items:
        raise ValueError("没有可导出的题目")
    seen_ids: set[str] = set()
    for idx, q in enumerate(items, 1):
        if not q.id or not str(q.id).strip():
            raise ValueError(f"第 {idx} 题缺少题目 ID")
        if q.id in seen_ids:
            raise ValueError(f"题目 ID 重复：{q.id}")
        seen_ids.add(q.id)
        if not (q.subject_html or "").strip():
            raise ValueError(f"第 {idx} 题（ID={q.id}）缺少题干")
        if not (q.answer or "").strip():
            raise ValueError(f"第 {idx} 题（ID={q.id}）缺少答案")
        if q.is_choice and len(q.options) > 26:
            raise ValueError(f"第 {idx} 题（ID={q.id}）选项超过 26 个，无法分配选项字母")
        for opt_idx, opt in enumerate(q.options):
            if not (opt.html or "").strip():
                raise ValueError(f"第 {idx} 题（ID={q.id}）第 {opt_idx + 1} 个选项为空")
    return items


def build_export_document_html(
    questions: list[Question],
    variant: str = "withAnswersRed",
    title: str = "题目与答案",
    smart_pagination: bool = True,
) -> str:
    """生成用于 A4 无损 PDF 渲染的完整 HTML（支持由用户选择是否开启防隔页分页）。"""
    items = validate_questions(questions)
    if variant not in ("withAnswersRed", "withAnswersPlain", "withoutAnswers"):
        raise ValueError(f"不支持的答案模式：{variant}")

    blocks: list[str] = []
    prev_group: tuple[str, str, str] | None = None

    for idx, q in enumerate(items, 1):
        group = (q.subject_name or "未分类学科", q.chapter_name or "未分类章节", q.question_type or "未分类题型")
        if group != prev_group:
            group_label = f"{group[0]} / {group[1]} / {group[2]}"
            if group_label != title:
                blocks.append(f"<h2>{html_lib.escape(group_label)}</h2>")
            prev_group = group

        stem_rendered, stem_rich = _render_text_or_html(q.subject_html)
        stem_cls = "content rich" if stem_rich else "content"

        opt_parts: list[str] = []
        if q.has_options and q.options:
            for o_idx, opt in enumerate(q.options):
                opt_rendered, opt_rich = _render_text_or_html(opt.html)
                is_correct = bool(opt.is_true and variant == "withAnswersRed")
                label = f'<span class="option-label">{chr(65 + o_idx)}.</span>' if q.is_choice else ""
                cls = "option correct" if is_correct else "option"
                body_cls = "option-body" + (" labeled" if label else "") + (" rich" if opt_rich else "")
                opt_parts.append(f'<div class="{cls}">{label}<div class="{body_cls}">{opt_rendered}</div></div>')

        answer_block = ""
        if variant != "withoutAnswers":
            ans_rendered, ans_rich = _render_text_or_html(q.answer)
            ans_cls = "content rich" if ans_rich else "content"
            answer_block = f'<div class="label">答案</div><div class="{ans_cls}">{ans_rendered}</div>'

        analysis_block = ""
        if variant != "withoutAnswers" and has_visible_rich_content(q.analysis_html or ""):
            ana_rendered, ana_rich = _render_text_or_html(q.analysis_html)
            ana_cls = "content rich" if ana_rich else "content"
            analysis_block = f'<div class="label">解析</div><div class="{ana_cls}">{ana_rendered}</div>'

        blocks.append(
            f'<article><h3>第 {idx} 题 <span>（{html_lib.escape(q.id)}）</span></h3>'
            f'<div class="{stem_cls}">{stem_rendered}</div>'
            f'{"".join(opt_parts)}'
            f'{answer_block}'
            f'{analysis_block}'
            f'</article>'
        )

    return (
        '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">'
        '<style>'
        '@page { size: A4; margin: 18mm 18mm; }'
        '@media screen { html, body { width: 174mm; max-width: 174mm; margin: 0 auto; padding: 0; } }'
        '* { box-sizing: border-box; }'
        'body { margin: 0; font-family: "Microsoft YaHei UI", "Microsoft YaHei", "Noto Sans SC", "PingFang SC", sans-serif; '
        'font-size: 10.5pt; line-height: 1.72; color: #111827; overflow-wrap: anywhere; background: #fff; }'
        'h1 { font-size: 15pt; font-weight: 700; margin: 0 0 12pt; padding-bottom: 8pt; border-bottom: 1.5px solid #e5e7eb; color: #0f172a; }'
        'h2 { font-size: 12pt; font-weight: 700; margin: 14pt 0 8pt; color: #1e293b; background: #f8fafc; border-left: 3px solid #2563eb; padding: 4.5pt 8pt; border-radius: 4px; break-after: avoid; }'
        'h3 { font-size: 10.5pt; font-weight: 700; margin: 10pt 0 4pt; break-after: avoid; color: #0f172a; }'
        'h3 span { color: #64748b; font-weight: normal; font-size: 8.5pt; }'
        '.content, .option { white-space: pre-wrap; font-size: 10.5pt; line-height: 1.72; }'
        '.rich, .rich *:not(sub):not(sup), .content *:not(sub):not(sup), .option-body, .option-body *:not(sub):not(sup) { '
        'font-family: inherit !important; font-size: 10.5pt !important; line-height: 1.72 !important; }'
        'sub, sup { font-size: 7.5pt !important; line-height: 0 !important; }'
        '.rich { white-space: normal; }'
        '.rich p { margin: 0 0 4pt; }'
        '.option { margin: 3.5pt 0 3.5pt 0.8em; padding: 2pt 6pt; border-radius: 4px; }'
        '.option.correct { color: #b91c1c; font-weight: 600; background: #fef2f2; border-left: 2.5px solid #ef4444; }'
        '.option-label { display: inline-block; min-width: 1.8em; font-weight: 600; }'
        '.option-body { display: inline; }'
        '.option-body.rich p:first-child { display: inline; }'
        'img { max-width: 100%; height: auto; vertical-align: middle; }'
        'svg { max-width: 100%; height: auto; vertical-align: middle; }'
        '.inline-ctrl { display: inline-block; padding: 0 3px; border: 1px solid #cbd5e1; border-radius: 3px; background: #f8fafc; font-size: 9.5pt; margin: 0 2px; }'
        'table { border-collapse: collapse; max-width: 100%; margin: 6pt 0; font-size: 9.5pt; }'
        'td, th { border: 1px solid #cbd5e1; padding: 4px 7px; font-size: 9.5pt !important; }'
        '.label { display: block; width: fit-content; margin: 7pt 0 3pt; padding: 1pt 6pt; border-radius: 4px; background: #ecfdf5; border: 1px solid #a7f3d0; font-weight: 700; font-size: 9pt; color: #047857; break-after: avoid; page-break-after: avoid; }'
        'article { margin-bottom: 12pt; padding-bottom: 8pt; border-bottom: 1px dashed #e2e8f0; }'
        'article:last-child { border-bottom: none; }'
        '</style></head>'
        f'<body data-smart-pagination="{"1" if smart_pagination else "0"}"><h1>{html_lib.escape(title)}</h1>{"".join(blocks)}</body></html>'
    )


def safe_archive_segment(value: str) -> str:
    """净化 ZIP 目录与文件名片段，兼容 Windows 保留名与非法字符。"""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", (value or "").strip())
    cleaned = cleaned.rstrip(". ").strip()[:60]
    if not cleaned or cleaned in (".", ".."):
        cleaned = "未命名"
    if re.match(r"^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)", cleaned, re.I):
        cleaned = f"_{cleaned}"
    return cleaned


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
