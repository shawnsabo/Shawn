"""内置浏览器网页捕获与加密字体解密（支持超星学习通 font-cxsecret 与雨课堂）"""
from __future__ import annotations

import base64
import html as html_lib
import re
import struct
from typing import Any

from .captcha_ocr import recognize_single_char
from .integrity import is_choice_question, sanitize_rich_html, validate_questions
from .models import Option, Question

PLATFORM_PRESETS: dict[str, tuple[str, str]] = {
    "chaoxing": ("超星学习通", "https://i.chaoxing.com"),
    "yuketang": ("雨课堂（标准版）", "https://www.yuketang.cn/web"),
    "yuketang_cj": ("长江雨课堂", "https://changjiang.yuketang.cn/web"),
    "yuketang_ht": ("荷塘雨课堂", "https://hetang.yuketang.cn/web"),
    "yuketang_hh": ("黄河雨课堂", "https://huanghe.yuketang.cn/web"),
}

_TAG_SPLIT_RE = re.compile(r"(<[^>]+>)")

XHR_INTERCEPT_JS = r"""
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
      if (window.__cctrApiPayloads.length > 25) {
        window.__cctrApiPayloads.shift();
      }
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
          if (text && text.trim().startsWith('{')) {
            pushPayload(this.__cctrUrl, JSON.parse(text));
          }
        }
      } catch (e) {}
    });
    return origSend.apply(this, arguments);
  };
})();
"""

DETECT_PAGE_STATUS_JS = r"""
(function() {
  function collectWins(win, depth, out) {
    if (!win || depth > 4) return;
    out.push(win);
    try {
      const frames = win.frames || [];
      for (let i = 0; i < frames.length; i++) {
        try {
          void frames[i].document.title;
          collectWins(frames[i], depth + 1, out);
        } catch (e) {}
      }
    } catch (e) {}
  }
  const wins = [];
  collectWins(window, 0, wins);
  let cxCount = 0;
  let yktDomCount = 0;
  let yktApiCount = 0;
  let pageTitle = document.title || '';
  for (const w of wins) {
    try {
      const d = w.document;
      cxCount += d.querySelectorAll('.TiMu, .questionLi, .singleQuestion, div[id^="sigleQuestionDiv"]').length;
      yktDomCount += d.querySelectorAll('.subject-item, .problem-item, .question-item, .exam-item, .exercise-item').length;
      const payloads = w.__cctrApiPayloads || [];
      for (const p of payloads) {
        const dt = (p.data && p.data.data) ? p.data.data : p.data;
        if (dt && Array.isArray(dt.problems)) yktApiCount = Math.max(yktApiCount, dt.problems.length);
      }
    } catch (e) {}
  }
  const host = (location.hostname || '').toLowerCase();
  let hint = '通用网页';
  if (/chaoxing|xuexitong/.test(host) || cxCount > 0) hint = '超星学习通';
  else if (/yuketang|xuetangx/.test(host) || yktApiCount > 0 || yktDomCount > 0) hint = '雨课堂';
  const estCount = Math.max(cxCount, yktApiCount, yktDomCount);
  return JSON.stringify({
    hasQuestions: estCount > 0,
    platformHint: hint,
    estCount: estCount,
    pageTitle: pageTitle
  });
})();
"""

