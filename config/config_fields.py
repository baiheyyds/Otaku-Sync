# config/config_fields.py
# 该文件用于定义 Notion 数据库的字段名
FIELDS = {
    ##游戏记录数据库
    "game_name": "游戏名称",
    "game_url": "官方网站",
    "game_size": "游戏大小",
    "release_date": "发售时间",
    "script": "剧本",
    "illustrator": "原画",
    "voice_actor": "声优",
    "music": "音乐",
    "tags": "标签",
    "price": "价格",
    "cover_image": "游戏封面",
    "brand_relation": "游戏厂商",
    "resource_link": "GGBases资源",
    "game_type": "游戏类型",
    "bangumi_url": "Bangumi链接",
    "game_characters": "游戏角色",
    ##游戏厂商数据库
    "brand_name": "厂商名",
    "brand_official_url": "官网",
    "brand_icon": "图标",
    "brand_name": "厂商名",  # ✅ title
    "brand_alias": "别名",  # ✅ rich_text
    "brand_summary": "简介",  # ✅ rich_text
    "brand_cien": "Ci-en",  # ✅ url
    "brand_twitter": "Twitter",  # ✅ url
    "brand_birthday": "生日",  # ✅ rich_text
    "brand_bangumi_url": "bangumi链接",
    "brand_company_address": "公司地址",
    # 以下为角色信息数据库字段
    "character_name": "角色名称",
    "character_alias": "别名",  # 如 Fia 英文名等
    "character_cv": "声优",
    "character_gender": "性别",
    "character_avatar": "头像",  # 图片
    "character_bwh": "BWH",  # 如果能提取（胸围/腰围/臀围）
    "character_height": "身高",  # 新增 身高 字段
    "character_summary": "简介",
    "character_url": "详情页面",  # Bangumi角色页面链接
    "character_birthday": "生日",  # rich_text
    "character_blood_type": "血型",  # select
}
