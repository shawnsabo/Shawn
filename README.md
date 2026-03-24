# CCTRCloud Export Desktop

基于 Python + PySide6 的 CCTRCloud 题目导出桌面工具，从 Kotlin/Compose 版本重建。

## 功能

- 🔐 登录 CCTRCloud 账号（RSA 加密）
- 📋 获取练习列表、章节、题型
- 📸 将题目 HTML 渲染为图片
- 📄 导出为 PNG / PDF
- 📦 自动打包 ZIP
- ⚙️ Edge WebDriver 自动管理
- 📝 任务队列管理（等待/运行/成功/失败）
- 🔄 失败任务重试
- 📊 实时日志查看
- 🌙 深色主题

## 安装

```bash
cd cctr2
pip install -r requirements.txt
```

## 运行

```bash
python main.py
```

## 使用流程

1. 点击右下角 **＋** 按钮添加任务
2. 填写学校编号、用户名、密码，点击登录
3. 选择要导出的练习
4. 按需选择章节和题型（留空=全部）
5. 选择导出格式（PDF/PNG）
6. 点击"创建并运行任务"
7. 在任务列表中查看进度，日志页面查看详细日志

## 输出目录

导出文件位于 `~/.cctr_export/output/`

## 技术栈

- Python 3.14
- PySide6 (Qt)
- httpx (HTTP 客户端)
- Selenium + Edge WebDriver (HTML 渲染)
- pycryptodome (RSA 加密)
- Pillow + img2pdf (图片处理)
- SQLite (任务存储)