EXTRACT_QUESTIONS_JS = r"""
(async function() {
  function collectWins(win, depth, out) {
    if (!win || depth > 4) return;
    out.push(win);
    try {
      const frames = win.frames || [];
      for (let i = 0; i < frames.length; i++) {
        try {
          void frames[i].document.title;
          collectWins(frames[i], depth + 1, out);
        } catch (e) {}
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
        const tag = String.fromCharCode(
          dv.getUint8(rec), dv.getUint8(rec + 1), dv.getUint8(rec + 2), dv.getUint8(rec + 3)
        );
        if (tag === 'cmap') {
          cmapOff = dv.getUint32(rec + 8, false);
          break;
        }
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
            for (let cp = startC; cp <= lim; cp++) {
              if (cp > 0x20 && cp !== 0xFFFF) cps.add(cp);
            }
          }
        } else if (fmt === 12 && subOff + 16 <= dv.byteLength) {
          const numGrp = dv.getUint32(subOff + 12, false);
          for (let g = 0; g < numGrp; g++) {
            const gOff = subOff + 16 + g * 12;
            if (gOff + 12 > dv.byteLength) break;
            const sc = dv.getUint32(gOff, false);
            const ec = dv.getUint32(gOff + 4, false);
            const lim = Math.min(ec, sc + 12000);
            for (let cp = sc; cp <= lim; cp++) {
              if (cp > 0x20) cps.add(cp);
            }
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
        try {
          const abs = new URL(rawSrc, baseHref).href;
          img.setAttribute('src', abs);
        } catch (e) {}
      }
      // 尝试将跨域风险的同源/CORS图片或 blob: 图直接画成 data URL 避免后续拦截
      const curSrc = img.getAttribute('src') || '';
      if (/^blob:/i.test(curSrc)) {
        try {
          const cv = document.createElement('canvas');
          cv.width = img.naturalWidth || 120;
          cv.height = img.naturalHeight || 60;
          const ctx = cv.getContext('2d');
          ctx.drawImage(img, 0, 0);
          img.setAttribute('src', cv.toDataURL('image/png'));
        } catch (e) {}
      }
    });
    return clone.innerHTML.trim();
  }

  function txtOf(el) {
    return (el && (el.innerText || el.textContent) || '').trim();
  }

  const wins = [];
  collectWins(window, 0, wins);

  const host = (location.hostname || '').toLowerCase();
  const isChaoxingHost = /chaoxing|xuexitong/.test(host);
  const isYuketangHost = /yuketang|xuetangx/.test(host);

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

    try {
      if (doc.fonts && doc.fonts.ready) await doc.fonts.ready;
    } catch (e) {}

    // 1) 扫描 @font-face 中的混淆字体（font-cxsecret / 雨课堂字体）
    try {
      const styles = Array.from(doc.querySelectorAll('style')).map(s => s.textContent || '');
      try {
        for (const ss of Array.from(doc.styleSheets || [])) {
          try {
            for (const rule of Array.from(ss.cssRules || [])) {
              if (rule.type === CSSRule.FONT_FACE_RULE) {
                styles.push(rule.cssText || '');
              }
            }
          } catch (e) {}
        }
      } catch (e) {}

      for (const cssText of styles) {
        const ffBlocks = cssText.match(/@font-face\s*\{[^}]*\}/gi) || [];
        for (const blk of ffBlocks) {
          const famM = blk.match(/font-family\s*:\s*['"]?([^'";}]+)['"]?/i);
          const fam = famM ? famM[1].trim() : '';
          const b64M = blk.match(/data:[^;]*font[^;]*;base64,([A-Za-z0-9+/=]+)/i);
          const urlM = blk.match(/url\(['"]?(https?:[^'")\s]+\.ttf[^'")\s]*)['"]?\)/i);
          if (/cxsecret|ykt|yuketang|encrypt|secret/i.test(fam) || b64M) {
            if (fam && !secretFontFamilies.includes(fam)) secretFontFamilies.push(fam);
            if (b64M) {
              parseTtfCmap(decodeBase64Bytes(b64M[1])).forEach(cp => secretCodepoints.add(cp));
            } else if (urlM && !apiFontUrl) {
              apiFontUrl = urlM[1];
            }
          }
        }
      }
    } catch (e) {}

    // 2) 检查雨课堂 / 通用 API 截获包
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
        const rawOpts = pr.Options || pr.options || [];
        const opts = [];
        for (const o of rawOpts) {
          const val = typeof o === 'string' ? o : String(o.value || o.name || o.text || o.html || '');
          if (val.trim()) opts.push({ isTrue: !!(o && (o.isCorrect || o.is_true)), html: val.trim() });
        }
        let ans = pr.Answer ?? pr.answer ?? '';
        if (Array.isArray(ans)) ans = ans.join('、');
        else if (ans && typeof ans === 'object') ans = Object.values(ans).join('；');
        items.push({
          id: String(pr.ProblemID || pr.problem_id || pr.id || ('ykt:' + (items.length + 1))),
          questionType: qtype,
          stemHtml: stem,
          options: opts,
          answerHtml: String(ans || '').trim(),
          analysisHtml: String(pr.Remark || pr.analysis || '').trim(),
          chapterName: String(dt.name || '雨课堂作业')
        });
      }
      matchedApi = true;
      break;
    }
    if (matchedApi) continue;

    // 3) 超星学习通 DOM 解析（兼容章节测验 .TiMu 与新版作业/考试 .questionLi / .singleQuestion）
    const cxNodes = Array.from(doc.querySelectorAll('.TiMu, .questionLi, .singleQuestion, div[id^="sigleQuestionDiv"]'));
    const topCx = cxNodes.filter(el => !cxNodes.some(other => other !== el && other.contains(el)));
    if (topCx.length > 0) {
      topCx.forEach((el, idx) => {
        el.querySelectorAll('.font-cxsecret, [style*="font-cxsecret"]').forEach(fn => {
          for (const ch of txtOf(fn)) {
            if (ch.codePointAt(0) > 127) secretCharTexts.add(ch);
          }
          if (!secretFontFamilies.includes('font-cxsecret')) secretFontFamilies.push('font-cxsecret');
        });
        const titleEl = el.querySelector('.Zy_TItle .clearfix, .Zy_TItle, .newZy_TItle, .mark_name, h3.mark_name');
        let stemHtml = cleanHtmlNode(titleEl || el.querySelector('.stem, .title'), baseHref);
        if (!stemHtml) return;

        let qtype = '';
        const typeEl = el.querySelector('.colorShallow, .newZy_TItle span, .type_tit, .mark_name span');
        if (typeEl) {
          const m = txtOf(typeEl).match(/(单选(?:题)?|多选(?:题)?|判断(?:题)?|填空(?:题)?|简答(?:题)?|论述(?:题)?|计算(?:题)?)/);
          if (m) qtype = m[1];
        }

        const optEls = Array.from(el.querySelectorAll('ul.mark_letter li, .qtDetail li, .Zy_ulTop li, .mark_answer .answer_p, .stem_answer .answerBg'));
        const opts = [];
        for (const o of optEls) {
          const h = cleanHtmlNode(o, baseHref);
          if (h) opts.push({ isTrue: false, html: h });
        }

        let ansHtml = '';
        let anaHtml = '';
        const ansNodes = Array.from(el.querySelectorAll('.Py_answer, .mark_answer, .mark_key, .newAnswer, .analysisDiv'));
        for (const an of ansNodes) {
          const rightEl = an.querySelector('.rightAnswerContent, .colorGreen, .mark_fill dd');
          if (rightEl && !ansHtml) ansHtml = cleanHtmlNode(rightEl, baseHref);
          const anaEl = an.querySelector('.analysisInfo, .Py_tk, .mark_jx, .answerAnalysis');
          if (anaEl && !anaHtml) anaHtml = cleanHtmlNode(anaEl, baseHref);
          const rawT = txtOf(an);
          if (!ansHtml && /正确答案\s*[:：]/.test(rawT)) {
            ansHtml = rawT.split(/正确答案\s*[:：]/)[1].split(/\n|我的答案|答案解析/)[0].trim();
          }
          if (!anaHtml && /答案解析\s*[:：]/.test(rawT)) {
            anaHtml = rawT.split(/答案解析\s*[:：]/)[1].trim();
          }
        }
        items.push({
          id: String(el.getAttribute('data') || el.id || ('cx:' + (idx + 1))),
          questionType: qtype || (opts.length > 0 ? '单选题' : '简答题'),
          stemHtml: stemHtml,
          options: opts,
          answerHtml: ansHtml,
          analysisHtml: anaHtml,
          chapterName: pageTitle || '超星学习通'
        });
      });
      continue;
    }

    // 4) 雨课堂 DOM / 通用题库 DOM 兜底
    const yktNodes = Array.from(doc.querySelectorAll('.subject-item, .problem-item, .question-item, .exam-item, .exercise-item, [class*="question-item"]'));
    const topYkt = yktNodes.filter(el => !yktNodes.some(other => other !== el && other.contains(el)));
    if (topYkt.length > 0) {
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
          stemHtml: stemHtml,
          options: opts,
          answerHtml: cleanHtmlNode(ansEl, baseHref),
          analysisHtml: cleanHtmlNode(anaEl, baseHref),
          chapterName: pageTitle || '网页提取'
        });
      });
    }
  }

  // 若发现外部 TTF URL 且尚未解析 cmap，尝试同源拉取解析
  if (apiFontUrl && secretCodepoints.size === 0) {
    try {
      const r = await fetch(apiFontUrl);
      if (r.ok) {
        const buf = new Uint8Array(await r.arrayBuffer());
        parseTtfCmap(buf).forEach(cp => secretCodepoints.add(cp));
      }
    } catch (e) {}
  }

  // 仅渲染实际在提取结果中出现过的混淆字符（每字 64x64 黑字白底，供端侧 ONNX 精确还原）
  const usedChars = new Set();
  const stripTags = (s) => String(s || '').replace(/<[^>]+>/g, '');
  for (const it of items) {
    const blobs = [stripTags(it.stemHtml), stripTags(it.answerHtml), stripTags(it.analysisHtml)];
    for (const o of (it.options || [])) blobs.push(stripTags(o.html));
    for (const b of blobs) {
      for (const ch of b) {
        const cp = ch.codePointAt(0);
        if (cp > 127 && (secretCodepoints.has(cp) || secretCharTexts.has(ch))) {
          usedChars.add(ch);
        }
      }
    }
  }

  const secretGlyphs = [];
  if (usedChars.size > 0 && secretFontFamilies.length > 0) {
    const cv = document.createElement('canvas');
    cv.width = 64;
    cv.height = 64;
    const ctx = cv.getContext('2d');
    const famStr = secretFontFamilies.map(f => `"${f.replace(/"/g, '')}"`).join(', ') + ', serif';
    for (const ch of Array.from(usedChars).slice(0, 600)) {
      ctx.fillStyle = '#FFFFFF';
      ctx.fillRect(0, 0, 64, 64);
      ctx.fillStyle = '#000000';
      ctx.font = '42px ' + famStr;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(ch, 32, 34);
      const dataUrl = cv.toDataURL('image/png');
      const b64 = dataUrl.split(',')[1] || '';
      if (b64) secretGlyphs.push({ char: ch, pngBase64: b64 });
    }
  }

  const platform = isChaoxingHost ? '超星学习通' : (isYuketangHost ? '雨课堂' : '网页捕获');
  return JSON.stringify({
    ok: items.length > 0,
    error: items.length > 0 ? '' : '当前页面未检测到题目节点，请进入具体的“作业/测验/练习”详情页后再提取',
    title: pageTitle || (platform + '题库'),
    sourceLabel: platform,
    platform: platform,
    items: items,
    secretGlyphs: secretGlyphs
  });
})();
"""


