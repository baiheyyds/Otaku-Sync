# `core` 模块说明

`core` 模块是 Otaku-Sync 应用的核心，包含了所有与用户界面无关的业务逻辑、数据处理和工作流编排。它是整个应用的大脑。

## 1. 设计理念

- **UI 无关性**: `core` 模块中的任何代码都不应直接依赖于 GUI (PySide6) 或 CLI (`print`, `input`)。所有的用户交互都必须通过 `core/interaction.py` 中定义的 `InteractionProvider` 抽象接口进行。
- **上下文驱动**: 整个核心逻辑的初始化通过 `core/context_factory.py` 完成。它负责创建和组装所有需要的客户端、管理器和工具类，形成一个统一的 `context` 字典，在整个处理流程中传递。
- **流程编排**: 核心模块负责定义和执行从用户输入关键词到最终数据同步至 Notion 的完整工作流。

## 2. 关键组件概览

- **`init.py`**: **[已修正]** 项目的资源管理核心。它提供 `init_context` 和 `close_context` 两个关键函数，负责在程序启动时安全地初始化所有必要的服务（如 HTTP 客户端、驱动程序工厂），并在程序退出时优雅地关闭它们、保存缓存，确保数据的一致性和资源的正确释放。

- **`context_factory.py`**: **[已重构]** 应用的“组装车间”，现在采用更先进的分层上下文设计：
    - **`create_shared_context`**: 创建在整个应用生命周期内共享的单例对象，如缓存 (`BrandCache`)、管理器 (`TagManager`, `BrandMappingManager`) 和驱动程序工厂 (`driver_factory`)。
    - **`create_loop_specific_context`**: 为每个独立的事件循环（例如，每个后台工作线程）创建专属的、非共享的对象，主要是 `httpx.AsyncClient` 和所有依赖它的 API 客户端（如 `DlsiteClient`, `NotionClient`）。这种设计确保了网络请求等操作在多线程环境下的线程安全。

- **`driver_factory.py`**: **[已重构]** 一个高度优化的、线程安全的 Selenium WebDriver 管理器。它不再简单地创建驱动，而是：
    1.  在独立的后台线程中运行一个自己的 `asyncio` 事件循环。
    2.  接收到创建请求后（如 `start_background_creation`），它会在此后台线程中**并发地**准备和实例化多个 WebDriver（例如，为 Dlsite 和 GGBases 分别创建）。
    3.  主线程可以通过 `await get_driver(...)` 安全地获取驱动，如果驱动正在后台创建，它会异步等待，而不会阻塞主线程或 GUI。
    这种设计极大地优化了程序的启动性能和响应速度。

- **`selector.py`**: **[新]** 游戏选择器。负责实现“跨站搜索”和“智能选择”的核心逻辑。
    - **`search_all_sites`**: 根据用户输入，依次在 DLsite 和 Fanza 等网站上搜索，直到找到结果为止。
    - **`_find_best_match`**: 对搜索结果列表，使用 `rapidfuzz` 库和加权的评分算法，计算每个候选项与用户输入关键词的相似度，并找出最可能的匹配项，以实现非手动模式下的自动选择。

- **`name_splitter.py`**: 负责将包含多个创作者的字符串（如 “A/B/C”）智能地拆分为独立的名称列表。它包含一个例外列表 `name_split_exceptions.json` 以处理特殊情况。

- **`brand_handler.py`**: **[新]** 专门处理与“品牌”相关的所有逻辑。它会检查一个新品牌是否已存在于 Notion 或缓存中，如果不存在，则使用 `rapidfuzz` 进行模糊匹配，查找相似的现有品牌，并通过 `InteractionProvider` 询问用户是希望“合并”到现有品牌还是“创建”为新品牌。

- **`game_processor.py`**: **[新]** 数据的“最终整合者”。在从所有来源（DLsite, Fanza, GGBases, Bangumi）获取到零散的数据后，此模块负责根据预设的优先级规则，将这些数据合并、去重、处理，最终组装成一个准备写入 Notion 的、结构完整的字典。

- **`schema_manager.py`**: 管理 Notion 数据库的结构（Schema）。它会在启动时从 Notion API 获取结构信息，并将其缓存到本地，避免了每次运行时都重复请求。

- **`cache_warmer.py`**: 在程序启动时，在后台线程中“预热”品牌缓存，即提前从 Notion 中获取所有品牌信息，以加速后续的品牌处理流程。

- **`interaction.py` (`InteractionProvider`)**: 定义了核心业务逻辑与用户界面之间“契约”的抽象基类。所有需要用户输入的场景都必须通过此接口的实现来完成。

- **`mapping_manager.py`**: **[新]** 数据映射的核心管理器。
    - **`BrandMappingManager`**: 负责处理品牌（厂商）名称的归一化。它维护一个 `brand_mapping.json` 文件，能将 "ゆずソフト"、"YuzuSoft" 等别名统一映射到规范名称 "YUZUSOFT" 上。
    - **`BangumiMappingManager`**: 负责动态处理 Bangumi 属性到 Notion 字段的映射。当从 Bangumi API 获取到一个未知的属性（如一个新的制作人员角色）时，它会通过 `InteractionProvider` 接口询问用户应如何映射（是映射到现有字段还是创建新字段），并将用户的选择持久化到 `bangumi_prop_mapping.json` 中。

- **`data_manager.py`**: **[新]** 一个全局数据加载器。它在程序启动时自动读取 `mapping/` 目录下的所有 `.json` 文件，并将它们加载到内存中，为 `TagManager` 等其他模块提供一个统一、便捷的数据访问接口。

- **`gui_worker.py` (`GameSyncWorker`, `ScriptWorker`)**: 
    - **定位**: 这是**专门为GUI模式设计**的后台工作线程 (`QThread`)，是连接 `core` 纯逻辑与 `gui` 界面的桥梁。
    - **核心职责**: 
        1.  **运行事件循环**: 在独立的线程中创建并管理一个 `asyncio` 事件循环，用于执行所有的核心异步任务。
        2.  **实例化交互提供者**: 在其管理的事件循环中，实例化 `GuiInteractionProvider`。
        3.  **充当信号代理 (Signal Proxy)**: 这是理解其工作模式的**关键**。`GameSyncWorker` 和 `ScriptWorker` 都会监听其内部 `GuiInteractionProvider` 实例发出的“内部”信号，然后**转发**一个由 Worker 自身定义的、名称相同的“外部”信号给 `MainWindow`。这确保了交互请求可以被线程安全地传递到主GUI线程进行处理。
        4.  **提供响应入口**: 为了接收 `MainWindow` 的响应，两个 Worker 都提供了公共方法。这些方法通过 `loop.call_soon_threadsafe` 来保证响应被安全地传递回后台的 `asyncio` 事件循环。
        5.  **报告进度与耗时**: Worker 现在会发出 `progress_start`, `progress_update`, `time_update`, 和 `progress_finish` 信号，用于驱动 GUI 界面上的进度条和耗时标签，为用户提供实时的任务反馈。

    - **架构说明**:
        交互完全基于 `asyncio.Future` 和 `InteractionProvider` 接口实现，确保了后台与前台之间通信模式的统一和线程安全。