# CCTRCloud Export Portable

> 融智云考（CCTRCloud）题库导出 · 单文件便携版
> Designed by Silvite and Shawnmark

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Platform](https://img.shields.io/badge/platform-Windows%2010%2F11-blue)

**单 exe · 免安装 · 免 Python 环境 · 登录验证码自动识别。**

基于官方 Rust 应用 `CCTRCloudExportRust v3` 的增强便携版：题库导出管线
100% 保留官方实现（浏览器渲染 PDF、manifest、ZIP），仅在登录环节补上
官方版本缺失的两块拼图。

---

## 背景：官方 v3 为什么登录不了

官方 Rust v3 构建于平台的两次变更之前，登录功能已经失效：

1. **登录验证码被服务端强制** —— 实测对所有 `client` 值均无豁免；
2. **内嵌 RSA 公钥已被服务端弃用**（公钥轮换），密码密文无法解密。

本工具不修改官方程序的任何业务逻辑，只在网络层与展示层补齐这两点，
让官方管线原样跑起来。

## 快速开始

1. 双击 `CCTRCloudExportPortable.exe`（无需安装任何依赖）
2. 自动弹出融智云考导出窗口，登录验证码自动识别（识别失败可手动输入）
3. 填学校代码 / 账号 / 密码 → 登录 → 选择练习 → 确认导出
4. ZIP 输出在 `~/.cctr_export_v3/`

## 工作原理

```
CCTRCloudExportPortable.exe（单文件）
  ├─ 释放内嵌官方 Rust 应用 → 两处等长内存补丁
  │    ├─ API 基址 → http://127.0.0.1:8899（本地代理）
  │    └─ RSA 公钥 → 现行版本（取自官方 Web 端 config.js）
  ├─ 本地代理转发全部 API 流量
  │    └─ 仅截获登录请求：用请求自带会话 Cookie 获取验证码
  │       → ddddocr 本地 OCR → 自动补 captcha 参数 → 转发
  ├─ WebView2 CDP 将验证码行注入官方登录界面（OCR 失败可手输）
  └─ OCR 连续失败 3 次 → 自动转人工确认对话框
```

- 官方应用的导出逻辑、渲染管线、打包方式**零改动**；
- 所有网络流量仅经过本机回环地址，不经过任何第三方；
- 原 exe 永不落地修改，补丁副本每次启动时在临时目录重建。

## 仓库结构

```
cctr_export/             桌面版（PySide6，Element Plus 风格 UI）
  ├─ core/               登录（含验证码参数）/ 抓题 / 渲染 / 任务引擎
  ├─ platforms/          题库平台抽象层
  └─ ui/                 桌面界面
portable/                单文件便携版构建源
  ├─ launcher_portable.py   便携版核心（代理 + OCR + CDP 注入 + 补丁）
  ├─ build.bat              一键构建脚本
  └─ requirements-build.txt 构建依赖
main.py                  桌面版入口
```

## 从源码构建便携版

前置：Windows 10/11、Python 3.10+；将官方原版
`CCTRCloudExportRust-v3.exe` 与 `WebView2Loader.dll` 放到仓库根目录。

```bat
portable\build.bat
```

产物：`portable\dist\CCTRCloudExportPortable.exe`

桌面版（可选）：

```bat
pip install -r requirements.txt
python main.py
```

---

## 免责声明

本品开源以便利学生为目的，**不建议也不鼓励** 以此进行任何
**盈利性操作**。如产生任何问题均由使用者自行承担。
请遵守所在学校与平台的相关规定。

## 致谢

- Designed by **Silvite** and **Shawnmark**
- 原始桌面工具与 Rust 应用：[shawnsabo](https://github.com/shawnsabo)
- UI 规范：[Element Plus](https://element-plus.org/) / Apple HIG（历史版本）

---

如果你觉得这个项目对你有帮助，欢迎 **给个 Star ⭐**