def parse_ttf_cmap_codepoints(ttf_bytes: bytes) -> set[int]:
    """解析 TrueType 字体文件 cmap 表（Format 4 & 12）包含的非空白 Unicode 码点集合。"""
    cps: set[int] = set()
    if len(ttf_bytes) < 12:
        return cps
    num_tables = struct.unpack_from(">H", ttf_bytes, 4)[0]
    cmap_off = -1
    for i in range(num_tables):
        rec = 12 + i * 16
        if rec + 16 > len(ttf_bytes):
            break
        tag = ttf_bytes[rec:rec + 4]
        if tag == b"cmap":
            cmap_off = struct.unpack_from(">I", ttf_bytes, rec + 8)[0]
            break
    if cmap_off < 0 or cmap_off + 4 > len(ttf_bytes):
        return cps
    num_sub = struct.unpack_from(">H", ttf_bytes, cmap_off + 2)[0]
    for i in range(num_sub):
        srec = cmap_off + 4 + i * 8
        if srec + 8 > len(ttf_bytes):
            break
        sub_off = cmap_off + struct.unpack_from(">I", ttf_bytes, srec + 4)[0]
        if sub_off + 14 > len(ttf_bytes):
            continue
        fmt = struct.unpack_from(">H", ttf_bytes, sub_off)[0]
        if fmt == 4:
            seg_count = struct.unpack_from(">H", ttf_bytes, sub_off + 6)[0] >> 1
            end_start = sub_off + 14
            start_start = end_start + seg_count * 2 + 2
            if start_start + seg_count * 2 > len(ttf_bytes):
                continue
            for s in range(seg_count):
                end_c = struct.unpack_from(">H", ttf_bytes, end_start + s * 2)[0]
                start_c = struct.unpack_from(">H", ttf_bytes, start_start + s * 2)[0]
                if start_c == 0xFFFF and end_c == 0xFFFF:
                    continue
                for cp in range(start_c, min(end_c, start_c + 12000) + 1):
                    if cp > 0x20 and cp != 0xFFFF:
                        cps.add(cp)
        elif fmt == 12 and sub_off + 16 <= len(ttf_bytes):
            num_grp = struct.unpack_from(">I", ttf_bytes, sub_off + 12)[0]
            for g in range(num_grp):
                goff = sub_off + 16 + g * 12
                if goff + 12 > len(ttf_bytes):
                    break
                sc, ec = struct.unpack_from(">II", ttf_bytes, goff)
                for cp in range(sc, min(ec, sc + 12000) + 1):
                    if cp > 0x20:
                        cps.add(cp)
    return cps


