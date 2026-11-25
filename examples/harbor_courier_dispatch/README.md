# Flagship Clean-Room Example 2: Port of Los Santos Harbor Courier Dispatch (`harbor_courier_dispatch`)

`harbor_courier_dispatch` 是 `GTA-Anything` 的第二套 **100% 洁净室原创标杆示例**，演示如何将「区域执勤与调度响应玩法 (`dispatch_zones`)」通过 `Gameplay IR` 转译为支持 **GTA V Enhanced (Gen9)** 与 **Legacy (Gen8)** 的高可靠 C# 模组。

---

## 1. 工程亮点与铁律示范

- **完整执勤与区域调度闭环 (`dispatch_zones`)**：
  - `Idle`（下班待命）→ `MenuSelecting`（静态货单卡片选配载具并上班执勤）→ `ResourceStreaming`（流式加载 `mule`/`benson` 货运车与 `s_m_m_dockwork_01` 港区协调员）→ `SpawningShift`（生成执勤车并接听调度指派）→ `ActiveDispatch`（驶往港区海关查验区、驻留核验、与 NPC 协调员交接并结案）→ `DispatchSummary`（执勤绩效结算）→ `Teardown`（下班并确定性回收全部租约实体）。
- **低冲突组合热键与多 Profile 友好设计**：
  - 默认采用 `LeftControl + F10` 唤起调度终端，显式避开 `F4` (RPH)、`Insert` (SHVDN)、`F3`/`F8` (Trainer)、`B`/`N`/`E`/`Y` (LSPDFR/原版高频按键) 及 `LeftShift + F9` (`metro_shuttle_loop`)。
- **静态元数据预览 (`static_metadata`) + 100% 原版可玩基线**：
  - 菜单阶段仅渲染静态货单与载具参数卡片，零 3D 预览实体生成；
  - 货运车辆槽位直接绑定 GTA V 原版 `mule` 与 `benson`，协调员绑定原版 `s_m_m_dockwork_01`，无需任何外部第三方 `.rpf` 即可完整跑通 L1–L7 七层验收。

---

## 2. 目录文件清单

- [`spec.md`](spec.md)：港区调度执勤玩法机制说明书（状态机、实体槽位、4 大查验区坐标与奖励规则）。
- [`gameplay_ir.json`](gameplay_ir.json)：严格符合 [`docs/GAMEPLAY_IR_SPEC.md`](../../docs/GAMEPLAY_IR_SPEC.md) 的标准中间表示文件。

---

## 3. 快速体验命令 (Quickstart CLI)

```bash
# 1. 校验 Gameplay IR 安全不变量
gta-anything --json validate-ir examples/harbor_courier_dispatch/gameplay_ir.json

# 2. 转译为洁净室 C# 模组工程
gta-anything --json transpile examples/harbor_courier_dispatch/gameplay_ir.json -o build/harbor_courier_dispatch_mod

# 3. 一键执行离线全链路 (Extract -> Validate -> Transpile C# -> Asset-Check)
gta-anything --json pipeline examples/harbor_courier_dispatch/gameplay_ir.json -o build/harbor_courier_dispatch_mod --edition enhanced_gen9
```
