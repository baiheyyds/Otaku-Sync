# core/brand_handler.py
# 该模块用于处理品牌信息的获取和存储
import json
import os

mapping_path = os.path.join(os.path.dirname(__file__), "../mapping/brand_mapping.json")
with open(mapping_path, "r", encoding="utf-8") as f:
    brand_mapping = json.load(f)


def handle_brand_info(
    source,
    dlsite_client,
    notion_client,
    brand_name,
    brand_page_url,
    cache,
    brand_homepage=None,
    brand_icon=None,
    bangumi_client=None,
    getchu_client=None,
    getchu_brand_page_url=None,
):
    if not brand_name:
        print("⚠️ 品牌名为空，跳过品牌处理")
        return None

    # 规范品牌名
    for canonical, aliases in brand_mapping.items():
        if brand_name == canonical or brand_name in aliases:
            brand_name = canonical
            break

    bangumi_info = {}
    if bangumi_client:
        try:
            bangumi_info = bangumi_client.fetch_brand_info_from_bangumi(brand_name) or {}
            if bangumi_info:
                print(f"🎯 [{brand_name}] 从 Bangumi 获取品牌信息成功")
        except Exception as e:
            print(f"⚠️ [{brand_name}] Bangumi品牌信息抓取异常: {e}")

    extra = {}
    getchu_extra = {}

    # 根据 source 选择性调用
    if source == "dlsite":
        if brand_page_url:
            if brand_page_url in cache:
                extra = cache[brand_page_url]
                print(f"♻️ [{brand_name}] 使用品牌缓存（Dlsite）")
            else:
                extra = dlsite_client.batch_get_brand_extra_info_from_dlsite([brand_page_url]).get(brand_page_url, {})
                cache[brand_page_url] = extra
        else:
            print(f"⚠️ [{brand_name}] 品牌页链接为空，无法从 Dlsite 获取额外信息")
    elif source == "getchu":
        if getchu_brand_page_url:
            try:
                getchu_extra = getchu_client.get_brand_extra_info(getchu_brand_page_url) or {}
                if getchu_extra:
                    print(f"🎯 [{brand_name}] 从 Getchu 获取品牌信息成功")
            except Exception as e:
                print(f"⚠️ [{brand_name}] Getchu品牌信息抓取异常: {e}")
        else:
            print(f"⚠️ [{brand_name}] Getchu 品牌页链接为空，无法获取额外信息")
    else:
        # 其他情况：可以考虑都不补充或者补充其它来源
        pass

    def first_nonempty(*args):
        for v in args:
            if v:
                return v
        return None

    def combine_field(*fields):
        return first_nonempty(*fields)

    combined_info = {
        "official_url": combine_field(
            bangumi_info.get("homepage"),
            extra.get("官网"),
            getchu_extra.get("官网"),
            brand_homepage,
        ),
        "icon_url": combine_field(
            bangumi_info.get("icon"),
            extra.get("图标"),
            getchu_extra.get("图标"),
            brand_icon,
        ),
        "summary": combine_field(bangumi_info.get("summary"), extra.get("简介"), getchu_extra.get("简介")),
        "bangumi_url": bangumi_info.get("bangumi_url"),
        "company_address": combine_field(
            bangumi_info.get("company_address"),
            extra.get("公司地址"),
            getchu_extra.get("公司地址"),
        ),
        "birthday": combine_field(bangumi_info.get("birthday"), extra.get("生日"), getchu_extra.get("生日")),
        "alias": combine_field(bangumi_info.get("alias"), extra.get("别名"), getchu_extra.get("别名")),
        "twitter": combine_field(bangumi_info.get("twitter"), extra.get("推特"), getchu_extra.get("推特")),
    }

    return notion_client.create_or_update_brand(brand_name, **combined_info)
