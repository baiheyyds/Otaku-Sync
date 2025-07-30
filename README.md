
-----

````markdown
<div align="center">
  <br>
  <img width="120" src="https://youke1.picui.cn/s1/2025/07/25/68829b028b263.png" alt="Otaku-Sync Logo">
  <br>
  <h2 align="center">Otaku-Sync</h2>
</div>

<p align="center" style="color:#6a737d">
自动同步二次元游戏、品牌、角色信息到 Notion 数据库的高效工具
</p>

<p align="center">
  <a href="https://github.com/baiheyyds/Otaku-Sync/actions">
    <img src="https://img.shields.io/github/actions/workflow/status/baiheyyds/Otaku-Sync/CI.yml?branch=main" alt="Build Status">
  </a>
  <img src="https://img.shields.io/github/license/baiheyyds/Otaku-Sync" alt="License">
  <img src="https://img.shields.io/github/stars/baiheyyds/Otaku-Sync?style=social" alt="Stars">
  <img src="https://img.shields.io/github/issues/baiheyyds/Otaku-Sync" alt="Issues">
  <img src="https://img.shields.io/github/last-commit/baiheyyds/Otaku-Sync" alt="Last Commit">
</p>

---

## ✨ 项目简介

Otaku-Sync 是一个自动化同步 Galgame 和同人游戏及其品牌、角色信息到 Notion 数据库的工具。它支持从 **DLsite**、**Getchu**、**GGBases** 等平台抓取数据，并通过标签映射、品牌归一等机制，保证多平台数据格式统一、内容规范。

这个工具特别适合需要批量管理和归档游戏信息的用户，尤其是对 Notion 数据库有需求的二次元爱好者。

---

## 📖 目录

