# `gui` 模块说明

`gui` 模块包含了 Otaku-Sync 图形用户界面的所有组件。它基于 `PySide6` 框架构建，旨在为用户提供一个直观、现代化的操作体验。

## 1. 设计理念

- **组件化**: 界面被拆分为多个独立的组件（Widgets），每个组件负责一块特定的功能区域。
- **主从结构**: `main_window.py` 是主窗口，它负责整合所有子组件，并管理应用的整体布局和生命周期。其核心布局基于 `QSplitter` 实现左右分割：左侧是包含“批处理工具”和“映射编辑器”等功能区的 `QTabWidget`，右侧是日志输出区域。
- **现代化主题**: 界面采用一个名为 "Otaku-Sync Soft & Fresh Theme" 的自定义浅色主题，该主题在 `gui/style.qss` 中定义。它以柔和的背景色和薄荷绿为强调色，取代了之前基于 `qdarkstyle` 的暗色主题，提供了更清新、更具现代感的视觉体验。
- **响应式布局**: 在需要排列多个按钮或元素的场景（如 `BatchToolsWidget`），采用了自定义的 `FlowLayout`，使得元素可以根据窗口大小自动换行，提高了界面的适应性。
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
    - **核心职责**: 初始化并管理 Worker 线程；包含所有 `handle_*` 槽函数，作为后台请求的UI响应中心；使用 `QSplitter` 和 `QTabWidget` 构建主界面的左右布局。**现在，它还在状态栏中集成了 `QProgressBar` 和 `QLabel`，用于连接 `GameSyncWorker` 和 `ScriptWorker` 发出的进度信号，从而实时显示任务进度和耗时。**

- **`dialogs.py`**: 
    - **作用**: 包含了应用中所有自定义的 `QDialog` 对话框。
    - **`SelectionDialog`**: **[已重构]** 一个用于展示搜索结果并让用户选择的通用对话框。它经过了多次迭代优化，最终采用列表视图（`QListWidget`），并为每个列表项使用自定义的 `GameListItemWidget`。
        - **`GameListItemWidget`**: 这是一个自定义的列表项控件，实现了左侧为封面图，右侧为文字信息的布局。它通过 `QPainter` 提供了高质量的图片缩放，并使用嵌套布局实现了文字部分的垂直居中，以达到最佳视觉效果。
        - **动态尺寸**: 对话框的高度会根据搜索结果的数量动态调整，避免了内容过少时出现大量空白区域。

- **`widgets.py`**: 
    - **作用**: 存放构成主窗口的、功能独立的子组件。
    - **`BatchToolsWidget`**: 提供一个响应式的按钮区域，用于执行各种批量脚本。
    - **`MappingEditorWidget`**: **[已重构]** 一个功能增强的映射文件编辑器。它现在具有左右分栏的布局、键搜索功能，并能跟踪文件的“未保存”状态，在退出时提醒用户，显著提升了易用性。

- **`flow_layout.py` (`FlowLayout`)**:
    - **作用**: 一个自定义的布局管理器，允许内部的子组件（如按钮）在空间不足时自动换行，而不是被压缩或截断。这在 `BatchToolsWidget` 中被用来创建响应式的按钮区域。

- **`image_loader.py` (`ImageLoader`)**: **[新]**
    - **作用**: 一个异步图片加载器。它使用 `QThreadPool` 在后台线程中下载图片，避免因网络请求阻塞 GUI 主线程。
    - **核心功能**: 在 `SelectionDialog` 中被用来加载和显示游戏封面图。它支持图片缓存，以避免重复下载相同的图片，并能在图片加载完成前显示一个占位符。

- **`style.qss`**:
    - **作用**: Qt 样式表（QSS）文件，用于覆盖和补充 `qdarkstyle` 的默认样式，实现更精细的视觉定制。

- **`utils/gui_bridge.py`**: 
    - **`GuiInteractionProvider`**: `InteractionProvider` 接口的GUI实现。**注意：`MainWindow` 不应直接与此类交互**，而是通过 Worker 的代理方法和信号进行间接通信。
