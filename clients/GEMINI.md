# `clients` 模块说明

`clients` 模块是 Otaku-Sync 项目与外部世界沟通的桥梁。它包含了所有用于与特定网站或 API 进行交互的客户端类。

## 1. 设计理念

- **单一职责**: 每个客户端文件（如 `dlsite_client.py`）只负责与一个数据源（如 `dlsite.com`）的全部交互逻辑。
- **统一基类**: 所有客户端都继承自 `clients/base_client.py` 中的 `BaseClient` 类，共享通用的异步网络请求、日志和错误处理功能。
- **解耦与隔离**: 将所有外部 API 的复杂性、认证方式和数据解析逻辑都封装在各自的客户端内部。

## 2. 核心客户端概览

- **`base_client.py`**: 所有客户端的父类，提供了 `_request`, `get`, `post` 等基础网络请求方法。

- **`notion_client.py`**: 负责与 Notion API 的所有交互。这是最核心的客户端之一。

- **`brand_cache.py`**: 维护一个品牌信息的本地缓存。

- **`dlsite_client.py`**: 负责从 DLsite 网站搜索和抓取游戏信息。**其 Selenium 部分用于抓取品牌页面上的额外信息（如Ci-en链接和图标）。该逻辑经过优化，通过延长超时时间（10秒）提高了抓取过程在慢速网络下的稳定性。为了解决动态加载问题，此部分现在使用 `EC.visibility_of_element_located` 来确保元素可见。同时，为了更精确地定位Ci-en链接，选择器已更新为 `.link_cien a`，确保了抓取的健壮性。**

- **`fanza_client.py`**: **[功能增强]** 负责从 Fanza (DMM) 网站搜索和抓取游戏信息。该客户端具有以下特性：
    - **双重搜索机制**: 优先使用 `dlsoft.dmm.co.jp` 接口进行搜索。如果无结果，它会自动**后备**到 `dmm.co.jp/mono/` 接口进行再次搜索，提高了搜索的成功率。
    - **智能解析器**: 在获取游戏详情时，它能根据 URL 的结构 (`/mono/` 或 `dlsoft`) 自动选择对应的 HTML 解析逻辑，以适应 DMM 不同时期和类型的页面布局。

- **`ggbases_client.py`**: 负责与 GGBases 网站交互，主要用于获取游戏资源信息。该客户端在解析 HTML 时，会利用 BeautifulSoup 的特性，根据页面 `meta` 标签智能判断编码（如 UTF-8, GBK 等），以保证标题等信息的正确显示。**其详情页抓取逻辑经过优化，能够通过等待通用页面元素（`<body>`）和更长的超时时间（10秒）来健壮地处理标签部分不存在或页面加载缓慢的情况，避免了抓取失败。**

- **`bangumi_client.py`**: **[功能增强]** 负责与 Bangumi API (bgm.tv) 交互，是获取规范化数据（特别是角色和制作人员信息）的关键。它内置了复杂的匹配逻辑：
    - **智能标题处理**: 在搜索前，会对关键词进行多次处理（如 `normalize_title`, `clean_title`），以应对不同网站对标题的细微差异。
    - **模糊匹配**: 使用 `rapidfuzz` 库计算候选项与关键词的相似度，以找出最准确的匹配结果。

## 3. 客户端使用须知 (重要)

为了确保稳定性和避免错误，在使用本模块中的客户端时，必须遵守以下约定：

### 3.1 调用方负责速率限制

- **约定**: 本模块中的所有客户端**均不内置**任何形式的 API 速率限制逻辑。
- **责任**: 在任何需要循环或批量调用客户端方法（如 `fill_missing_bangumi.py` 脚本）的场景下，**调用方必须自行实现**速率控制。
- **推荐实现**: 
    - **简单延时**: 在循环的每次迭代结束时加入 `await asyncio.sleep(seconds)`。
    - **并发控制 (推荐)**: 使用 `asyncio.Semaphore` 来限制并发任务的数量。例如，对于 Notion API（限制约为3次/秒），应使用 `Semaphore(3)`；对于 Bangumi API（限制较严格），应使用 `Semaphore(1)`。

### 3.2 Selenium 驱动的依赖注入

- **约定**: `DlsiteClient` 和 `GgBasesClient` 中部分需要执行 JavaScript 的高级功能（如抓取品牌额外信息、解析动态加载的页面），依赖于一个外部传入的 Selenium WebDriver 实例。
- **责任**: 这些客户端自身**不会**自动创建浏览器驱动。调用方（通常是 `context_factory.py` 或 `gui_worker.py`）必须通过 `DriverFactory` 获取一个驱动实例，然后通过客户端的 `set_driver(driver)` 方法将其**注入**进去。
- **检查**: 在调用任何可能使用 Selenium 的方法前，可以通过 `has_driver()` 方法来检查驱动是否已就绪。

### 3.3 交互的实现

- **约定**: `BangumiClient` 在需要用户选择或处理未知映射时，会通过 `InteractionProvider` 接口发起交互请求。
- **责任**: 调用方必须向 `BangumiClient` 的构造函数中传入一个 `InteractionProvider` 的有效实例 (`ConsoleInteractionProvider` 或 `GuiInteractionProvider`)，否则将在运行时引发错误。