- [快速开始](#快速开始)
- [Notion 数据库准备](#notion-数据库准备)
- [Notion 字段设置指引（必看）](#notion-字段设置指引必看)
- [主要配置文件说明](#主要配置文件说明)
- [使用流程](#使用流程)
- [常见问题与解决](#常见问题与解决)
- [维护建议](#维护建议)
- [免责声明与安全提醒](#免责声明与安全提醒)
- [参考文档](#参考文档)

---

## 快速开始

### 1. 安装 Python

-   推荐 **Python 3.8** 及以上版本。
-   可在 [Python 官网](https://www.python.org/downloads/) 下载并安装。

### 2. 安装依赖库

本项目**强烈推荐使用 `requirements.txt` 文件**来安装所有依赖。
在项目根目录下打开终端，执行：

```bash
pip install -r requirements.txt
````

如果没有 `requirements.txt` 文件（请检查项目仓库，通常会提供），你也可以手动安装核心依赖：

```bash
pip install requests selenium beautifulsoup4 undetected-chromedriver notion-client
```

### 3\. 配置 Chrome 浏览器驱动

Otaku-Sync 使用 `undetected-chromedriver`，它通常可以**自动下载和管理**与你本地 Chrome 浏览器版本匹配的驱动。大多数情况下，你无需手动下载和配置 ChromeDriver。

如果程序运行出现驱动相关问题，你可以尝试：

  * **确保 Chrome 浏览器已更新到最新版本。**
  * **手动下载 ChromeDriver：** 从 [ChromeDriver 官网](https://chromedriver.chromium.org/downloads) 下载与你本地 Chrome 浏览器**完全一致**版本的 `chromedriver.exe`（Windows）或对应平台的文件。
  * **放置驱动文件：** 将下载的 `chromedriver.exe` 文件**放到本项目根目录**（即 `main.py` 所在的文件夹），或将其添加到你的系统 PATH 环境变量中（后者对于初学者可能稍复杂）。

-----

## Notion 数据库准备

### 1\. 注册并新建数据库

  - 注册并登录 [Notion](https://www.notion.so/)。
  - 新建三个数据库页面，例如分别命名为：
      - **游戏信息数据库**（如：“游戏记录”）
      - **品牌信息数据库**（如：“厂商信息”）
      - **角色信息数据库**（如：“角色记录”）

### 2\. 获取数据库 ID 和 API Token

1.  **获取 Notion API Token (集成令牌)：**

      * 登录 Notion。
      * 访问 [Notion 集成页面](https://www.google.com/search?q=https://www.notion.so/my-integrations)。
      * 点击 **“+ New integration”**。
      * 为你的集成命名（例如：`Otaku-Sync Integration`），选择你希望关联的**工作区**，然后点击 **“Submit”**。
      * 复制生成的 **“Internal Integration Token”**（这是你的 `NOTION_TOKEN`）。

2.  **分享数据库给集成：**

      * 打开你新建的**每个数据库页面**（游戏、品牌、角色数据库）。
      * 点击页面右上角的 `...` 菜单。
      * 向下滚动找到 **“Add connections”** 或 **“添加连接”**。
      * 在弹出的搜索框中找到并选择你刚刚创建的集成名称（例如：`Otaku-Sync Integration`）。

3.  **获取数据库 ID：**

      * 在 Notion 浏览器中打开你的**每个数据库页面**。
      * 复制页面链接中的数据库 ID。它通常是链接中 `notion.so/` 后面一串由 32 位字符组成的字符串，位于数据库名称之前，例如：`https://www.notion.so/你的用户名/d8f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0?v=...` 中的 `d8f0f0f0f0f0f0f0f0f0f0f0f0f0f0f0`。

4.  **填写配置文件：**

      * 将获取到的 Token 和数据库 ID 填入项目根目录下的 `config/config_token.py` 文件：

    <!-- end list -->

    ```python
    NOTION_TOKEN = "你的 Notion API Token"
    GAME_DB_ID = "你的游戏数据库ID"
    BRAND_DB_ID = "你的品牌数据库ID"
    CHARACTER_DB_ID = "你的角色数据库ID"
    ```

### 3\. 配置字段名

  - 检查 `config/config_fields.py` 文件，确保其中定义的字段名与你的 Notion 数据库中实际创建的字段名**完全一致**（包括大小写、空格）。
  - 如需自定义字段，你可以在 Notion 数据库页面右上角点击 **“+ 属性”** 添加或修改字段，并同步更新 `config/config_fields.py` 文件。

-----

## Notion 字段设置指引（必看）

为了保证程序正常运行，请严格按照以下字段要求设置你的 Notion 数据库。以下为每个数据库的字段设置方法：

### ✅ 游戏信息数据库（游戏记录）

| 字段名称 | 类型 | 说明 |
| :----------- | :------------- | :----------------------------------- |
| 游戏名称 | **标题 (Title)** | 游戏的主标题 |
| 官方网站 | **URL** | 官网地址 |
| 游戏大小 | **文本 (Text)** | 格式不限，程序会自动识别 GB 单位 |
| 发售时间 | **日期 (Date)** | 支持日期选择器 |
| 剧本 | **多选 (Multi-select)** | 支持多个作者名 |
| 原画 | **多选 (Multi-select)** | 支持多个原画师名 |
| 声优 | **多选 (Multi-select)** | 角色配音演员 |
| 音乐 | **多选 (Multi-select)** | BGM 或 OP 等音乐创作者 |
| 标签 | **多选 (Multi-select)** | 游戏标签，支持程序自动同步 |
| 价格 | **数字 (Number)** | 单位为日元 |
| 游戏封面 | **文件和媒体 (Files & Media)** | 游戏主图，用于展示 |
| 游戏厂商 | **关系 (Relation)** | 关联到“厂商信息”数据库 |
| GGBases资源 | **URL** | 链接到 GGBases 或其他资源页 |
| 游戏类型 | **多选 (Multi-select)** | 如 RPG、ACT、ADV 等 |
| Bangumi链接 | **URL** | 游戏在 Bangumi 的页面链接 |
| 游戏角色 | **关系 (Relation)** | 关联到“角色记录”数据库 |

💡 **提示：** 其他字段如评分、计算字段等可以根据你的需求自由设置，程序不会自动写入，但可用来自定义 Notion 视图和排序。

### ✅ 品牌信息数据库（厂商信息）

| 字段名称 | 类型 | 说明 |
| :--------- | :------------- | :---------------------------------- |
| 厂商名 | **标题 (Title)** | 品牌主名，程序主键 |
| 图标 | **文件和媒体 (Files & Media)** | 品牌 Logo，可选 |
| 官网 | **URL** | 官方网站链接 |
| 别名 | **文本 (Text)** | 可填写日文名、缩写等别称 |
| 简介 | **文本 (Text)** | 简要介绍品牌信息 |
| Ci-en | **URL** | 支持者平台页面（如有） |
| Twitter | **URL** | 官方社交媒体 |
| Bangumi链接 | **URL** | 品牌在 Bangumi 的页面链接 |
| 公司地址 | **文本 (Text)** | 可填写品牌所在地区 |
| 生日 | **文本 (Text)** | 创建时间或初次发布作品的日期 |

### ✅ 角色信息数据库（角色记录）

| 字段名称 | 类型 | 说明 |
| :--------- | :------------- | :------------------------------ |
| 角色名称 | **标题 (Title)** | 角色主名 |
| 别名 | **文本 (Text)** | 英文名、昵称、其他别称等 |
| 声优 | **文本 (Text)** | 配音演员名 |
| 性别 | **单选 (Select)** | 男 / 女 / 不明 |
| 头像 | **文件和媒体 (Files & Media)** | 角色图像 |
| BWH | **文本 (Text)** | 三围，格式自由 |
| 身高 | **文本 (Text)** | 身高信息，如 160cm |
| 简介 | **文本 (Text)** | 简要介绍 |
| 详情页面 | **URL** | Bangumi 角色详情页链接 |
| 生日 | **文本 (Text)** | 出生日期 |
| 血型 | **单选 (Select)** | A/B/O/AB/不明等 |
| 所属游戏 | **关系 (Relation)** | 关联到“游戏记录”数据库 |

### ⚙ 字段命名与映射说明（自动匹配逻辑）

  - 程序通过 `config/config_fields.py` 文件中的字段名定义来与 Notion 数据库字段对应。
  - 如果你对字段名进行了修改，请**务必同步更新该文件中的映射**。
  - 程序只会写入已配置字段，未配置的字段将被跳过。
  - **推荐在创建数据库时直接复制上述表格中的字段名和类型**，以避免大小写、空格或类型不匹配导致写入失败。

-----

## 主要配置文件说明

| 文件路径 | 作用 |
| :---------------------------------- | :----------------------------------- |
| `config/config_token.py` | 填写 Notion API Token 和数据库 ID |
| `config/config_fields.py` | 定义各字段名，需与 Notion 数据库一致 |
| `mapping/brand_mapping.json` | 品牌名称映射，统一多平台品牌名 |
| `mapping/tag_jp_to_cn.json` | DLsite 日文标签到中文标签的翻译表 |
| `mapping/tag_ggbase.json` | GGBases 标签到中文标签的映射表 |
| `mapping/tag_mapping_dict.json` | 标签归一化映射，合并同义标签 |
| `cache/brand_extra_info_cache.json` | 品牌信息本地缓存，自动维护 |

-----

## 使用流程

### 1\. 启动主程序

在 VS Code 终端或命令行中运行：

```bash
python main.py
```

### 2\. 输入关键词抓取游戏

  - 按提示输入游戏关键词（支持日文/中文）。
  - 可在关键词后加 `-m`，进入 GGBases 手动选择模式。
  - 程序会自动在 DLsite、Getchu 搜索并展示结果，让你手动选择目标游戏。

### 3\. 查重与同步

  - 程序自动检测 Notion 数据库中是否有相似游戏条目。
  - 你可以选择**新建**、**覆盖**或**跳过**。
  - 程序会自动抓取详情页信息、品牌信息、标签、角色等，并写入 Notion。

### 4\. 标签与品牌映射维护

  - 新标签会自动追加到 `mapping/tag_jp_to_cn.json` 或 `mapping/tag_ggbase.json`。这些新标签**需你定期人工补充中文翻译**。
  - 品牌名会自动归一到 `mapping/brand_mapping.json`，保证多平台一致。你可以根据需要手动调整这些映射。

### 5\. 辅助脚本（可选）

项目还提供了辅助脚本（在 `scripts/` 目录下），能帮助你更好地管理数据：

  - `auto_tag_completer.py`：批量补全 Notion 中已存在条目的标签，自动写入。
  - `extract_brands.py`：导出所有已识别的品牌名到 txt 文件。
  - `export_all_tags.py`：导出所有已识别的标签到 txt 文件。

运行方式示例：

```bash
python scripts/auto_tag_completer.py
```

-----

## 常见问题与解决

  - **标签未翻译/归类**：请定期检查并更新 `mapping/tag_jp_to_cn.json` 和 `mapping/tag_ggbase.json`，补充中文翻译和标签归类。
  - **品牌信息不全**：可在 `mapping/brand_mapping.json` 中手动补充或修正，或完善 Bangumi、DLsite、Getchu 等源平台的品牌信息。
  - **角色信息缺失**：请确保 `CHARACTER_DB_ID` 已在 `config/config_token.py` 中正确配置，并检查角色相关字段设置。
  - **Notion API 报错**：请仔细检查 `NOTION_TOKEN` 和数据库 ID 是否正确、完整，以及你的网络连接是否畅通。同时，确认你已将 Notion 数据库**分享给你的集成**。
  - **浏览器驱动异常**：请确保你的 Chrome 浏览器已是最新版本。如果问题依旧，尝试手动下载与 Chrome 版本匹配的 ChromeDriver，并将其放入项目根目录。
  - **字段名不一致**：请再次核对 `config/config_fields.py` 中的字段名是否与你的 Notion 数据库中**完全一致**。

-----

## 维护建议

  - 每次同步后，请检查 `mapping` 文件夹下的映射文件，及时补充和维护标签、品牌、角色信息，以确保数据准确、统一。
  - 定期备份 `cache` 文件和 `mapping` 文件，防止数据丢失，这对于你的自定义配置非常重要。
  - 你可以根据实际需求，扩展标签归类、品牌补全等逻辑，让工具更贴合你的使用习惯。

-----

## 免责声明与安全提醒

  - 本项目旨在提供一个自动化数据归档和技术交流的工具。请用户遵守所在地的法律法规，合理使用本工具。
  - 本项目部分标签可能包含 NSFW（不适宜在工作场合观看）内容，**仅供个人数据归档和技术研究使用**。
  - **请勿**将任何敏感 Token 或个人隐私信息（如 `config_token.py` 文件）上传到公共仓库，这可能会导致你的 Notion 账户被他人访问。建议将其添加到 `.gitignore` 文件中。
  - 如有任何疑问或改进建议，欢迎随时在项目 Issues 区反馈！

-----

## 参考文档

  - [Notion API 官方文档](https://developers.notion.com/)
  - [Bangumi API](https://bangumi.github.io/api/)

<!-- end list -->

```
```