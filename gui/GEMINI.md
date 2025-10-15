# `gui` 模块说明

`gui` 模块包含了 Otaku-Sync 图形用户界面的所有组件。它基于 `PySide6` 框架构建，旨在为用户提供一个直观、现代化的操作体验。

## 1. 设计理念

- **组件化**: 界面被拆分为多个独立的组件（Widgets），每个组件负责一块特定的功能区域。
- **主从结构**: `main_window.py` 是主窗口，它负责整合所有子组件，并管理应用的整体布局和生命周期。
- **对话框驱动**: 所有需要用户输入的交互都通过弹出的对话框（`dialogs.py`）来完成。
- **线程安全**: 核心业务逻辑运行在独立的 `QThread` (统称为 Worker) 中，通过 Qt 的信号与槽机制与主线程的 `MainWindow` 安全通信。

## 2. 核心交互模式：信号、槽与响应契约

`MainWindow` 与后台 Worker (`GameSyncWorker`, `ScriptWorker`) 之间的通信遵循一个严格的、统一的异步契约。

### 2.1 信号的来源与 `sender()`

- **信号源**: `MainWindow` 中所有用于处理交互的 `handle_*` 槽函数，其信号**均由 Worker 线程实例 (`GameSyncWorker` 或 `ScriptWorker`) 发出**。
- **`sender()` 的身份**: 因此，在任何 `handle_*` 槽函数内部，调用 `worker = self.sender()` 所获取的 `worker` 变量，**始终是 Worker 线程自身的实例**，而不是 `GuiInteractionProvider`。

### 2.2 统一的响应机制

现在，所有的交互都遵循统一的“现代模式”，基于 `asyncio.Future`。

- **流程**:
    1. Worker 内部的 `GuiInteractionProvider` 在需要用户输入时，会发出一个内部信号，并 `await` 一个 `asyncio.Future` 对象（可以理解为一个等待结果的“占位符”）。
    2. Worker 捕获此内部信号，并**转发**一个自身定义的、名称相同的外部信号给 `MainWindow`。
    3. `MainWindow` 中对应的 `handle_*` 槽函数被触发，并显示一个对话框。
    4. 用户操作完毕后，`MainWindow` 调用 `worker.set_interaction_response(response)` 来发回用户的选择。

- **关键契约**: `GameSyncWorker` 和 `ScriptWorker` 都提供了一个名为 `set_interaction_response(response)` 的公共方法。此方法通过 `loop.call_soon_threadsafe` 将响应安全地调度回后台 `asyncio` 循环，最终为等待中的 `Future` 对象设置结果，从而让 `await` 的代码可以继续执行。

- **代码示例 (`main_window.py`)**:
  ```python
  def handle_bangumi_mapping(self, request_data):
      # ... (创建对话框)
      worker = self.sender() # worker 是 GameSyncWorker 或 ScriptWorker
      dialog.exec()
      # 正确：调用 Worker 的统一响应方法
      worker.set_interaction_response(dialog.result)
  ```

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
