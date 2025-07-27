# utils/field_helper.py
# 该模块用于处理字段相关的辅助函数
import json
import os

alias_path = os.path.join(os.path.dirname(__file__), "../config/field_aliases.json")
with open(alias_path, "r", encoding="utf-8") as f:
    FIELD_ALIASES = json.load(f)


def extract_aliases(infobox):
    aliases = []
    alias_keys = FIELD_ALIASES.get("brand_alias", [])
    for item in infobox:
        if item.get("key") in alias_keys and isinstance(item.get("value"), list):
            for alias_obj in item["value"]:
                if isinstance(alias_obj, dict):
                    if "v" in alias_obj:
                        aliases.append(alias_obj["v"])
                    elif isinstance(alias_obj, str):
                        aliases.append(alias_obj)
                elif isinstance(alias_obj, str):
                    aliases.append(alias_obj)
    return aliases


def extract_link_map(infobox):
    link_keys_map = {
        "官网": FIELD_ALIASES.get("brand_official_url", []),
        "Ci-en": FIELD_ALIASES.get("brand_cien", []),
        "Twitter": FIELD_ALIASES.get("brand_twitter", []),
        "Facebook": FIELD_ALIASES.get("brand_facebook", []),
        "DLsite": FIELD_ALIASES.get("brand_dlsite", []),
    }
    links = {}
    for item in infobox:
        if item.get("key") == "链接" and isinstance(item.get("value"), list):
            for kv in item["value"]:
                k, v = kv.get("k"), kv.get("v")
                if not v:
                    continue
                for lk, variants in link_keys_map.items():
                    if k in variants:
                        links[lk] = v
        else:
            key = item.get("key")
            val = item.get("value")
            if not val:
                continue
            for lk, variants in link_keys_map.items():
                if key in variants and isinstance(val, str) and val.strip():
                    links[lk] = val.strip()
    # 兼容 Twitter 账号格式
    if "Twitter" in links:
        tw = links["Twitter"]
        if tw.startswith("@"):
            links["Twitter"] = f"https://twitter.com/{tw[1:]}"
    return links


def extract_first_valid(infobox, keys):
    for key in keys:
        for item in infobox:
            if item.get("key") == key and item.get("value"):
                val = item["value"]
                if isinstance(val, list):
                    parts = []
                    for vobj in val:
                        if isinstance(vobj, dict) and "v" in vobj:
                            parts.append(str(vobj["v"]))
                        elif isinstance(vobj, str):
                            parts.append(vobj)
                    val_str = ", ".join(parts).strip()
                    if val_str:
                        return val_str
                elif isinstance(val, str):
                    val_str = val.strip()
                    if val_str:
                        return val_str
    return None
