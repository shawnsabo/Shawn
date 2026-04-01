# CCTRCloud Export Desktop ⭐

> 沈阳理工大学课程格子(CCTRCloud) 导出工具 — 开源桌面版

[![GitHub stars](https://img.shields.io/github/stars/shawnsabo/Shawn?style=social)](https://github.com/shawnsabo/Shawn/stargazers)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## 功能

- 登录 CCTRCloud 账号（RSA 加密）
- 获取学习通课程列表、章节、作业
- 题目 HTML 渲染为图片 / 导出为 PNG / PDF
- 自动打包 ZIP
- Edge WebDriver 自动检测安装
- 任务状态：待处理 / 处理中 / 成功 / 失败
- 失败重试机制
- 实时日志查看
- 主题切换

## 使用方法

1. 点击主界面「登录学习通」按钮，按提示输入学校名、账号、密码并登录
2. 选择需要导出内容的课程
3. 选择章节范围（支持全选）
4. 选择导出格式：PDF / PNG
5. 点击「开始导出任务」
6. 在导出列表中查看进度，日志页面查看详细日志

> [!IMPORTANT]
> **免责声明**: 本品开源以便利学生为目的，
> **不建议也不鼓励** 以此进行任何 **盈利性操作**。
> 如产生任何问题均由使用者自行承担。

## 安装

```bash
pip install -r requirements.txt
python main.py
```

## 技术栈

- Python 3.14
- PySide6 (Qt)
- httpx (HTTP 客户端)
- Selenium + Edge WebDriver (HTML 渲染)
- pycryptodome (RSA 加密)
- Pillow + img2pdf (图片处理)
- SQLite (本地存储)

## 项目结构

```
cctr2/
├── main.py              # 应用入口
├── cctr_export/         # 核心导出模块
│   ├── login.py         # 登录 & RSA 加密
│   ├── fetcher.py       # 课程/章节数据获取
│   ├── renderer.py      # HTML 渲染为图片
│   ├── exporter.py       # PNG / PDF 导出
│   └── storage.py        # SQLite 状态管理
├── dist/
│   └── CCTRCloudExport.exe  # Windows 打包版
└── requirements.txt
```

## 输出目录

导出文件默认保存在 `~/.cctr_export/output/`

---

如果你觉得这个项目对你有帮助，欢迎 **给个 Star ⭐**，你的支持是我继续维护的动力！
