# 🌸 Otaku-Notion-Sync 超详细使用说明

## 一、项目简介

Otaku-Notion-Sync 是一个自动化同步二次元游戏、品牌和角色信息到 Notion 数据库的工具。它支持从 DLsite、Getchu、GGBases 等平台抓取数据，并通过标签映射、品牌归一等机制，保证多平台数据格式统一、内容规范。适合需要批量管理和归档游戏信息的用户，尤其是有 Notion 数据库需求的二次元爱好者。

---

## 二、快速开始

### 1. 安装 Python

- 推荐 Python 3.8 及以上版本。
- 可在 [Python 官网](https://www.python.org/downloads/) 下载并安装。

### 2. 安装依赖库

在项目根目录下打开终端，执行：

```bash
pip install -r requirements.txt
```

如未提供 requirements.txt，可手动安装：

```bash
pip install requests selenium beautifulsoup4 undetected-chromedriver
```

### 3. 配置 Chrome 浏览器驱动

- 下载 [ChromeDriver](https://chromedriver.chromium.org/downloads)，版本需与本地 Chrome 浏览器一致。
- 将 chromedriver.exe 放到系统 PATH 或项目根目录。

---

## 三、Notion 数据库准备

### 1. 注册并新建数据库

- 注册并登录 [Notion](https://www.notion.so/)。
- 新建三个数据库页面：
  - 游戏信息数据库（如“游戏记录”）
  - 品牌信息数据库（如“厂商信息”）
  - 角色信息数据库（如“角色记录”）

### 2. 获取数据库 ID 和 API Token

- 参考 [Notion API 官方文档](https://developers.notion.com/) 申请集成，获取 `integration token`。
- 打开每个数据库页面，复制页面链接中的数据库 ID（通常是一串 32 位字符）。
- 将 Token 和数据库 ID 填入 `config/config_token.py` 文件：

```python
NOTION_TOKEN = "你的 Notion API Token"
GAME_DB_ID = "你的游戏数据库ID"
BRAND_DB_ID = "你的品牌数据库ID"
CHARACTER_DB_ID = "你的角色数据库ID"
```

### 3. 配置字段名

- 检查 `config/config_fields.py` 文件，确保字段名与你的 Notion 数据库一致。
- 如需自定义字段，可在 Notion 数据库页面右上角“+”添加或修改字段，并同步到 config 文件。

---

## 4. Notion 字段设置指引（必看）

为了保证程序正常运行，请严格按照以下字段要求设置你的 Notion 数据库。以下为每个数据库的字段设置方法：

### ✅ 游戏信息数据库（游戏记录）

| 字段名称   | 类型         | 说明                           |
| ---------- | ------------ | ------------------------------ |
| 游戏名称   | 标题 (Title) | 游戏的主标题                   |
| 官方网站   | URL          | 官网地址                       |
| 游戏大小   | 富文本       | 格式不限，程序会自动识别 GB 单位 |
| 发售时间   | 日期         | 支持日期选择器                 |
| 剧本       | 多选         | 支持多个作者名                 |
| 原画       | 多选         | 支持多个原画师名               |
| 声优       | 多选         | 角色配音演员                   |
| 音乐       | 多选         | BGM 或 OP 等音乐创作者         |
| 标签       | 多选         | 游戏标签，支持程序自动同步     |
| 价格       | 数字         | 单位为日元                     |
| 游戏封面   | 文件 (图片)  | 游戏主图，用于展示             |
| 游戏厂商   | 关系         | 关联到“厂商信息”数据库         |
| GGBases资源| URL          | 链接到 GGBases 或 TG 资源页     |
| 游戏类型   | 多选         | 如 RPG、ACT、ADV 等            |
| Bangumi链接| URL          | 游戏在 Bangumi 的页面链接       |
| 游戏角色   | 关系         | 关联到“角色记录”数据库         |

💡 其他字段如评分、计算字段等可选设置，程序不会自动写入，但可用来自定义 Notion 视图和排序。

### ✅ 品牌信息数据库（厂商信息）

| 字段名称   | 类型         | 说明                           |
| ---------- | ------------ | ------------------------------ |
| 厂商名     | 标题 (Title) | 品牌主名，程序主键             |
| 图标       | 文件 (图片)  | 品牌 Logo，可选                |
| 官网       | URL          | 官方网站链接                   |
| 别名       | 富文本       | 可填写日文名、缩写等别称       |
| 简介       | 富文本       | 简要介绍品牌信息               |
| Ci-en      | URL          | 支持者平台页面（如有）         |
| Twitter    | URL          | 官方社交媒体                   |
| bangumi链接| URL          | 品牌在 Bangumi 的页面链接      |
| 公司地址   | 富文本       | 可填写品牌所在地区             |
| 生日       | 富文本       | 创建时间或初次发布作品的日期   |

### ✅ 角色信息数据库（角色记录）

| 字段名称   | 类型         | 说明                           |
| ---------- | ------------ | ------------------------------ |
| 角色名称   | 标题 (Title) | 角色主名                       |
| 别名       | 富文本       | 英文名、昵称、其他别称等       |
| 声优       | 富文本       | 配音演员名                     |
| 性别       | 单选         | 男 / 女 / 不明                 |
| 头像       | 文件 (图片)  | 角色图像                       |
| BWH        | 富文本       | 三围，格式自由                 |
| 身高       | 富文本       | 身高信息，如 160cm             |
| 简介       | 富文本       | 简要介绍                       |
| 详情页面   | URL          | Bangumi 角色详情页链接         |
| 生日       | 富文本       | 出生日期                       |
| 血型       | 单选         | A/B/O/AB/不明等                |
| 所属游戏   | 关系         | 关联到“游戏记录”数据库         |

### ⚙ 字段命名与映射说明（自动匹配逻辑）

- 程序通过 `config/config_fields.py` 文件中的字段名定义来与 Notion 数据库字段对应。
- 如果你对字段名进行了修改，请同步更新该文件中的映射。
- 程序只会写入已配置字段，未配置的字段将被跳过。
- 推荐在创建数据库时直接复制上述字段名，避免大小写或空格差异导致写入失败。

---

## 五、主要配置文件说明

| 文件路径                            | 作用                                 |
| :---------------------------------- | :----------------------------------- |
| `config/config_token.py`            | 填写 Notion API Token 和数据库 ID    |
| `config/config_fields.py`           | 定义各字段名，需与 Notion 数据库一致 |
| `mapping/brand_mapping.json`        | 品牌名称映射，统一多平台品牌名       |
| `mapping/tag_jp_to_cn.json`         | DLsite 日文标签到中文标签的翻译表    |
| `mapping/tag_ggbase.json`           | GGBases 标签到中文标签的映射表       |
| `mapping/tag_mapping_dict.json`     | 标签归一化映射，合并同义标签         |
| `cache/brand_extra_info_cache.json` | 品牌信息本地缓存，自动维护           |

---

## 六、使用流程（一步步操作）

### 1. 启动主程序

在 VS Code 终端或命令行中运行：

```bash
python main.py
```

### 2. 输入关键词抓取游戏

- 按提示输入游戏关键词（支持日文/中文）。
- 可在关键词后加 `-m`，进入 GGBases 手动选择模式。
- 程序会自动在 DLsite、Getchu 搜索并展示结果，手动选择目标游戏。

### 3. 查重与同步

- 程序自动检测 Notion 数据库中是否有相似游戏条目。
- 可选择新建、覆盖或跳过。
- 自动抓取详情页信息、品牌信息、标签、角色等，并写入 Notion。

### 4. 标签与品牌映射维护

- 新标签会自动追加到 `mapping/tag_jp_to_cn.json` 或 `mapping/tag_ggbase.json`，需定期人工补充翻译。
- 品牌名自动归一到 `mapping/brand_mapping.json`，保证多平台一致。

### 5. 辅助脚本（可选）

项目还提供了辅助脚本（在 `scripts/` 目录下），如：

- `auto_tag_completer.py`：批量补全标签，自动写入 Notion。
- `extract_brands.py`：导出所有品牌名到 txt 文件。
- `export_all_tags.py`：导出所有标签到 txt 文件。

运行方式：

```bash
python scripts/auto_tag_completer.py
```

---

## 七、常见问题与解决

- **标签未翻译/归类**：请定期检查 `mapping/tag_jp_to_cn.json` 和 `mapping/tag_ggbase.json`，补充中文翻译和归类。
- **品牌信息不全**：可手动补充 `mapping/brand_mapping.json`，或完善 Bangumi、DLsite、Getchu 品牌信息。
- **角色信息缺失**：请确保 `CHARACTER_DB_ID` 已配置，并检查角色相关字段。
- **Notion API 报错**：请检查 Token 和数据库 ID 是否正确，网络是否畅通。
- **浏览器驱动异常**：请确保 chromedriver 版本与 Chrome 浏览器匹配，路径配置正确。
- **字段名不一致**：确保 `config/config_fields.py` 字段名与你的 Notion 数据库一致。

---

## 八、维护建议

- 每次同步后检查 mapping 文件，及时补充和维护标签、品牌、角色信息，确保数据准确、统一。
- 定期备份 cache 文件和映射文件，防止数据丢失。
- 可根据实际需求扩展标签归类、品牌补全等规则。

---

## 九、免责声明与安全提醒

- 本项目部分标签可能包含 NSFW 内容，仅供数据归档和技术交流使用。
- 请勿上传任何敏感 Token 或个人隐私信息到公共仓库。
- 如有疑问或建议，欢迎在项目 Issues 区反馈！

---