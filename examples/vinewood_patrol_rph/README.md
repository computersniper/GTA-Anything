# Flagship Clean-Room Example 3: Vinewood Hills Patrol & Incident Response (`vinewood_patrol_rph`)

`vinewood_patrol_rph` 是 `GTA-Anything` 的第三套 **100% 洁净室原创标杆示例**，专门演示 **RAGE Plugin Hook (`loader_target: "rph"`)** 双加载链后端转译、**2D 静态菜单预览卡 (`static_sprite` SVG)**、离线 7 层仿真与洛圣都雷达蓝图可视化。

---

## 1. 工程亮点与铁律示范

- **一模双链 · 原生 RPH 后端 (`loader_target: "rph"`)**：
  - `gta-anything transpile` 自动生成带 `USE_RPH` 条件编译宏的 `.csproj`、`RphPluginBridge.cs`（含纤程安全主循环与 `OnUnload` 确定性 `WorldSession.DisposeAll()` 清理钩子）以及兼容的 `ModEntrypoint.cs`。
- **低冲突 RPH 组合热键**：
  - 采用 `LeftControl + F10` 唤起巡逻调度面板，显式避让 RPH 控制台 (`F4`) 与 LSPDFR/原版高频按键 (`B` / `N` / `E` / `Y`)。
- **2D 静态预览卡 (`static_sprite`) + 100% 原版可玩基线**：
  - 菜单阶段严禁实时 3D 刷车，转译时自动在 `cards/` 目录输出 SVG 静态路线预览卡；
  - 载具槽位默认绑定 GTA V 原版 `police3`（巡逻截击车）与 `fbi2`（战术响应 SUV），现场联络员绑定原版 `s_m_y_ranger_01`，零外部第三方 `.rpf` 即可跑通 L1–L7 全链路。
- **完整巡逻与应急响应状态机**：
  - `Idle` → `MenuSelecting` → `ResourceStreaming` → `SpawningShift` → `ActivePatrol`（覆盖 Vinewood Hills 与 Downtown 4 大应急响应点）→ `ShiftSummary` → `Teardown` → `Idle`。

---

## 2. 目录文件清单

- [`spec.md`](spec.md)：Vinewood 巡逻与应急响应玩法说明书（RPH 契约、实体槽位、4 大响应区坐标与状态机定义）。
- [`gameplay_ir.json`](gameplay_ir.json)：严格符合 [`docs/GAMEPLAY_IR_SPEC.md`](../../docs/GAMEPLAY_IR_SPEC.md) 的 RPH 目标中间表示文件。

---

## 3. 快速体验命令 (Quickstart CLI)

```bash
# 1. 校验 Gameplay IR 安全不变量
gta-anything --json validate-ir examples/vinewood_patrol_rph/gameplay_ir.json

# 2. 离线 7 层无头仿真（验证 L1-L7 遥测与零泄漏回收）
gta-anything --json simulate examples/vinewood_patrol_rph/gameplay_ir.json \
  --telemetry-out build/vinewood_patrol_telemetry.jsonl

# 3. 生成独立的洛圣都街头雷达蓝图 HTML
gta-anything --json visualize examples/vinewood_patrol_rph/gameplay_ir.json \
  -o build/vinewood_patrol_radar.html

# 4. 转译为 RPH C# 洁净室插件工程 + 2D 静态菜单预览卡 (cards/*.svg)
gta-anything --json transpile examples/vinewood_patrol_rph/gameplay_ir.json \
  -o build/vinewood_patrol_rph_mod

# 5. 一键跑完离线全链路 (Extract -> Validate -> Transpile -> Asset-Check -> Simulate -> Visualize)
gta-anything --json pipeline examples/vinewood_patrol_rph/gameplay_ir.json \
  -o build/vinewood_patrol_rph_pipeline --edition enhanced_gen9
```
