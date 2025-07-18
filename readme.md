# Otaku-Notion-Sync 使用教程

## 项目简介

Otaku-Notion-Sync 是一个用于自动化同步和补全二次元游戏信息到 Notion 数据库的工具。它支持从 DLsite、Getchu、GGBases 等平台抓取游戏、品牌、标签等数据，并通过标签映射、品牌归一等机制，保证多平台数据格式统一、内容规范。项目适合需要批量管理和归档游戏信息的用户，尤其是有 Notion 数据库需求的二次元爱好者。

---

## 功能概览

- **自动抓取游戏信息**：支持 DLsite、Getchu、GGBases 多平台搜索与详情页解析。
- **品牌信息补全**：优先使用 Bangumi 补全品牌信息，DLsite/Getchu 作为补充。
- **标签自动映射与翻译**：自动将日文标签、GGBases标签映射为中文，并归一化处理。
- **查重机制**：新建游戏时自动检测相似条目，支持跳过/覆盖/新建。
- **自动补全 Notion 数据库**：游戏、品牌、角色等信息一键写入 Notion。
- **缓存机制**：品牌信息、游戏标题等均有本地缓存，提升运行效率。
- **标签和品牌映射文件自动维护**：新标签自动追加到映射文件，便于后续人工补充。

---

## 使用流程

### 1. 环境准备

- 安装 Python 3.8+，建议使用虚拟环境。
- 安装依赖库（如 requests、selenium、beautifulsoup4、undetected-chromedriver 等）。
- 配置 Notion API Token、数据库 ID（在 `config/config_token.py` 中填写）。
- 配置 Chrome 浏览器驱动（chromedriver），并确保可用。

### 2. 启动主程序

在 VS Code 终端或命令行中运行：

```bash
python main.py
```

### 3. 输入关键词抓取游戏

- 按提示输入游戏关键词（支持日文/中文）。
- 可在关键词后加 `-m`，进入 GGBases 手动选择模式。
- 程序会自动在 DLsite、Getchu 搜索并展示结果，手动选择目标游戏。

### 4. 查重与同步

- 程序自动检测 Notion 数据库中是否有相似游戏条目。
- 可选择新建、覆盖或跳过。
- 自动抓取详情页信息、品牌信息、标签等，并写入 Notion。

### 5. 标签与品牌映射维护

- 新标签会自动追加到 `mapping/tag_jp_to_cn.json` 或 `mapping/tag_ggbase.json`，需定期人工补充翻译。
- 品牌名自动归一到 `mapping/brand_mapping.json`，保证多平台一致。

---

## 主要模块说明

- `main.py`：主入口，负责整体流程控制、交互和数据同步。
- `clients/`：各平台抓取模块（DLsite、Getchu、GGBases、Bangumi、Notion）。
- `core/`：核心处理逻辑，包括游戏选择、品牌处理、游戏数据同步。
- `utils/`：工具函数，包括标签映射、查重、字段处理等。
- `mapping/`：标签、品牌等映射文件，支持自动追加和人工维护。
- `config/`：配置文件，包含字段名、Token、数据库ID等。

---

## 项目原理与逻辑

1. **关键词搜索**：用户输入关键词，程序优先在 DLsite 搜索，未找到则切换 Getchu。
2. **游戏选择**：展示搜索结果，用户手动选择目标游戏。
3. **查重机制**：自动检测 Notion 数据库中是否有相似游戏，避免重复创建。
4. **详情抓取**：自动抓取游戏详情页信息，包括品牌、发售日、容量、标签等。
5. **品牌补全**：优先用 Bangumi 补全品牌信息，DLsite/Getchu 作为补充，归一化品牌名。
6. **标签映射**：抓取到的标签自动查表翻译为中文，并归一化处理，保证标签规范。
7. **数据写入 Notion**：自动将游戏、品牌、角色等信息写入 Notion 数据库，支持新建和更新。
8. **缓存与映射维护**：品牌信息、游戏标题等有本地缓存，标签和品牌映射文件自动追加新内容，便于后续维护。

---

## 常见问题

- **标签未翻译/归类**：请定期检查 `mapping/tag_jp_to_cn.json` 和 `mapping/tag_ggbase.json`，补充中文翻译和归类。
- **品牌信息不全**：可手动补充 `mapping/brand_mapping.json`，或完善 Bangumi、DLsite、Getchu 品牌信息。
- **Notion API 报错**：请检查 Token 和数据库 ID 是否正确，网络是否畅通。
- **浏览器驱动异常**：请确保 chromedriver 版本与 Chrome 浏览器匹配，路径配置正确。

---

## 维护建议

- 每次同步后检查 mapping 文件，及时补充和维护标签、品牌信息，确保数据准确、统一。
- 定期备份 cache 文件和映射文件，防止数据丢失。
- 可根据实际需求扩展标签归类、品牌补全等规则。

---

## 参考文档

- [Notion API 官方文档](https://developers.notion.com/)
- [DLsite 官网](https://www.dlsite.com/)
- [Getchu 官网](https://www.getchu.com/)
- [GGBases 官网](https://www.ggbases.com/)
- [Bangumi 官网](https://bangumi.tv/)

---

如有疑问或建议，欢迎在项目 Issues 区反