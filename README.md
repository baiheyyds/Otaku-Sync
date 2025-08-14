<div align="center">
  <br>
  <img width="120" src="https://youke1.picui.cn/s1/2025/07/25/68829b028b263.png" alt="Otaku-Sync Logo">
  <br>
  <h2 align="center">Otaku-Sync</h2>
  <p align="center">
    一款能自动同步二次元游戏、品牌、角色信息到 Notion 数据库的高效工具
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

**Otaku-Sync** 是一个为 Galgame 和同人游戏爱好者打造的自动化信息管理解决方案。它能够从 **DLsite**, **Fanza**, **GGBases**, 以及 **Bangumi** 等主流平台抓取丰富的数据，并将其智能、规范地同步到你的个人 Notion 数据库中。

无论你是想建立一个私人的游戏资料库，还是希望高效地归档和管理自己的收藏，Otaku-Sync 都能为你节省大量手动录入的时间，并通过其强大的数据整合与映射能力，确保你的数据库信息高度统一和规范。

![Otaku-Sync 统计页面](https://raw.githubusercontent.com/baiheyyds/Otaku-Sync/main/assets/statistics.png)

## ✨ 项目特性

-  **多源数据聚合**: 同时从 DLsite, Fanza, GGBases, Bangumi 等多个权威平台获取游戏、品牌和角色信息。
-  **全周期信息同步**: 覆盖从游戏基本信息、发售日期、价格，到剧本、原画、声优、标签等全方位数据。
-  **智能数据处理**:
   -  **重复检测**: 在添加新游戏前进行智能相似度比对，避免重复录入。
   -  **品牌归一**: 自动将不同平台的同一品牌（如「ゆずソフト」和「YUZUSOFT」）映射为统一记录。
   -  **标签映射**: 自动翻译日文标签，并将同义标签（如「NTR」和「寝取られ」）进行归类合并。
-  **角色信息关联**: 自动从 Bangumi 抓取游戏关联的角色、声优等信息，并建立关系链接。
-  **高度可定制**: 通过独立的映射文件和配置文件，你可以轻松自定义 Notion 字段、标签体系和品牌别名。
-  **交互式命令行**: 在关键步骤（如选择搜索结果、处理新属性）提供清晰的交互式提示，让你完全掌控同步过程。
-  **高效稳定**: 采用异步 IO 和共享浏览器驱动等技术，显著提升抓取效率，节约系统资源。

## 📂 项目结构

```
Otaku-Sync/
├── cache/                # 自动生成的缓存文件
├── clients/              # 各个平台（DLsite, Fanza等）的抓取客户端
├── config/               # 项目配置
│   ├── config_fields.py  # Notion 数据库字段名映射
│   └── config_token.py   # 从 .env 加载 API Token 和 DB ID
├── core/                 # 核心业务逻辑（数据处理、同步流程等）
├── mapping/              # 品牌、标签等映射文件（可自定义）
├── utils/                # 通用工具（日志、驱动、相似度检查等）
├── .env.example          # 环境变量模板（重要）
├── .gitignore            # Git 忽略文件配置
├── main.py               # 🚀 主程序入口
├── README.md             # 你正在阅读的文档
└── requirements.txt      # Python 依赖库
```

## 🚀 快速开始

### 1. 环境准备

-  **Python**: 推荐版本 `3.8` 或更高。
-  **Google Chrome**: 请确保你的电脑上已安装最新版的 Chrome 浏览器。

### 2. 下载与安装

首先，克隆本项目到本地：

```bash
git clone https://github.com/baiheyyds/Otaku-Sync.git
cd Otaku-Sync
```

接着，安装所有必需的 Python 依赖库：

```bash
pip install -r requirements.txt
```

### 3. Notion 数据库准备（关键步骤）

#### ① 创建数据库

登录你的 [Notion](https://www.notion.so/)，创建 **3 个** 新的数据库页面，分别用于存储游戏、品牌和角色信息。例如：

-  `我的游戏收藏`
-  `游戏厂商信息`
-  `游戏角色库`

#### ② 获取 Notion API Token

1. 访问 [Notion 集成页面](https://www.notion.so/my-integrations)。
2. 点击 **"+ New integration"**，为你的集成命名（如 `Otaku-Sync Bot`），提交创建。
3. 复制生成的 **"Internal Integration Token"**，它看起来像 `secret_xxxxxxxx`。

#### ③ 关联数据库与集成

回到你创建的每一个数据库页面（游戏、品牌、角色），点击右上角的 `...` 菜单，选择 **"Add connections" / "添加连接"**，然后搜索并选择你刚刚创建的集成（如 `Otaku-Sync Bot`）。**每个数据库都需要执行此操作**。

#### ④ 获取数据库 ID

在浏览器中打开你的每个数据库页面，其 URL 格式如下：
`https://www.notion.so/你的工作区/THIS_IS_YOUR_DATABASE_ID?v=...`
复制链接中那串 32 位的字符串，这就是你的数据库 ID。

### 4. 配置项目

1. 在项目根目录，将 `.env.example` 文件复制一份并重命名为 `.env`。

   -  在 Windows (CMD) 上: `copy .env.example .env`
   -  在 Linux / macOS / Git Bash 上: `cp .env.example .env`

2. 打开新建的 `.env` 文件，填入你在上一步获取到的信息：

   ```ini
   # .env
   # --- Notion API 配置 ---
   NOTION_TOKEN="secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
   GAME_DB_ID="你的游戏数据库ID"
   BRAND_DB_ID="你的厂商数据库ID"
   CHARACTER_DB_ID="你的角色数据库ID"

   # --- Bangumi API 配置 (可选, 但强烈推荐) ---
   BANGUMI_TOKEN="你的Bangumi API Token"
   ```

   > ⚠️ **安全警告**: `.env` 文件包含了你的私密信息，已被添加到 `.gitignore` 中。**绝对不要**将此文件上传到任何公共仓库！

### 5. 配置 Notion 字段（必读）

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

## 🎮 如何使用

一切准备就绪后，在项目根目录运行主程序：

```bash
python main.py
```

程序启动后，会提示你输入游戏关键词。

-  **普通模式**: 直接输入游戏名（日文或中文）并回车。
-  **手动模式**: 在关键词后追加 ` -m`（例如：`抜きゲーみたいな島に住んでる貧乳はどうすりゃいいですか？ -m`），这会在 GGBases 搜索后让你手动选择结果，而不是自动选择热度最高的。
-  **退出**: 输入 `q` 或直接按 Ctrl+C。

程序将引导你完成游戏选择、查重、信息同步等所有步骤。

## 🔧 核心概念与维护

### 映射系统 (`mapping/` 目录)

这是 Otaku-Sync 的灵魂。通过维护该目录下的 JSON 文件，你可以实现高度自动化的数据整理。

-  `brand_mapping.json`: **品牌归一**。将不同写法（如 `YUZUSOFT` 和 `ゆずソフト`）映射到同一个品牌记录。
-  `tag_jp_to_cn.json`: **日文标签翻译**。程序发现未翻译的 DLsite 标签会自动追加到此文件，键值为空（`"新しいタグ": ""`）。你需要手动为其添加中文翻译。
-  `tag_ggbase.json`: **GGBases 标签映射**。同上，用于处理 GGBases 的标签。
-  `tag_mapping_dict.json`: **标签同义词合并**。将多个相似标签（如 `巨乳`, `爆乳`）归类到一个主标签下（如 `巨乳/爆乳`）。

**维护建议**:

-  **定期维护**: 每次同步一批游戏后，花几分钟检查 `mapping/` 目录下的文件，为新出现的标签补充翻译或归类。
-  **备份**: `mapping/` 目录是你个性化配置的核心，建议定期备份。

## 🤝 贡献

欢迎任何形式的贡献！

-  如果你发现了 Bug，请在 [Issues](https://github.com/baiheyyds/Otaku-Sync/issues) 中提交详细报告。
-  如果你有新功能或改进建议，也欢迎提出 Issue 或提交 Pull Request。

## 📜 授权协议 (License)

本项目基于 [GNU GPL v3](./LICENSE) 许可证进行分发和使用。

你可以自由复制、修改和分发本项目，但必须遵守 GPL v3 的相关条款。  
详细条款请见 [LICENSE](./LICENSE) 文件。

## ⚠️ 免责声明

-  本项目仅供个人学习、技术研究和数据归档使用。请在遵守当地法律法规的前提下使用本工具。
-  项目抓取的部分内容可能包含 **NSFW** (不适宜在工作场合观看) 元素，请谨慎使用。
-  请妥善保管你的 `.env` 文件和 Notion Token，切勿泄露。
