/* 登录表单图形验证码注入
 * 在「填账号」步骤的表单末尾追加验证码行（图片 + 输入框，点击图片刷新），
 * 样式使用前端自带 CSS 变量，与原生观感一致。
 * 前端资产文件本身未做任何修改，本脚本由外壳注入。 */
(function () {
  "use strict";

  var ROW_ID = "__cctr_captcha_row";
  var reloading = false;

  function findForm() {
    return document.querySelector(".wizard-body .form") || document.querySelector(".form");
  }

  function findPasswordInput() {
    var labels = document.querySelectorAll(".form label");
    for (var i = 0; i < labels.length; i++) {
      var input = labels[i].querySelector('input[type="password"]');
      if (input) return input;
    }
    return null;
  }

  function ensureUI() {
    if (document.getElementById(ROW_ID)) return true;
    var form = findForm();
    if (!form || !findPasswordInput()) return false;

    var row = document.createElement("div");
    row.id = ROW_ID;
    row.style.cssText = "margin-top:2px;display:grid;gap:7px;";
    row.innerHTML =
      '<span style="color:#334155;font-size:13px;font-weight:650;">验证码</span>' +
      '<div style="display:flex;gap:10px;align-items:center;">' +
      '<input id="__cctr_captcha_input" maxlength="8" autocomplete="off" placeholder="输入右侧 4 位字符"' +
      ' style="flex:1;min-height:40px;border:1px solid var(--line);border-radius:8px;' +
      'background:var(--surface);color:var(--ink);padding:0 12px;outline:none;" />' +
      '<img id="__cctr_captcha_img" alt="验证码加载中" title="看不清？点击图片刷新"' +
      ' style="height:40px;min-width:110px;border:1px solid var(--line);border-radius:8px;' +
      'cursor:pointer;background:#fff;" />' +
      "</div>";
    // 追加在表单末尾（React 兄弟节点之间的外来节点有重渲染风险，末尾位置最安全）
    form.appendChild(row);

    var input = row.querySelector("#__cctr_captcha_input");
    var img = row.querySelector("#__cctr_captcha_img");
    input.addEventListener("input", function () {
      window.__TAURI_INTERNALS__.invoke("set_captcha", { code: input.value }).catch(function () {});
    });
    img.addEventListener("click", function () { reload(); });
    syncDisabled();
    reload();
    return true;
  }

  function syncDisabled() {
    var row = document.getElementById(ROW_ID);
    if (!row) return;
    var pwd = findPasswordInput();
    var input = row.querySelector("input");
    if (pwd && input) input.disabled = pwd.disabled;
  }

  function reload() {
    if (reloading) return;
    reloading = true;
    var img = document.getElementById("__cctr_captcha_img");
    if (img) img.alt = "验证码加载中";
    window.__TAURI_INTERNALS__.invoke("get_captcha").then(function (res) {
      var img2 = document.getElementById("__cctr_captcha_img");
      if (img2 && res && res.image) img2.src = res.image;
      reloading = false;
    }).catch(function () {
      var img2 = document.getElementById("__cctr_captcha_img");
      if (img2) img2.alt = "加载失败，点击重试";
      reloading = false;
    });
  }

  // 登录失败（任意错误）后：清空输入框 + 自动刷新验证码（服务端已作废旧码）
  var internals = window.__TAURI_INTERNALS__;
  var origInvoke = internals.invoke;
  internals.invoke = function (cmd, args, opts) {
    var p = origInvoke.call(internals, cmd, args, opts);
    if (cmd === "auth_login") {
      p.catch(function () {
        var input = document.getElementById("__cctr_captcha_input");
        if (input) input.value = "";
        reload();
      });
    }
    return p;
  };

  var mo = new MutationObserver(function () {
    if (!ensureUI()) return;
    syncDisabled();
  });

  function start() {
    ensureUI();
    mo.observe(document.body, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
