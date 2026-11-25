# Gameplay IR (G-IR v0.1) 形式化规范

## 1. 设计目标

`Gameplay IR (G-IR)` 是 `GTA-Anything` 连接「上游任意玩法描述/源码」与「下游 GTA 模组代码生成」的核心中间表示层。它的职责是：
1. **剥离原宿主语言细节**，提取纯粹的玩法状态机、空间节点、角色契约与计分/经济规则；
2. **强制显式声明生命周期与安全兜底**（原版载具兜底、流式超时、UI 静态预览约束、确定性清理态）；
3. **保留证据锚点 (`evidence`)**（借鉴 `REA`），让每个转译出来的机制都能追溯到输入文档或源码位置。

---

## 2. JSON Schema 结构示例

```json
{
  "schema_version": "0.1.0",
  "meta": {
    "id": "metro_shuttle_loop",
    "name": "Los Santos Metro Shuttle Loop",
    "version": "0.1.0",
    "author": "GTA-Anything Clean-Room",
    "license": "MIT",
    "description": "Fixed-route urban transit operational loop with ordered stops, passenger boarding, fare accounting, and reversible shift teardown.",
    "source_kind": "spec_and_xml",
    "target_editions": ["enhanced_gen9", "legacy_gen8"]
  },
  "loader_target": "shvdn_enhanced",
  "inputs": {
    "activation_key": "F9",
    "modifier_key": "LeftShift",
    "menu_library": "LemonUI",
    "avoid_conflicts_with": ["F4", "Insert", "B", "N", "E"]
  },
  "ui_spec": {
    "title": "Metro Shuttle Dispatch",
    "subtitle": "Select route & vehicle class",
    "preview_mode": "static_sprite"
  },
  "entities": [
    {
      "slot_id": "transit_coach_primary",
      "role": "player_service_vehicle",
      "vanilla_fallback_model": "bus",
      "preferred_addon_model": null,
      "stream_timeout_ms": 5000,
      "is_player_vehicle": true
    },
    {
      "slot_id": "commuter_passenger",
      "role": "boarding_npc",
      "vanilla_fallback_model": "a_m_y_business_01",
      "preferred_addon_model": null,
      "stream_timeout_ms": 3000,
      "is_player_vehicle": false
    }
  ],
  "routes_or_zones": [
    {
      "track_id": "route_10_downtown",
      "name": "Route 10 Downtown Circular",
      "mode": "ordered_stops",
      "fare_or_reward": 15,
      "allowed_vehicle_slots": ["transit_coach_primary"],
      "stops": [
        {"index": 0, "name": "Terminal Depot", "x": 436.2, "y": -645.8, "z": 28.7, "dwell_seconds": 6},
        {"index": 1, "name": "Legion Square North", "x": 215.4, "y": -810.1, "z": 30.7, "dwell_seconds": 8}
      ]
    }
  ],
  "state_machine": {
    "initial_state": "Idle",
    "cleanup_state": "Teardown",
    "states": [
      {"name": "Idle", "phase": "standby", "description": "Mod loaded, waiting for activation keybind."},
      {"name": "MenuSelecting", "phase": "ui", "description": "Browsing routes and vehicle static cards without spawning 3D entities."},
      {"name": "ResourceStreaming", "phase": "streaming", "description": "Requesting vehicle/ped models with timeout and fallback."},
      {"name": "SpawningShift", "phase": "spawning", "description": "Creating service vehicle, verifying non-null handle, seating player."},
      {"name": "ActiveRoute", "phase": "operation", "description": "Driving ordered stops, handling dwell, doors, boarding NPCs, and fares."},
      {"name": "ShiftSummary", "phase": "completion", "description": "Displaying shift completion stats before releasing world entities."},
      {"name": "Teardown", "phase": "cleanup", "description": "Releasing all leased vehicles, peds, blips, and model handles."}
    ],
    "transitions": [
      {"from_state": "Idle", "to_state": "MenuSelecting", "trigger": "HotkeyPressed"},
      {"from_state": "MenuSelecting", "to_state": "Idle", "trigger": "MenuCancelled"},
      {"from_state": "MenuSelecting", "to_state": "ResourceStreaming", "trigger": "ShiftConfirmed"},
      {"from_state": "ResourceStreaming", "to_state": "SpawningShift", "trigger": "ModelReadyOrFallback"},
      {"from_state": "ResourceStreaming", "to_state": "Teardown", "trigger": "CriticalStreamFailure"},
      {"from_state": "SpawningShift", "to_state": "ActiveRoute", "trigger": "DriverSeated"},
      {"from_state": "SpawningShift", "to_state": "Teardown", "trigger": "SpawnReturnedNull"},
      {"from_state": "ActiveRoute", "to_state": "ShiftSummary", "trigger": "FinalStopCompleted"},
      {"from_state": "ActiveRoute", "to_state": "Teardown", "trigger": "ShiftAbortedOrVehicleDestroyed"},
      {"from_state": "ShiftSummary", "to_state": "Teardown", "trigger": "SummaryAcknowledged"},
      {"from_state": "Teardown", "to_state": "Idle", "trigger": "ResourcesReleased"}
    ]
  },
  "evidence": [
    {
      "source_file": "spec.md",
      "locator": "L12-L28",
      "extracted_fact": "Ordered transit stops with dwell timer and fare calculation per boarding passenger.",
      "confidence": 0.98
    }
  ]
}
```

---

## 3. 强制静态校验不变量 (`validate_gameplay_ir`)

1. **原版兜底完整性**：`entities` 中每一项的 `vanilla_fallback_model` 必须非空，且属于合法标识符。
2. **禁止菜单实时生成 3D 预览实体**：`ui_spec.preview_mode` 严禁为 `"live_3d_spawn"`。
3. **状态机完备性与安全回收**：
   - `initial_state` 和 `cleanup_state` 必须存在于 `states` 列表中；
   - 从 `initial_state` 出发所有状态可达；
   - 任何处于 `streaming`、`spawning`、`operation`、`completion` 阶段的状态，必须存在至少一条有向路径能够到达 `cleanup_state`（确保异常或中途退出时一定能执行 `WorldSession` 清理）。
4. **热键防冲突告警**：当未配置 `modifier_key` 且直接使用高冲突单键（如 `F4`、`Insert`、`E`、`B`）时产生明确告警。
5. **洁净室授权校验**：`meta.license` 不得为空或 `"proprietary-unlicensed"`。
