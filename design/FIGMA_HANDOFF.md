# 融智导出 Studio · Figma 设计系统与统一实现说明 (v4)

- **Figma 设计稿**: [Rongzhi Export Studio · Figma](https://www.figma.com/design/pPu0Lj18qSMfbyKjdLN9hz)
- **配额说明**: 当前 Figma Starter 团队当月 MCP 工具调用次数已用尽；界面令牌、组件与四帧骨架保存在上述链接中，桌面端与安卓端基于 **Quiet Paper & Indigo Ink** 设计系统 1:1 落地重构。

## 设计系统令牌 (Design Tokens)
| Token | 浅色 (Light) | 深色 (Dark) | 用途 |
| --- | --- | --- | --- |
| `--bg` | `#F6F7FB` | `#0B0E14` | 画布底色 |
| `--sidebar` | `#EEF1F7` | `#111520` | 228px 极简左侧导轨 |
| `--surface` | `#FFFFFF` | `#161B26` | 卡片与工作区表层 |
| `--primary` | `#4338CA` | `#6366F1` | 主强调色 (Indigo) |
| `--ok` | `#059669` | `#34D399` | 校验通过 / 完成状态 |
| `--border` | `rgba(15,23,42,0.08)` | `rgba(255,255,255,0.08)` | 发丝分割线 |

## 桌面端 v4 信息架构
1. **双区域单焦点架构**：移除旧版拥挤多栏边框卡片与常驻黑底日志框；左侧导轨承载 `导出工作台 / 导出记录 / 校验日志` 与底部目录/内核设置。
2. **导出不掉线**：提交与完成后保持登录会话与已选课程列表，在第三步顶部直接呈现绿色结果横幅（一键打开文件或定位目录）。
3. **A4 统一排版引擎**：强制剥离内联 `font-size`/`font-family`，正文统一 `10.5pt`，保留 `sub/sup` 上下标；Wiris SVG（`0.86x`）与高分辨率 Word 截屏图（`0.45x`）按阅读视觉比例自动缩放，四周 `18mm` 留白。
4. **零空文件夹策略**：PDF、分类 ZIP 与图片包直接输出到用户选定目录（默认 `Documents/CCTRExport`），不再遗留空数字子目录。
