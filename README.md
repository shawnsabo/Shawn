# 融智导出 Studio · 统一桌面端与安卓端题库无损导出套件

> 桌面端（Windows PySide6 + Chromium/Edge + QtWebEngine）与安卓端（Kotlin Jetpack Compose）统一排版管线  
> 离线验证码 OCR · 全量分页完整性核对 · A4 10.5pt 统一字号与公式等比排版

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 直接运行成品

前往 [v4.0.0 发布页面](https://github.com/shawnsabo/Shawn/releases/tag/v4.0.0) 下载成品；源码仓库不包含 `成品/` 文件夹中的安装包：

- `CCTRCloudExportDesktop.exe`：Windows 桌面版独立单文件程序（内置 `ddddocr` 离线自动识别验证码、浏览器内核自选与便携 Chromium 下载）。
- `CCTRCloudExportAndroid.apk`：Android 移动端安装包（内置 ONNX 离线自动识别验证码、A4 无损 PDF 与分类 ZIP 导出）。

---

## 核心特性

1. **离线验证码 OCR**：Windows 使用内置的 `ddddocr`，安卓使用内置 ONNX 模型。应用获取图形验证码后，在设备上自动识别并填写，可手动修正。识别无需调用云端 OCR 服务，获取验证码和登录仍需联网。
2. **统一排版与字号控制**：自动剥离原始富文本中的混杂 `font-size` / `font-family`，正文严格统一为 `10.5pt`（保留 `sub`/`sup` 上下标），对 Wiris 内联 SVG 与高分辨率 Word 截屏公式图按视觉比例等比缩放，标准 A4 四周 `18mm` 留白。
3. **智能分页与完整性校验**：导出设置中的「智能防隔页分页」默认开启，尽量避免常规题目跨页拆分；超长题目可跨页续排，关闭后使用紧凑连续分页。导出时核对平台分页总数，等待图片和公式加载，分类 ZIP 附带 SHA-256 `导出清单.json`。
4. **导出不掉线、目录零冗余**：支持自选默认保存目录（默认 `Documents/CCTRExport` / 手机 `Download/CCTRExport`），PDF/ZIP 直接输出清晰命名文件，不生成空数字子目录；导出完成后保留当前登录会话与课程列表。
5. **渲染内核自选**：桌面端支持自动优选 / Edge / Chrome / 便携 Chromium（支持一键下载）与内置 QtWebEngine 兜底。

---

## 仓库结构

```text
cctr_export/            桌面端源码（PySide6 WebView + Core 引擎）
  ├─ core/              API、验证码 OCR、富文本/PDF 完整性校验、内核管理、任务引擎
  └─ ui/                Quiet Paper & Indigo Ink Studio 界面与 WebChannel 桥接
android/                安卓端源码（Kotlin + Jetpack Compose + ONNX OCR）
desktop/                桌面端 PyInstaller 单文件打包脚本
design/                 Figma 设计系统与交付说明
tests/                  Python 自动化单元测试与 PDF 完整性测试
main.py                 桌面端入口
```

---

## 从源码开发与打包

### 桌面端

```bat
python -m pip install -r requirements.txt
python main.py
```

单文件构建：`desktop\build_desktop.bat`（输出到 `成品\CCTRCloudExportDesktop.exe`）。

### 安卓端

```bat
android\gradlew.bat -p android testDebugUnitTest assembleDebug
```

---

## 致谢与免责声明

- 桌面端创建导出任务时，会在本机 `~/.cctr_export/tasks.db` 中保存账号、密码和登录会话信息，请妥善保护该文件。
- 本工具仅供个人学习与课程资料整理使用，请遵守所在学校与平台规范。
- 原始桌面工具来源：[shawnsabo](https://github.com/shawnsabo)
