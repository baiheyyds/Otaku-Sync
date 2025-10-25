<div align="center">
  <br>
  <h2 align="center">Otaku-Sync</h2>
  <p align="center">
    一款能自动同步 Galgame 游戏信息到 Notion 数据库的高效工具
  </p>
  <p align="center">
    <a href="https://github.com/baiheyyds/Otaku-Sync/actions">
      <img src="https://img.shields.io/github/actions/workflow/status/baiheyyds/Otaku-Sync/CI.yml?branch=main" alt="Build Status">
    </a>
    <a href="./LICENSE">
    <img src="https://img.shields.io/badge/License-GPLv3-blue.svg" alt="License: GPL v3">
    </a>
    <img src="https://img.shields.io/github/stars/baiheyyds/Otaku-Sync?style=social" alt="Stars">
    <img src="https://img.shields.io/github/issues/baiheyyds/Otaku-Sync" alt="Issues">
    <img src="https://img.shields.io/github/last-commit/baiheyyds/Otaku-Sync" alt="Last Commit">
  </p>
</div>

---

## 目录

- [✨ 项目特性](#-项目特性)
- [📸 截图](#-截图)
- [🎮 如何使用](#-如何使用)
- [🏗️ 技术架构](#️-技术架构)
- [📂 项目结构](#-项目结构)
- [🚀 快速开始 (环境配置)](#-快速开始-环境配置)
- [🔧 核心概念与维护](#-核心概念与维护)
- [🤝 贡献](#-贡献)
- [📜 授权协议 (License)](#-授权协议-license)
- [⚠️ 免责声明](#️-免责声明)
- [📞 联系](#-联系)

---

**Otaku-Sync** 是一个为 Galgame 和同人游戏爱好者打造的自动化信息管理解决方案。它能够从 **DLsite**, **Fanza**, **GGBases**, 以及 **Bangumi** 等主流平台抓取丰富的数据，并将其智能、规范地同步到你的个人 Notion 数据库中。

与繁琐的手动录入说再见。现在，你可以通过一个现代化的图形界面，轻松管理你的游戏收藏，并借助其强大的数据整合与映射能力，确保你的数据库信息高度统一和规范。

## ✨ 项目特性

-  **优雅的图形用户界面 (GUI)**: 提供一个现代化、直观的图形界面，让搜索、选择、同步的全过程一目了然。所有交互（如处理重复项、翻译新标签）都在可视化的对话框中完成，操作体验流畅。
-  **多模式操作：GUI、CLI 与批量处理**:
   -  **GUI 模式 (推荐)**: 为绝大多数用户提供开箱即用的图形化体验。
   -  **CLI 模式**: 保留了功能完整的命令行界面，适合高级用户或自动化脚本集成。
   -  **批量模式**: 提供独立的批量处理工具，用于定期维护和刷新数据库。
-  **多源数据聚合**: 同时从 DLsite, Fanza, GGBases, Bangumi 等多个权威平台获取游戏、品牌和角色信息。
-  **全周期信息同步**: 覆盖从游戏基本信息、发售日期、价格，到剧本、原画、声优、标签等全方位数据。
-  **智能数据处理**:
   -  **重复检测**: 在添加新游戏前进行智能相似度比对，并让你在GUI中轻松选择“更新现有条目”或“创建新条目”。
   -  **品牌归一**: 自动将不同平台的同一品牌（如「ゆずソフト」和「YUZUSOFT」）映射为统一记录。
   -  **标签映射**: 交互式地翻译日文标签，并将同义标签（如「NTR」和「寝取られ」）进行归类合并，所有操作均有GUI支持。
-  **角色信息关联**: 自动从 Bangumi 抓取游戏关联的角色、声优等信息，并建立关系链接。
-  **高度可定制**: 通过独立的映射文件和配置文件，你可以轻松自定义 Notion 字段、标签体系和品牌别名。
-  **高效稳定**: 采用异步 IO 和共享浏览器驱动等技术，显著提升抓取效率，节约系统资源。

## 📸 截图

![Otaku-Sync GUI 主界面](./assets/gui.png)
![数据统计](./assets/statistics.png)

## 🎮 如何使用

一切准备就绪后，你可以选择以下任一方式运行程序。

### 方式一：使用图形界面 (推荐)

在项目根目录运行 `run_gui.py` 启动图形化工具：

```bash
python run_gui.py
```

**使用流程:**
1.  在顶部的输入框中输入游戏关键词，然后点击“开始同步”按钮。
2.  程序会自动在后台搜索，并在下方的日志区域显示进度。
3.  当需要你进行选择时（例如，从多个搜索结果中选择一个，或处理一个重复游戏），程序会自动弹出对话框，引导你完成操作。
4.  同步完成后，结果会清晰地显示在日志中。

### 方式二：使用命令行

如果你偏爱命令行，可以运行 `main.py`：

```bash
python main.py
```

程序启动后，会提示你输入游戏关键词。

-  **普通模式**: 直接输入游戏名（日文或中文）并回车。
-  **手动模式**: 在关键词后追加 ` -m`，这会在需要时让你手动选择，而不是自动选择最优结果。
-  **退出**: 输入 `q` 或直接按 Ctrl+C。

### 方式三：使用批量更新工具

对于需要定期维护、保持数据与最新信息同步的用户，项目提供了一个强大的批量更新工具 `batch_updater.py`。

```bash
python batch_updater.py
```

**主要用途**:
- 遍历你的 Notion 数据库（可选择游戏、厂商或角色库）。
- 从 Bangumi 重新获取每个条目的最新数据。
- 将最新信息更新回 Notion，用于批量刷新和补全数据。

> 💡 **架构说明**: 本项目之所以能支持多种操作模式，得益于其核心的 **“交互提供者” (Interaction Provider)** 设计模式。该模式将核心业务逻辑与用户界面完全解耦，为 GUI 和 CLI 提供了不同的交互实现，从而保证了代码的可维护性和未来的可扩展性。

## 🏗️ 技术架构

本项目的核心设计思想是将 **业务逻辑** 与 **用户界面** 分离。

-   **核心逻辑 (`core/`)**: 包含所有的数据抓取、处理和同步逻辑，与具体 UI 实现无关。
-   **交互接口 (`core/interaction.py`)**: 定义了业务逻辑与 UI 之间通信的抽象“契约”。
-   **UI 实现 (GUI/CLI)**: 分别实现了交互接口，将后台请求转化为用户看得见的图形界面或命令行提示。

这种解耦设计使得项目可以轻松地适配未来可能出现的新界面（如 Web），而无需改动核心代码。更详细的架构说明，请参考项目内的 `GEMINI.md` 系列文档。

## 📂 项目结构

```
Otaku-Sync/
├── clients/              # 各平台（DLsite, Fanza等）的抓取客户端
├── config/               # 项目配置（Notion字段、API Token等）
├── core/                 # 核心业务逻辑
│   ├── interaction.py    # 交互提供者抽象接口
│   └── ...
├── gui/                  # GUI 界面
├── mapping/              # 品牌、标签等映射文件（可自定义）
├── scripts/              # 实用工具脚本
├── utils/                # 通用工具（日志、驱动、GUI桥接等）
├── .env.example          # 环境变量模板
├── run_gui.py            # 🚀 图形界面 (GUI) 程序入口
├── main.py               # ⌨️ 命令行 (CLI) 程序入口
└── requirements.txt      # Python 依赖库
```

## 🚀 快速开始 (环境配置)

*首次使用需要进行一些初始配置，无论你使用GUI还是CLI。*

### 1. 环境准备

-  **Python**: 推荐版本 `3.8` 或更高。
-  **Google Chrome**: 请确保你的电脑上已安装最新版的 Chrome 浏览器。

### 2. 依赖

本项目的关键依赖包括：

- **PySide6**: 用于构建图形用户界面。
- **Notion API**: 用于与 Notion 数据库进行交互。
- **Selenium**: 用于模拟浏览器操作，抓取动态加载的网页内容。
- **httpx**: 用于执行异步 HTTP 请求。

你可以在 `requirements.txt` 文件中查看完整的依赖列表。

### 3. 下载与安装

克隆本项目，进入目录，并安装所有依赖：

```bash
git clone https://github.com/baiheyyds/Otaku-Sync.git
cd Otaku-Sync
pip install -r requirements.txt
```

### 4. Notion 数据库准备 (关键步骤)

#### ① 创建数据库
在你的 Notion 中创建 **3 个** 新的数据库，分别用于存储游戏、品牌和角色信息。

#### ② 获取 Notion API Token
1. 访问 [Notion 集成页面](https://www.notion.so/my-integrations)。
2. 创建一个新的集成，并复制生成的 **"Internal Integration Token"** (`secret_...`)。

#### ③ 关联数据库与集成
回到你创建的每一个数据库，点击右上角的 `...` 菜单，选择 **"Add connections"**，然后选择你刚刚创建的集成。**每个数据库都需要执行此操作**。

#### ④ 获取数据库 ID
在浏览器中打开你的每个数据库页面，从 URL 中复制 32 位的数据库 ID。
`https://www.notion.so/你的工作区/THIS_IS_YOUR_DATABASE_ID?v=...`

### 5. 配置项目
1. 在项目根目录，复制 `.env.example` 并重命名为 `.env`。
2. 打开 `.env` 文件，填入你的 **Notion Token** 和三个 **数据库ID**。如果需要 Bangumi 功能，也请填入 **Bangumi Token**。

   ```ini
   # .env
   NOTION_TOKEN="secret_xxxxxxxx"
   GAME_DB_ID="你的游戏数据库ID"
   BRAND_DB_ID="你的厂商数据库ID"
   CHARACTER_DB_ID="你的角色数据库ID"
   BANGUMI_TOKEN="你的Bangumi API Token"
   ```
   > ⚠️ **安全警告**: `.env` 文件包含了你的私密信息，已被添加到 `.gitignore` 中。**绝对不要**将此文件上传到任何公共仓库！

### 6. 配置 Notion 字段 (必读)
为了让程序能正确写入数据，你的 Notion 数据库需要包含特定的字段。请严格按照下表创建或修改你的数据库属性。

<details>
<summary><b>展开查看 ✅ 游戏数据库 字段要求</b></summary>

| 字段名称 (需与 `config_fields.py` 保持一致) | 类型 (Type)              | 说明                       |
| :------------------------------------------ | :----------------------- | :------------------------- |
| `游戏名称`                                  | **标题 (Title)**         | **必需**，游戏主标题       |
| `游戏别名`                                  | 文本 (Rich Text)         | 游戏的其他常用名           |
| `游戏简介`                                  | 文本 (Rich Text)         | 游戏的故事梗概             |
| `游戏官网`                                  | 网址 (URL)               | 游戏的官方网站             |
| `DLsite链接`                                | 网址 (URL)               |                            |
| `Fanza链接`                                 | 网址 (URL)               |                            |
| `游戏大小`                                  | 文本 (Rich Text)         | 如 `1.2GB`                 |
| `发售时间`                                  | **日期 (Date)**          |                            |
| `剧本`                                      | **多选 (Multi-select)**  |                            |
| `原画`                                      | **多选 (Multi-select)**  |                            |
| `声优`                                      | **多选 (Multi-select)**  |                            |
| `音乐`                                      | **多选 (Multi-select)**  |                            |
| `标签`                                      | **多选 (Multi-select)**  |                            |
| `价格`                                      | **数字 (Number)**        |                            |
| `游戏封面`                                  | **文件 (Files & media)** |                            |
| `游戏厂商`                                  | **关系 (Relation)**      | **必需**，关联到品牌数据库 |
| `GGBases资源`                               | 网址 (URL)               |                            |
| `游戏类别`                                  | **多选 (Multi-select)**  | 如 `RPG`, `ADV`            |
| `Bangumi链接`                               | 网址 (URL)               |                            |
| `游戏角色`                                  | **关系 (Relation)**      | **必需**，关联到角色数据库 |

</details>

<details>
<summary><b>展开查看 ✅ 品牌数据库 字段要求</b></summary>

| 字段名称 (需与 `config_fields.py` 保持一致) | 类型 (Type)              | 说明                 |
| :------------------------------------------ | :----------------------- | :------------------- |
| `厂商名`                                    | **标题 (Title)**         | **必需**，品牌主名称 |
| `官网`                                      | 网址 (URL)               |                      |
| `图标`                                      | **文件 (Files & media)** | 品牌 Logo            |
| `别名`                                      | 文本 (Rich Text)         |                      |
| `简介`                                      | 文本 (Rich Text)         |                      |
| `Ci-en`                                     | 网址 (URL)               |                      |
| `Twitter`                                   | 网址 (URL)               |                      |
| `生日`                                      | 文本 (Rich Text)         |                      |
| `bangumi链接`                               | 网址 (URL)               |                      |
| `公司地址`                                  | 文本 (Rich Text)         |                      |

</details>

<details>
<summary><b>展开查看 ✅ 角色数据库 字段要求</b></summary>

| 字段名称 (需与 `config_fields.py` 保持一致) | 类型 (Type)              | 说明                 |
| :------------------------------------------ | :----------------------- | :------------------- |
| `角色名称`                                  | **标题 (Title)**         | **必需**，角色主名称 |
| `别名`                                      | 文本 (Rich Text)         |                      |
| `声优`                                      | 文本 (Rich Text)         |                      |
| `性别`                                      | **单选 (Select)**        |                      |
| `头像`                                      | **文件 (Files & media)** |                      |
| `BWH`                                       | 文本 (Rich Text)         | 三围                 |
| `身高`                                      | 文本 (Rich Text)         |                      |
| `简介`                                      | 文本 (Rich Text)         |                      |
| `详情页面`                                  | 网址 (URL)               |                      |
| `生日`                                      | 文本 (Rich Text)         |                      |
| `血型`                                      | **单选 (Select)**        |                      |

</details>

> 💡 **提示**: 如果你想修改 Notion 中的字段名，请务必同步修改 `config/config_fields.py` 文件中对应的字符串。

## 🔧 核心概念与维护

### 映射系统 (`mapping/` 目录)
这是 Otaku-Sync 的灵魂。通过维护该目录下的 JSON 文件，你可以实现高度自动化的数据整理。

-  `brand_mapping.json`: **品牌归一**。将不同写法（如 `YUZUSOFT` 和 `ゆずソフト`）映射到同一个品牌记录。
-  `tag_jp_to_cn.json` / `tag_fanza_to_cn.json`: **日文标签翻译**。当程序通过 GUI 或 CLI 询问你新标签的翻译时，你的选择会自动保存到这里。
-  `tag_mapping_dict.json`: **标签同义词合并**。将多个相似标签（如 `巨乳`, `爆乳`）归类到一个主标签下。

**维护建议**:
-  **即时维护**: 使用 GUI 时，程序会实时引导你完成翻译和映射，大大减轻了手动维护负担。
-  **备份**: `mapping/` 目录是你个性化配置的核心，建议定期备份。

## 🐛 疑难解答

- **Q: 我遇到了 `Auth` 相关的错误。**
- **A:** 请检查你的 `.env` 文件中的 `NOTION_TOKEN` 是否正确，以及你的集成是否已添加到相应的数据库中。

- **Q: 我遇到了 `KeyError` 或 `字段不存在` 相关的错误。**
- **A:** 请检查你的 Notion 数据库中的字段名是否与 `config/config_fields.py` 文件中的定义完全一致。

- **Q: 程序运行缓慢或卡住。**
- **A:** 请确保你的网络连接正常。如果问题仍然存在，请尝试重新启动程序。

## 💡 未来工作

- [ ] **添加更多数据源**: 支持更多游戏信息网站。
- [ ] **优化性能**: 进一步提高数据抓取和处理的速度。
- [ ] **完善文档**: 提供更详细的开发和使用文档。

## 🤝 贡献

欢迎任何形式的贡献！

-  如果你发现了 Bug，请在 [Issues](https://github.com/baiheyyds/Otaku-Sync/issues) 中提交详细报告。
-  如果你有新功能或改进建议，也欢迎提出 Issue 或提交 Pull Request。

## 📜 授权协议 (License)

本项目基于 [GNU GPL v3](./LICENSE) 许可证进行分发和使用。

## ⚠️ 免责声明

-  本项目仅供个人学习、技术研究和数据归档使用。请在遵守当地法律法规的前提下使用本工具。
-  项目抓取的部分内容可能包含 **NSFW** 元素，请谨慎使用。
-  请妥善保管你的 `.env` 文件和 Notion Token，切勿泄露。

## 📞 联系

如果你有任何问题或建议，欢迎通过以下方式联系我：

- **GitHub Issues**: [https://github.com/baiheyyds/Otaku-Sync/issues](https://github.com/baiheyyds/Otaku-Sync/issues)