def decrypt_glyph_list(secret_glyphs: list[dict[str, Any]]) -> dict[str, str]:
    """将浏览器渲染出的混淆字体字形 PNG 批量交给 ddddocr 还原为汉字映射表。"""
    mapping: dict[str, str] = {}
    for entry in secret_glyphs or []:
        ch = str(entry.get("char") or "")
        b64 = str(entry.get("pngBase64") or "")
        if not ch or not b64 or ch in mapping:
            continue
        try:
            png_bytes = base64.b64decode(b64)
            decoded = recognize_single_char(png_bytes)
            if decoded:
                mapping[ch] = decoded
        except Exception:
            continue
    return mapping


def apply_glyph_map_to_html(raw_html: str, mapping: dict[str, str]) -> str:
    """只替换 HTML 标签之外的纯文本节点，避免误伤属性/图片 base64 URL。"""
    if not raw_html or not mapping:
        return raw_html or ""
    out: list[str] = []
    for part in _TAG_SPLIT_RE.split(str(raw_html)):
        if not part:
            continue
        if part.startswith("<") and part.endswith(">"):
            out.append(part)
        else:
            out.append("".join(mapping.get(c, c) for c in part))
    return "".join(out)


def _clean_captured_html(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    if "<" not in text:
        return text
    try:
        return sanitize_rich_html(text)
    except ValueError as exc:
        msg = str(exc)
        if "图片来源不在允许域" in msg:
            raise
        # 对第三方的非关键容器标签（如 label / figure / fieldset）退化为保留图文的安全 HTML/文本
        plain = html_lib.unescape(re.sub(r"<(?!img\b)[^>]+>", "", text, flags=re.I)).strip()
        return plain or html_lib.escape(re.sub(r"<[^>]+>", "", text)).strip()


def _strip_leading_opt_prefix(opt_html: str) -> str:
    return re.sub(r"^\s*(?:<span[^>]*>\s*)?[A-H]\s*[.、．)\）:：]?\s*(?:</span>\s*)?", "", opt_html, count=1, flags=re.I).strip()


def build_questions_from_capture(payload: dict[str, Any]) -> tuple[str, list[Question]]:
    """将浏览器抓包与字形识别结果转换为规范 Question 列表。"""
    if not payload.get("ok"):
        raise ValueError(payload.get("error") or "当前页面未提取到题目")

    mapping = decrypt_glyph_list(payload.get("secretGlyphs") or [])
    title = str(payload.get("title") or "网页捕获题库").strip() or "网页捕获题库"
    source_label = str(payload.get("sourceLabel") or payload.get("platform") or "网页捕获").strip()

    questions: list[Question] = []
    for idx, it in enumerate(payload.get("items") or [], 1):
        stem_dec = apply_glyph_map_to_html(str(it.get("stemHtml") or ""), mapping)
        stem_clean = _clean_captured_html(stem_dec)
        if not stem_clean:
            continue

        raw_qtype = apply_glyph_map_to_html(str(it.get("questionType") or ""), mapping).strip()
        raw_opts = it.get("options") or []
        opts: list[Option] = []
        for o in raw_opts:
            if isinstance(o, dict):
                oh = apply_glyph_map_to_html(str(o.get("html") or ""), mapping)
                oc = _clean_captured_html(_strip_leading_opt_prefix(oh))
                if oc:
                    opts.append(Option(is_true=bool(o.get("isTrue")), html=oc))
            elif o is not None:
                oc = _clean_captured_html(_strip_leading_opt_prefix(apply_glyph_map_to_html(str(o), mapping)))
                if oc:
                    opts.append(Option(is_true=False, html=oc))

        ans_dec = apply_glyph_map_to_html(str(it.get("answerHtml") or ""), mapping)
        ans_clean = _clean_captured_html(ans_dec)
        if not ans_clean and opts and any(o.is_true for o in opts):
            ans_clean = "、".join(chr(ord("A") + i) for i, o in enumerate(opts) if o.is_true)
        if not ans_clean:
            ans_clean = "略（当前页面未显示答案）"

        ana_dec = apply_glyph_map_to_html(str(it.get("analysisHtml") or ""), mapping)
        ana_clean = _clean_captured_html(ana_dec)

        qtype = raw_qtype or ("多选题" if len(re.findall(r"[A-H]", ans_clean)) > 1 and opts else ("单选题" if opts else "简答题"))
        choice = is_choice_question(qtype) or bool(opts)
        if choice and opts and not any(o.is_true for o in opts):
            letters = set(re.findall(r"[A-H]", re.sub(r"<[^>]+>", "", ans_clean).upper()))
            if letters:
                opts = [Option(is_true=(chr(ord("A") + i) in letters), html=o.html) for i, o in enumerate(opts)]

        chap = apply_glyph_map_to_html(str(it.get("chapterName") or title), mapping).strip() or title
        questions.append(
            Question(
                id=str(it.get("id") or f"web:{idx}"),
                question_type=qtype,
                subject_html=stem_clean,
                answer=ans_clean,
                has_options=bool(opts),
                options=opts,
                subject_name=source_label,
                chapter_name=chap,
                analysis_html=ana_clean,
                is_choice=choice,
            )
        )

    validate_questions(questions)
    return title, questions
