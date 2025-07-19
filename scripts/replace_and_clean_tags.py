from os.path import abspath, dirname
from sys import path

path.append(dirname(dirname(abspath(__file__))))

from collections import Counter

from notion_client import Client

from config.config_fields import FIELDS
from config.config_token import GAME_DB_ID, NOTION_TOKEN
from mapping.tag_replace_map import tag_replace_map


def fetch_all_games(notion):
    results = []
    next_cursor = None
    while True:
        response = notion.databases.query(database_id=GAME_DB_ID, start_cursor=next_cursor, page_size=100)
        results.extend(response["results"])
        next_cursor = response.get("next_cursor")
        if not next_cursor:
            break
    return results


def replace_tags(original_tags, replace_map):
    old_names = [tag["name"] for tag in original_tags]
    new_names = set(replace_map.get(name, name) for name in old_names)
    changed = set(old_names) != new_names
    return list(new_names), changed


def delete_unused_tags(notion, database_id, tag_field_name, used_tags, dry_run=True):
    print("\n🧹 正在检测未使用标签...\n")

    db = notion.databases.retrieve(database_id=database_id)
    tag_field = db["properties"].get(tag_field_name)

    if not tag_field or tag_field["type"] != "multi_select":
        print("❌ 找不到标签字段定义，或字段不是 multi_select 类型")
        return

    current_options = tag_field["multi_select"]["options"]
    unused_tags = [opt["name"] for opt in current_options if opt["name"] not in used_tags]

    if not unused_tags:
        print("✅ 所有标签都有使用，无需清理")
        return

    print(f"🧹 共发现 {len(unused_tags)} 个未使用的标签：")
    for tag in unused_tags:
        print(f"   - {tag}")

    with open("unused_tags.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(unused_tags))

    print("\n📄 未使用标签已保存至 unused_tags.txt 文件，请在 Notion 中手动删除这些标签。")


def main(dry_run=True):
    notion = Client(auth=NOTION_TOKEN)
    tag_field = FIELDS["tags"]
    pages = fetch_all_games(notion)

    total_pages = len(pages)
    modified_pages = 0
    deleted_tag_counter = Counter()
    used_tags = set()

    print(f"✅ 共读取 {total_pages} 条游戏记录，开始检查标签替换...\n")

    for page in pages:
        props = page["properties"]
        tag_prop = props.get(tag_field)
        if not tag_prop or tag_prop["type"] != "multi_select":
            continue

        current_tags = tag_prop["multi_select"]
        current_names = [t["name"] for t in current_tags]
        used_tags.update(current_names)

        new_tags, changed = replace_tags(current_tags, tag_replace_map)

        replaced = [name for name in current_names if name in tag_replace_map]
        deleted_tag_counter.update(replaced)

        if changed:
            modified_pages += 1
            print(f"🟡 修改页面：{page['id']}")
            print(f"   原标签：{current_names}")
            print(f"   新标签：{new_tags}")

            if not dry_run:
                notion.pages.update(
                    page_id=page["id"],
                    properties={tag_prop["id"]: {"multi_select": [{"name": name} for name in new_tags]}},
                )
                print("✅ 已更新\n")
            else:
                print(f"🔍 [dry-run] 将移除旧标签：{replaced}\n")

    print("\n🎯 标签替换统计结果")
    print(f"📄 总页面数：{total_pages}")
    print(f"📝 被修改的页面数：{modified_pages}")
    print(f"❌ 被替换的旧标签总数：{sum(deleted_tag_counter.values())}")
    if deleted_tag_counter:
        print("📊 替换明细：")
        for tag, count in deleted_tag_counter.items():
            print(f"   - {tag}：{count} 次")

    delete_unused_tags(
        notion=notion, database_id=GAME_DB_ID, tag_field_name=tag_field, used_tags=used_tags, dry_run=dry_run
    )


if __name__ == "__main__":
    main(dry_run=False)
