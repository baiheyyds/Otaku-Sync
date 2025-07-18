# 🌸 Otaku-Notion-Sync 使用指南

## 一、项目简介

Otaku-Notion-Sync 是一个自动化同步二次元游戏、品牌和角色信息到 Notion 数据库的工具。它支持从 DLsite、Getchu、GGBases 等平台抓取数据，并通过标签映射、品牌归一等机制，保证多平台数据格式统一、内容规范。适合需要批量管理和归档游戏信息的用户，尤其是有 Notion 数据库需求的二次元爱好者。

---

## 二、准备工作

### 1. 安装 Python 环境

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

### 1. 新建数据库

在 Notion 中新建三个数据库页面：

- 游戏信息数据库（如“游戏记录”）
- 品牌信息数据库（如“厂商信息”）
- 角色信息数据库（如“角色记录”）

### 2. 获取数据库 ID 和 API Token

- 参考 [Notion API 官方文档](https://developers.notion.com/) 申请集成，获取 `integration token`。
- 打开数据库页面，复制页面链接中的数据库 ID（通常是一串 32 位字符）。
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

## 四、主要配置文件说明

| 文件路径 | 作用 |
| :--- | :--- |
| `config/config_token.py` | 填写 Notion API Token 和数据库 ID |
| `config/config_fields.py` | 定义各字段名，需与 Notion 数据库一致 |
| `mapping/brand_mapping.json` | 品牌名称映射，统一多平台品牌名 |
| `mapping/tag_jp_to_cn.json` | DLsite 日文标签到中文标签的翻译表 |
| `mapping/tag_ggbase.json` | GGBases 标签到中文标签的映射表 |
| `mapping/tag_mapping_dict.json` | 标签归一化映射，合并同义标签 |
| `cache/brand_extra_info_cache.json` | 品牌信息本地缓存，自动维护 |

---

## 五、使用流程

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

## 六、常见问题与解决

- **标签未翻译/归类**：请定期检查 `mapping/tag_jp_to_cn.json` 和 `mapping/tag_ggbase.json`，补充中文翻译和归类。
- **品牌信息不全**：可手动补充 `mapping/brand_mapping.json`，或完善 Bangumi、DLsite、Getchu 品牌信息。
- **角色信息缺失**：请确保 `CHARACTER_DB_ID` 已配置，并检查角色相关字段。
- **Notion API 报错**：请检查 Token 和数据库 ID 是否正确，网络是否畅通。
- **浏览器驱动异常**：请确保 chromedriver 版本与 Chrome 浏览器匹配，路径配置正确。
- **字段名不一致**：确保 `config/config_fields.py` 字段名与你的 Notion 数据库一致。

---

## 七、维护建议

- 每次同步后检查 mapping 文件，及时补充和维护标签、品牌、角色信息，确保数据准确、统一。
- 定期备份 cache 文件和映射文件，防止数据丢失。
- 可根据实际需求扩展标签归类、品牌补全等规则。

---

## 八、参考文档

- [Notion API 官方文档](https://developers.notion.com/)
- [DLsite 官网](https://www.dlsite.com/)
- [Getchu 官网](https://www.getchu.com/)
- [GGBases 官网](https://www.ggbases.com/)
- [Bangumi 官网](https://bangumi.tv/)

---

> 如有疑问或建议，欢迎在项目 Issues 区反馈！