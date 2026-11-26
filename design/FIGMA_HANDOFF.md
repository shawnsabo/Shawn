# 融智导出 Atelier · Editorial Atelier 设计系统与统一实现说明 (v4.1)

- **Figma 设计参考**: [Rongzhi Export Studio · Figma](https://www.figma.com/design/pPu0Lj18qSMfbyKjdLN9hz)
- **美学定位**: **Editorial Atelier（瑞士印务工坊 · 纸墨与精密仪器美学）** —— 彻底弃用旧版冷灰蓝紫 SaaS 卡片模板与重边框堆砌，转而采用暖石纹纸面（Warm Archival Stone）、哑光碳黑主控（Matte Carbon Ink）、几何 A4 裁切十字标、等宽刻度数字与带四角裁切线的点阵 A4 实样校对台。

## 设计系统令牌 (Design Tokens)
| Token | 浅色 (Warm Stone) | 深色 (Anodized Graphite) | 用途 |
| --- | --- | --- | --- |
| `--frame` / `BgCanvas` | `#F4F3EF` | `#0E0E0D` | 画布底框（典藏石纹 / 阳极石墨） |
| `--paper` / `BgSurface` | `#FFFFFF` | `#151514` | 印张表层 |
| `--well` / `BgSubtle` | `#EAE7E0` | `#1E1E1C` | 分段凹槽底座与裁切点阵垫 |
| `--line` / `BorderHairline` | `#E2DFD7` | `#262523` | `1px` 建筑级发丝分割线 |
| `--ink` / `InkPrimary` | `#141413` | `#EDEDEA` | 主墨色与主按钮实心底色 |
| `--vermilion` / `AccentSeal` | `#C83E2B` | `#E26250` | A4 样张朱批红标与异常提示 |
| `--jade` / `StatusOk` | `#1E6B4E` | `#4EAD89` | 就绪 / 校准通过状态 |

## 双端统一架构与工程健壮性
1. **桌面端一体化顶栏架构 (`CCTR Atelier · 融智云考印务工作台`)**：
   - `48px` 全宽精密顶栏整合裁切标、分段视图（`工作台 / 归档库 / 审校日志`）及右侧目录、内核、活动抽屉与深浅主题切换。
   - 工序 `01` 采用左社论规格铭牌 + 右 `400px` 表单台面的非对称分栏；工序 `02` 为双列高密度目录账本与底部结算条；工序 `03` 为左参数台账 + 右带四角裁切线的点阵底板 A4 实样校对台。支持 `<= 780px` 窄屏与分屏平板无缝自适应。
2. **安卓手机与平板自绘高定组件 (`MainScreen.kt` + `Theme.kt`)**：
   - 淘汰默认 Material3 胶囊导航栏与肥大边框输入框，采用自绘 `AtelierRegistrationMark`、`AtelierTextField`（`42dp` 紧凑输入）、`AtelierSegmentedRow` 与 `AtelierSwitchRow`。
   - 自适应 `BoxWithConstraints` 断点：`>= 600dp` 平板切换左侧建筑感导轨与双列练习/归档网格；`>= 840dp` 横屏平板启用工序 `01` 社论双栏与工序 `03` 参数 + A4 实样双栏；手机 `< 600dp` 使用 `50dp` 极简顶栏与 `52dp` 顶横线底栏，且配置 `configChanges` 避免旋转丢态。
3. **A4 排版引擎与容错升级**：
   - 统一 `10.5pt` 正文 + `Wiris 0.86×` + `18mm` 留白；可选开启 **智能防隔页分页**。
   - **Word / Office 富文本容错**：自动预剥离 Word MSO 条件注释与 XML/Style 元数据，对 `<font>`、`<st1:chmetcnv>`、`<st1:chsdate>`、`<o:p>` 等包装/命名空间标签安全解包保留正文。
   - **远程 OSS 图片预内联**：导出前 8 线程直连拉取图片并校验魔数后内联为 `data:` URI，彻底避免代理抖动导致的并发加载失败。
