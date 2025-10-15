# `core` 模块说明

`core` 模块是 Otaku-Sync 应用的核心，包含了所有与用户界面无关的业务逻辑、数据处理和工作流编排。它是整个应用的大脑。

## 1. 设计理念

- **UI 无关性**: `core` 模块中的任何代码都不应直接依赖于 GUI (PySide6) 或 CLI (`print`, `input`)。所有的用户交互都必须通过 `core/interaction.py` 中定义的 `InteractionProvider` 抽象接口进行。
- **上下文驱动**: 整个核心逻辑的初始化通过 `core/context_factory.py` 完成。它负责创建和组装所有需要的客户端、管理器和工具类，形成一个统一的 `context` 字典，在整个处理流程中传递。
- **流程编排**: 核心模块负责定义和执行从用户输入关键词到最终数据同步至 Notion 的完整工作流。

## 2. 关键组件概览

- **`init.py`**: 初始化 `core` 模块，使其成为一个 Python 包。
- **`context_factory.py`**: 应用的“组装车间”，负责实例化所有必要的对象（如 `NotionClient`, `TagManager`）并注入到 `context` 中。
- **`driver_factory.py`**: 管理 Selenium WebDriver 的创建和配置。
- **`selector.py`**: 提供用于从搜索结果中选择正确游戏的功能。
- **`name_splitter.py`**: 负责将游戏名称拆分为品牌和游戏标题。
- **`schema_manager.py`**: 管理 Notion 数据库的结构。
- **`cache_warmer.py`**: 在程序启动时预热缓存。
- **`interaction.py` (`InteractionProvider`)**: 定义了核心业务逻辑与用户界面之间“契约”的抽象基类。所有需要用户输入的场景都必须通过此接口的实现来完成。

- **`game_processor.py`**: 负责将从各个来源收集到的零散数据进行合并、处理，并最终组装成符合 Notion 数据库结构的格式。

- **`brand_handler.py`**: 专门处理与“品牌”相关的所有逻辑。

- **`mapping_manager.py`**: 管理 `mapping/` 目录下的各种映射关系，是实现数据规范化的关键。

- **`data_manager.py`**: 在程序启动时加载 `mapping/` 目录下的所有 JSON 文件到内存中。

- **`gui_worker.py` (`GameSyncWorker`, `ScriptWorker`)**: 
    - **定位**: 这是**专门为GUI模式设计**的后台工作线程 (`QThread`)，是连接 `core` 纯逻辑与 `gui` 界面的桥梁。
    - **核心职责**: 
        1.  **运行事件循环**: 在独立的线程中创建并管理一个 `asyncio` 事件循环，用于执行所有的核心异步任务。
        2.  **实例化交互提供者**: 在其管理的事件循环中，实例化 `GuiInteractionProvider`。
        3.  **充当信号代理 (Signal Proxy)**: 这是理解其工作模式的**关键**。`GameSyncWorker` 和 `ScriptWorker` 都会监听其内部 `GuiInteractionProvider` 实例发出的“内部”信号，然后**转发**一个由 Worker 自身定义的、名称相同的“外部”信号给 `MainWindow`。这确保了交互请求可以被线程安全地传递到主GUI线程进行处理。
        4.  **提供响应入口**: 为了接收 `MainWindow` 的响应，两个 Worker 都提供了公共方法。这些方法通过 `loop.call_soon_threadsafe` 来保证响应被安全地传递回后台的 `asyncio` 事件循环。

    - **架构说明**:
        交互完全基于 `asyncio.Future` 和 `InteractionProvider` 接口实现，确保了后台与前台之间通信模式的统一和线程安全。

## 3. 核心工作流（GUI模式）

GUI 模式下的工作流与CLI模式在核心逻辑上相似，但在交互处理上完全不同。

1.  `MainWindow` 创建一个 `GameSyncWorker` (或 `ScriptWorker`) 实例并启动它。
2.  Worker 在其 `run()` 方法中创建 `asyncio` 循环和 `GuiInteractionProvider`。
3.  Worker 开始执行其核心异步函数（如 `game_flow()`）。
4.  当业务逻辑需要用户输入时，它会调用 `GuiInteractionProvider` 的方法（例如 `get_tag_translation`）。
5.  `GuiInteractionProvider` 发出一个**内部信号**。
6.  Worker 监听到此内部信号，并立即发出一个**同名的外部信号**。
7.  `MainWindow` 的对应槽函数被触发。
8.  `MainWindow` 显示对话框，等待用户操作。
9.  用户操作完毕后，`MainWindow` 调用 `worker.set_interaction_response(...)` 将结果返回给 Worker。
10. Worker 通过线程安全的方式将结果传递给 `GuiInteractionProvider`，解除 `await` 阻塞。
11. 核心业务逻辑继续执行。