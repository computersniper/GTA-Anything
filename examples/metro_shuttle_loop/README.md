# Flagship Clean-Room Example 1: Los Santos Metro Shuttle Loop (`metro_shuttle_loop`)

`metro_shuttle_loop` 是 `GTA-Anything` 的第一套 **100% 洁净室原创标杆示例**，演示如何将「固定线路城市公共交通运营玩法 (`spec.md` + `routes/ls_downtown_loop.xml`)」通过 `Gameplay IR` 转译为支持 **GTA V Enhanced (Gen9)** 与 **Legacy (Gen8)** 的高可靠 C# 模组。

---

## 1. 工程亮点与铁律示范

- **完整公交运营闭环（非单步刷车玩具）**：
  - `Idle` → `MenuSelecting`（静态路线卡片选配）→ `ResourceStreaming`（流式加载与超时释放）→ `SpawningShift`（场站发车与租约登记）→ `ActiveRoute`（8 站有序停靠、驻留计时、开关门、NPC 乘客上下车、票价核算）→ `ShiftSummary`（完班营收结算）→ `Teardown`（确定性回收所有实体）。
- **UI 与 3D 实体生成彻底解耦**：
  - `ui_spec.preview_mode = "static_sprite"`，在菜单滚动路线与车型时绝不调用 `CreateVehicle` 实时刷出 3D 预览车，彻底消除 `NullReferenceException` 与内存抖动。
- **原版基线先行 + 流式超时兜底**：
  - 主力车型槽位 `transit_coach_primary` 绑定 GTA V 原版 `bus`，快线槽位 `airport_shuttle_express` 绑定原版 `airbus`，乘客槽位绑定 `a_m_y_business_01`。
  - 若用户后续挂载自定义双层巴士 Add-on (`preferred_addon_model`) 发生流式加载超时（5000ms），`SafeModelStreamer` 自动调用 `MarkAsNoLongerNeeded()` 释放悬空句柄并无缝回退至原版 `bus`。

---

## 2. 目录文件清单

- [`spec.md`](spec.md)：结构化玩法机制说明书（状态机、实体槽位、交互规则）。
- [`routes/ls_downtown_loop.xml`](routes/ls_downtown_loop.xml)：100% 原创的洛圣都中心城区 8 站环线 XML 配置（含 Dashound 总站、Legion Square、Pillbox Hill、Rockford Hills 等站点坐标、驻留秒数与票价）。
- [`gameplay_ir.json`](gameplay_ir.json)：严格符合 [`docs/GAMEPLAY_IR_SPEC.md`](../../docs/GAMEPLAY_IR_SPEC.md) 的标准中间表示文件。

---

## 3. 快速体验命令 (Quickstart CLI)

```bash
# 1. 从 spec.md + routes/ls_downtown_loop.xml 提取 Gameplay IR
gta-anything --json extract examples/metro_shuttle_loop/spec.md -o build/metro_ir.json --edition enhanced_gen9

# 2. 校验 Gameplay IR 安全不变量
gta-anything --json validate-ir examples/metro_shuttle_loop/gameplay_ir.json

# 3. 一键执行离线全链路 (Extract -> Validate -> Transpile C# -> Asset-Check)
gta-anything --json pipeline examples/metro_shuttle_loop/gameplay_ir.json -o build/metro_shuttle_loop_mod --edition enhanced_gen9
```
