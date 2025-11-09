
import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List

import pytest

from core.interaction import InteractionProvider
from utils.tag_manager import TagManager


# 1. 假的“用户”
class MockInteractionProvider(InteractionProvider):
    def __init__(self):
        self.answers = {}
        self.prompts = []

    def set_answer(self, prompt_key: str, answer: Any):
        self.answers[prompt_key] = answer

    async def get_tag_translation(self, tag: str, source_name: str) -> str | None:
        self.prompts.append(f"translate:{tag}")
        return self.answers.get(f"translate:{tag}")

    async def get_concept_merge_decision(self, concept: str, candidate: str) -> str | None:
        self.prompts.append(f"merge:{concept}")
        return self.answers.get(f"merge:{concept}")

    # 其他未使用的抽象方法
    async def handle_new_bangumi_key(self, request_data: Dict[str, Any]) -> Dict[str, Any]: return {"action": "ignore_session"}
    async def get_bangumi_game_choice(self, search_term: str, candidates: List[Dict]) -> str | None: return None
    async def confirm_brand_merge(self, new_brand_name: str, suggested_brand: str) -> str: return "create"
    async def select_game(self, choices: list, title: str, source: str) -> int | str | None: return -1
    async def confirm_duplicate(self, candidates: list) -> str | None: return "skip"
    async def get_name_split_decision(self, text: str, parts: list) -> dict: return {"action": "keep", "save_exception": False}
    async def ask_for_new_property_type(self, prop_name: str) -> str | None: return "rich_text"

# 2. 测试环境
@pytest.fixture
def tag_manager_environment(tmp_path: Path):
    # 准备假的配置文件和数据
    jp_to_cn_path = tmp_path / "tag_jp_to_cn.json"
    jp_to_cn_data = {"需要合并的日文标签": "同义词标签"} # 这个日文标签会被翻译成一个同义词
    jp_to_cn_path.write_text(json.dumps(jp_to_cn_data, ensure_ascii=False), encoding="utf-8")

    mapping_dict_path = tmp_path / "tag_mapping_dict.json"
    mapping_dict_data = {"主标签": ["主标签", "同义词标签"]} # “同义词标签”应该被合并到“主标签”
    mapping_dict_path.write_text(json.dumps(mapping_dict_data, ensure_ascii=False), encoding="utf-8")

    mock_interaction = MockInteractionProvider()

    tag_manager = TagManager(
        jp_to_cn_path=str(jp_to_cn_path),
        fanza_to_cn_path=str(tmp_path / "fanza.json"),
        ggbase_path=str(tmp_path / "ggbase.json"),
        mapping_dict_path=str(mapping_dict_path),
        ignore_list_path=str(tmp_path / "ignore.json")
    )
    return tag_manager, mock_interaction

# 3. 核心测试函数
def test_tag_manager_full_process(tag_manager_environment):
    tag_manager, mock_interaction = tag_manager_environment

    # --- 准备 (Arrange) ---
    # 准备一组真实的日文标签
    dlsite_source_tags = ["新日文标签", "需要合并的日文标签"]

    # 设定假的“用户”的回答
    mock_interaction.set_answer("translate:新日文标签", "已翻译的新标签")
    mock_interaction.set_answer("merge:已翻译的新标签", "create")

    # --- 执行 (Act) ---
    final_tags = asyncio.run(tag_manager.process_tags(
        dlsite_tags=dlsite_source_tags,
        fanza_tags=[],
        ggbases_tags=[],
        interaction_provider=mock_interaction
    ))

    # --- 断言 (Assert) ---
    # 1. "新日文标签" -> 被翻译为 "已翻译的新标签", 然后作为一个新概念创建
    # 2. "需要合并的日文标签" -> 被翻译为 "同义词标签", 然后被合并进 "主标签"
    expected_tags = sorted(["已翻译的新标签", "主标签"]) # 最终结果应该是这两个标签
    assert final_tags == expected_tags

    # 验证提问流程是否正确
    assert "translate:新日文标签" in mock_interaction.prompts
    # “需要合并的日文标签”因为在文件里有翻译，所以不应该提问
    assert "translate:需要合并的日文标签" not in mock_interaction.prompts
    # “同义词标签”因为在映射文件里，所以不应该提问合并
    assert "merge:同义词标签" not in mock_interaction.prompts
