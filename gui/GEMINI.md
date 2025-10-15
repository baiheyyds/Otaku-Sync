# `gui` 模块说明

`gui` 模块包含了 Otaku-Sync 图形用户界面的所有组件。它基于 `PySide6` 框架构建，旨在为用户提供一个直观、现代化的操作体验。

## 1. 设计理念

- **组件化**: 界面被拆分为多个独立的组件（Widgets），每个组件负责一块特定的功能区域。
- **主从结构**: `main_window.py` 是主窗口，它负责整合所有子组件，并管理应用的整体布局和生命周期。
- **对话框驱动**: 所有需要用户输入的交互都通过弹出的对话框（`dialogs.py`）来完成。
- **线程安全**: 核心业务逻辑运行在独立的 `QThread` (统称为 Worker) 中，通过 Qt 的信号与槽机制与主线程的 `MainWindow` 安全通信。

## 2. 核心交互模式：信号、槽与响应契约

这是整个GUI最复杂且最关键的部分。`MainWindow` 与后台 Worker (`GameSyncWorker`, `ScriptWorker`) 之间的通信遵循一个严格的契约。

### 2.1 信号的来源与 `sender()`

- **信号源**: `MainWindow` 中所有用于处理交互的 `handle_*` 槽函数，其信号**均由 Worker 线程实例 (`GameSyncWorker` 或 `ScriptWorker`) 发出**。
- **`sender()` 的身份**: 因此，在任何 `handle_*` 槽函数内部，调用 `worker = self.sender()` 所获取的 `worker` 变量，**始终是 Worker 线程自身的实例**，而不是 `GuiInteractionProvider`。

### 2.2 两种响应机制

根据交互类型的不同，`MainWindow` 将用户的选择传回后台的方式有两种，必须严格区分：

> **架构说明 (待重构)**
> 当前并存的两种机制是历史遗留问题，也是一个技术债。**机制A** 是更现代、更推荐的方式。未来的重构目标应该是将“机制B”的交互全部迁移到“机制A”，以统一和简化架构。

#### 机制 A：通过 Worker 的代理方法响应 (主要方式)

这是处理绝大多数通用交互（如标签翻译、Bangumi映射、名称分割等）的标准方式，基于 `asyncio.Future`。

- **流程**:
    1. Worker 内部的 `GuiInteractionProvider` 发出内部信号。
    2. Worker 捕获此信号，并**转发**一个自身定义的同名信号给 `MainWindow`。
    3. `MainWindow` 的 `handle_*` 槽函数被触发。
    4. `MainWindow` 调用 `worker.set_interaction_response(response)` 来发回响应。
- **关键契约**: `GameSyncWorker` 和 `ScriptWorker` 都提供了一个名为 `set_interaction_response(response)` 的公共方法。此方法通过 `loop.call_soon_threadsafe` 将响应安全地调度回后台 `asyncio` 循环，最终解除 `Future` 的等待状态。

- **代码示例 (`main_window.py`)**:
  ```python
  def handle_bangumi_mapping(self, request_data):
      # ... (创建对话框)
      worker = self.sender() # worker 是 GameSyncWorker 或 ScriptWorker
      dialog.exec()
      # 正确：调用 Worker 的代理方法
      worker.set_interaction_response(dialog.result)
  ```

#### 机制 B：直接更新 Worker 状态 (特殊情况)

这只用于少数几个历史遗留的、与 Worker 自身状态强相关的交互，主要是**初次的游戏选择**和**重复游戏确认**。它基于 `QMutex` 和 `QWaitCondition`。

- **流程**:
    1. Worker 发出 `selection_required` 或 `duplicate_check_required` 信号。
    2. `MainWindow` 的 `handle_selection_required` 或 `handle_duplicate_check` 槽函数被触发。
    3. `MainWindow` 调用 `worker.set_choice(choice)` 来直接设置 Worker 内部的一个状态变量。
    4. Worker 内部使用 `QMutex` 和 `QWaitCondition` 来同步等待这个状态变量被设置。
- **关键契约**: `GameSyncWorker` 提供了一个名为 `set_choice(choice)` 的公共方法，用于接收这种特定交互的结果。**此方法不应与其他交互混用。**

- **代码示例 (`main_window.py`)**:
  ```python
  def handle_selection_required(self, choices, title, source):
      # ... (创建对话框)
      worker = self.sender() # worker 是 GameSyncWorker
      # ...
      if result == QDialog.Accepted:
          # 正确：调用 Worker 的特定状态设置方法
          worker.set_choice(dialog.selected_index())
      else:
          worker.set_choice(-1) # 用户取消
  ```

**总结：在不确定的情况下，应优先假定使用机制 A (`set_interaction_response`)。**

## 3. 关键组件概览

- **`main_window.py` (`MainWindow`)**: 
    - **作用**: GUI 应用的入口和主容器。
    - **核心职责**: 初始化并管理 Worker 线程；包含所有 `handle_*` 槽函数，作为后台请求的UI响应中心。

- **`dialogs.py`**: 
    - **作用**: 包含了应用中所有自定义的 `QDialog` 对话框。

- **`widgets.py`**: 
    - **作用**: 存放构成主窗口的、功能独立的子组件，如 `BatchToolsWidget` 和 `MappingEditorWidget`。

- **`utils/gui_bridge.py`**: 
    - **`GuiInteractionProvider`**: `InteractionProvider` 接口的GUI实现。**注意：`MainWindow` 不应直接与此类交互**，而是通过 Worker 的代理方法和信号进行间接通信。
