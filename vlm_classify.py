# -*- coding: utf-8 -*-
"""
图片分类模块 v2.0.0 - 配置文件分离

核心改进：
1. 按内容语义分类，废除来源分类（B站/通讯）
2. 拆分截图垃圾桶为细分类别（学习资料/聊天记录/软件界面等）
3. 新增艺术风格分类（油画/厚涂/抽象/水墨等）
4. 合并学习笔记+考试题目为学习资料
5. 保留横屏/1比1比例分类（壁纸和头像实用场景）
6. 照片仅作为相机直出的兜底分类
"""

import shutil
import json
from pathlib import Path
from PIL import Image
from collections import defaultdict
import platformdirs

# ===== 默认分类体系（18个）=====
DEFAULT_CATEGORIES = [
    "人像写真", "风景自然", "插画绘画", "艺术风格", "AI生成",
    "学习资料", "好词好句", "聊天记录", "影视动漫",
    "海报设计", "表情包梗图", "动物萌宠", "美食生活",
    "软件界面", "横屏", "1比1", "照片", "其他",
]

# 默认旧分类名 → 扫描时仍需包含，以便迁移
DEFAULT_LEGACY_CATEGORIES = [
    "AI生成图片", "B站图片", "人像", "截图", "插画艺术",
    "通讯图片", "风景", "厚涂", "视频截图", "知识点截屏",
    "好词好句", "海报设计",
    "111", "DCIM",
]

DEFAULT_CATEGORY_KEYWORDS = {
    "人像写真": {
        "keywords": ["人物", "人像", "人脸", "自拍", "肖像", "女孩", "男孩", "美女", "帅哥",
                     "模特", "少女", "少年", "儿童", "男生", "女生", "男子", "女子",
                     "cosplay", "角色扮演", "古装", "汉服", "婚纱", "礼服", "写真",
                     "侧脸", "背影", "全身照", "半身照", "特写", "大头照",
                     "妆容", "发型", "穿搭", "街拍", "合影", "情侣",
                     "眼神", "微笑", "姿势", "站姿", "坐姿"],
        "filename_hints": ["portrait", "selfie", "people", "person", "model", "face", "headshot"],
    },
    "风景自然": {
        "keywords": ["风景", "风光", "自然", "山", "海", "湖", "森林", "天空", "日落", "日出",
                     "云", "雪山", "草原", "田野", "城市景观", "建筑", "夜景", "星空", "银河",
                     "河流", "瀑布", "海滩", "沙漠", "极光", "彩虹", "晚霞", "朝霞",
                     "月色", "全景", "地标", "名胜", "旅游", "旅行", "户外",
                     "园林", "公园", "花海", "湿地", "海岸", "峡谷", "冰川",
                     "梯田", "古镇", "村落", "倒影", "晨曦", "暮色", "黄昏",
                     "海岸线", "绿洲", "落日", "朝阳", "薄雾"],
        "filename_hints": ["landscape", "scenery", "view", "nature", "sunset", "sunrise"],
    },
    "插画绘画": {
        "keywords": ["插画", "漫画", "动漫", "二次元", "CG", "原画", "概念艺术",
                     "线稿", "简笔画", "q版", "萌系", "日系", "韩风",
                     "赛博朋克", "蒸汽波", "像素风", "lowpoly", "矢量", "扁平风",
                     "国潮", "新中式", "色块", "唯美", "梦幻", "治愈系",
                     "手绘插画", "数字绘画", "板绘"],
        "filename_hints": ["illust", "anime", "manga", "pixiv", "fanart", "drawing", "sketch", "artwork"],
    },
    "艺术风格": {
        "keywords": ["油画", "厚涂", "抽象", "水墨", "国画", "水彩", "彩铅", "素描",
                     "版画", "浮世绘", "壁画", "岩彩", "工笔画", "工笔", "写意", "泼墨", "白描",
                     "超现实", "立体主义", "印象派", "后印象派", "野兽派", "波普",
                     "文艺复兴", "巴洛克", "洛可可", "肌理画", "晕染",
                     "油画风", "厚涂风", "写实厚涂", "伪厚涂", "厚涂风格",
                     "敦煌", "美术", "画作", "手绘", "绘画", "涂鸦"],
        "filename_hints": ["painting", "oilpainting", "watercolor", "abstract"],
    },
    "AI生成": {
        "keywords": ["AI生成", "ai生成", "AI绘画", "Midjourney", "Stable Diffusion", "DALL-E",
                     "生成式", "AIGC", "文生图", "图生图", "AI创作", "AI绘图",
                     "智能绘画", "人工智能"],
        "filename_hints": ["jimeng", "kling", "midjourney", "mj_", "sd_", "stable_diffusion",
                          "dalle", "ai绘画", "ai生成", "即梦", "可灵", "文心一格",
                          "通义万相", "智谱", "画宇宙"],
    },
    "学习资料": {
        "keywords": ["笔记", "课件", "公式", "推导", "思维导图", "知识点", "教程",
                     "考点", "干货", "板书", "科普", "讲解", "解析",
                     "试卷", "考题", "答案", "选择题", "填空题", "解答题", "练习题",
                     "高考", "中考", "考试", "测验", "联考", "模拟",
                     "高数", "英语", "数学", "物理", "化学", "语文", "历史",
                     "微积分", "线性代数", "概率论", "图文教程", "资料",
                     "定义域", "值域", "函数", "方程", "不等式",
                     "复习", "备考", "刷题", "招生", "录取", "学习"],
        "filename_hints": [],
    },
    "好词好句": {
        "keywords": ["语录", "好词好句", "摘抄", "句子", "金句", "名言", "格言",
                     "诗句", "台词", "文案", "经典语录", "美文", "读书笔记",
                     "文字截图", "文字摘录", "诗词", "诗歌", "散文", "名句"],
        "filename_hints": [],
    },
    "聊天记录": {
        "keywords": ["聊天", "微信", "QQ", "对话", "群聊", "私信", "聊天记录",
                     "聊天截图", "朋友圈", "转账", "红包", "语音消息",
                     "群消息"],
        "filename_hints": ["wx_", "wechat", "mmexport", "wx_camera", "qq_", "qqimage",
                          "qqpic", "tim", "weixin"],
    },
    "影视动漫": {
        "keywords": ["电影", "电视剧", "剧照", "综艺", "MV", "影视", "番剧",
                     "视频截图", "影视截图", "电影截图", "剧集", "动画片",
                     "短视频", "视频画面", "动漫截图", "韩剧", "美剧", "日剧",
                     "纪录片"],
        "filename_hints": ["video", "movie", "film"],
    },
    "海报设计": {
        "keywords": ["海报", "宣传", "广告", "设计", "logo", "LOGO", "封面", "banner",
                     "邀请函", "平面设计", "排版", "字体设计", "品牌", "视觉设计",
                     "招贴", "传单", "名片", "画册", "展板", "易拉宝",
                     "主视觉", "KV", "横幅", "标语"],
        "filename_hints": ["poster", "banner", "cover", "design", "logo", "flyer", "kv"],
    },
    "表情包梗图": {
        "keywords": ["表情包", "梗图", "搞笑", "段子", "沙雕", "恶搞", "鬼畜",
                     "调侃", "meme", "火柴人", "暴漫",
                     "吐槽", "神评", "弹幕梗"],
        "filename_hints": ["meme", "emoji", "sticker"],
    },
    "动物萌宠": {
        "keywords": ["猫", "狗", "鸟", "宠物", "动物", "萌宠", "猫咪", "狗狗",
                     "兔子", "仓鼠", "鹦鹉", "鱼", "昆虫", "蜥蜴",
                     "柯基", "金毛", "哈士奇", "布偶", "英短", "橘猫",
                     "小猫", "小狗", "鹿", "马", "羊",
                     "松鼠", "熊猫", "企鹅", "海豚"],
        "filename_hints": ["cat", "dog", "pet", "animal"],
    },
    "美食生活": {
        "keywords": ["美食", "食物", "菜品", "烹饪", "餐厅", "甜品", "蛋糕",
                     "咖啡", "奶茶", "料理", "小吃", "火锅", "水果",
                     "面包", "零食", "饮品", "烧烤", "寿司", "披萨",
                     "早餐", "午餐", "晚餐", "下午茶", "厨房", "做饭",
                     "菜谱", "食材"],
        "filename_hints": ["food", "meal", "recipe", "cook"],
    },
    "软件界面": {
        "keywords": ["界面", "页面", "软件", "APP", "网页", "浏览器", "设置页面",
                     "桌面", "菜单", "搜索框", "商品页", "电商",
                     "支付界面", "二维码", "扫码", "通知栏", "状态栏",
                     "操作系统", "工具", "配置", "面板", "仪表盘",
                     "详情页", "列表页", "登录", "注册", "输入法",
                     "天气预报", "快递", "订单", "购物车"],
        "filename_hints": ["screenshot", "screen_shot", "screencapture", "screen_capture",
                          "capture", "dm_", "screen"],
    },
    "照片": {
        "keywords": ["照片", "实拍", "相机", "摄影", "纪实", "随拍", "抓拍",
                     "棚拍", "外拍", "旅拍", "证件照"],
        "filename_hints": ["photo", "camera", "dcim", "dsc_", "cannon", "sony", "nikon"],
    },
}

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".svg", ".ico", ".psd"}

# ===== 旧分类 → 新分类的默认映射（用于迁移时兜底） =====
LEGACY_MAPPING = {
    "AI生成图片": "AI生成",
    "人像": "人像写真",
    "插画艺术": "插画绘画",
    "风景": "风景自然",
    "厚涂": "艺术风格",
    "知识点截屏": "学习资料",
    "视频截图": "影视动漫",
    # B站图片, 通讯图片, 截图 → 需按内容重新判断，无法简单映射
}

# ===== 文件名强特征 → 分类（高置信度锁定） =====
FILENAME_STRONG_FEATURES = {
    "AI生成": ["jimeng", "kling", "midjourney", "mj_", "stable_diffusion", "sd_",
               "dalle", "即梦", "可灵", "文心一格", "通义万相", "智谱", "画宇宙"],
    "聊天记录": ["wx_camera", "mmexport", "wechat", "wx_", "qq_image", "qq_pic",
                "qq_", "tim_", "weixin", "com.tencent.mm", "com.tencent.mobileqq"],
}

# 动态状态变量
CATEGORIES = []
LEGACY_CATEGORIES = []
SCAN_CATEGORIES = []
CATEGORY_KEYWORDS = {}

def get_data_dir():
    """获取数据目录路径（操作系统标准应用数据目录）"""
    data_dir = Path(platformdirs.user_data_dir("VLM_Renamer", "AI_Renamer"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir

def load_categories():
    global CATEGORIES, LEGACY_CATEGORIES, SCAN_CATEGORIES, CATEGORY_KEYWORDS
    data_dir = get_data_dir()
    categories_file = data_dir / "categories.json"
    
    if categories_file.exists():
        try:
            with open(categories_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                CATEGORIES = data.get("categories", DEFAULT_CATEGORIES)
                LEGACY_CATEGORIES = data.get("legacy_categories", DEFAULT_LEGACY_CATEGORIES)
                CATEGORY_KEYWORDS = data.get("category_keywords", DEFAULT_CATEGORY_KEYWORDS)
        except Exception as e:
            print(f"⚠️ 加载 categories.json 失败: {e}，使用默认分类配置")
            CATEGORIES = DEFAULT_CATEGORIES.copy()
            LEGACY_CATEGORIES = DEFAULT_LEGACY_CATEGORIES.copy()
            CATEGORY_KEYWORDS = DEFAULT_CATEGORY_KEYWORDS.copy()
    else:
        CATEGORIES = DEFAULT_CATEGORIES.copy()
        LEGACY_CATEGORIES = DEFAULT_LEGACY_CATEGORIES.copy()
        CATEGORY_KEYWORDS = DEFAULT_CATEGORY_KEYWORDS.copy()
        save_categories()  # 生成默认配置
        
    SCAN_CATEGORIES = list(dict.fromkeys(CATEGORIES + LEGACY_CATEGORIES))

def save_categories():
    data_dir = get_data_dir()
    categories_file = data_dir / "categories.json"
    data = {
        "categories": CATEGORIES,
        "legacy_categories": LEGACY_CATEGORIES,
        "category_keywords": CATEGORY_KEYWORDS
    }
    try:
        with open(categories_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"⚠️ 保存 categories.json 失败: {e}")

# 初始化加载
load_categories()


def suggest_category(description, original_category, img_path=None, vlm_category=None):
    """建议分类 - 支持VLM直接分类和关键词匹配两种模式

    参数：
        description: 图片内容描述（VLM生成或文件名）
        original_category: 原始分类目录名
        img_path: 图片文件路径（可选）
        vlm_category: VLM直接给出的分类建议（可选，v7.0新增）

    策略：
        模式A（有VLM分类）：以VLM建议为主，文件名强特征可覆盖
        模式B（无VLM分类）：关键词得分制，与旧版类似但分类体系已更新
    """
    text_lower = description.lower()
    filename_lower = ""
    if img_path:
        filename_lower = img_path.stem.lower()

    # 映射旧分类名到新分类名（用于原始分类保护）
    mapped_original = LEGACY_MAPPING.get(original_category, original_category)

    # ===== 文件名强特征检测 =====
    strong_cat = None
    if filename_lower:
        for cat, markers in FILENAME_STRONG_FEATURES.items():
            if any(m in filename_lower for m in markers):
                strong_cat = cat
                break

    # ===== 模式A：VLM直接分类 =====
    if vlm_category and vlm_category in CATEGORIES:
        # 强特征覆盖VLM（仅当冲突时）
        if strong_cat and strong_cat != vlm_category:
            return strong_cat
        return vlm_category

    # ===== 模式B：关键词得分制 =====
    scores = defaultdict(int)

    # 1. 描述关键词得分
    for category, config in CATEGORY_KEYWORDS.items():
        keywords = config.get("keywords", [])
        for kw in keywords:
            if kw.lower() in text_lower:
                scores[category] += 2

    # 2. 文件名特征得分（权重更高）
    if filename_lower:
        for category, config in CATEGORY_KEYWORDS.items():
            hints = config.get("filename_hints", [])
            for hint in hints:
                if hint.lower() in filename_lower:
                    scores[category] += 5

    # 3. 强特征锁定（+10分）
    if strong_cat:
        scores[strong_cat] += 10

    # 4. 原始分类保护分（映射后的新分类名）
    if mapped_original in CATEGORIES:
        scores[mapped_original] += 2

    # 5. 降低"照片"优先级 — 照片仅作为兜底
    if "照片" in scores and scores["照片"] < 10:
        scores["照片"] -= 1

    # 6. 无得分时，尝试旧分类映射
    if not scores:
        if mapped_original in CATEGORIES and mapped_original != original_category:
            return mapped_original
        return original_category if original_category in CATEGORIES else "其他"

    best_cat = max(scores, key=lambda k: scores[k])
    best_score = scores[best_cat]
    orig_score = scores.get(mapped_original, 0)

    # 7. 迁移决策
    if best_cat == mapped_original:
        return mapped_original

    # 有强信号（>=10分）时直接迁移
    if best_score >= 10:
        return best_cat

    # 否则需要比原始分类高出至少2分才迁移
    if best_score - orig_score >= 2:
        return best_cat

    return mapped_original if mapped_original in CATEGORIES else "其他"


def check_ratio_category(img_path):
    """检测图片比例分类，横屏(16:9)和1比1优先级最高

    判定标准：
    - 横屏: 宽高比在 1.6 ~ 1.9 之间（覆盖16:9及其常见邻近比例）
    - 1比1: 宽高比在 0.95 ~ 1.05 之间（严格方形）
    """
    try:
        with Image.open(img_path) as img:
            w, h = img.size
            if h == 0:
                return None
            ratio = w / h
            # 16:9 横屏
            if 1.6 <= ratio <= 1.9:
                return "横屏"
            # 1:1 方形
            if 0.95 <= ratio <= 1.05:
                return "1比1"
    except Exception:
        pass
    return None


def run_classification_task(base_dir=r"e:\Picture"):
    """执行独立的重新分类任务

    此任务仅根据当前文件名（作为描述）和图片比例重新归类，不调用VLM。
    用于将旧分类体系下的文件迁移到新分类体系。
    """
    base_path = Path(base_dir)
    print("=" * 60)
    print("🚀 开始重新分类任务（v7.0 新分类体系）")
    print("说明：根据文件名关键词和图片比例重新归类，不调用大模型。")
    print(f"新分类体系：{len(CATEGORIES)} 个分类")
    print("=" * 60)

    # 确保所有新分类目录存在
    for cat in CATEGORIES:
        (base_path / cat).mkdir(exist_ok=True)

    total_processed = 0
    total_moved = 0
    move_log = []  # 记录所有移动操作

    for cat in SCAN_CATEGORIES:
        cat_dir = base_path / cat
        if not cat_dir.exists():
            continue

        # 收集文件列表（避免迭代中修改目录）
        files = [f for f in cat_dir.iterdir()
                 if f.is_file() and f.suffix.lower() in IMAGE_EXTS]

        for img_path in files:
            total_processed += 1
            description = img_path.stem  # 已重命名的文件名即为描述
            original_category = cat

            # 判断新分类
            ratio_cat = check_ratio_category(img_path)
            if ratio_cat:
                new_cat = ratio_cat
            else:
                new_cat = suggest_category(description, original_category, img_path)

            if new_cat != original_category:
                dst_dir = base_path / new_cat
                dst_dir.mkdir(exist_ok=True)
                new_name = description
                suffix = img_path.suffix.lower()
                new_path = dst_dir / f"{new_name}{suffix}"

                # 防冲突
                counter = 1
                while new_path.exists():
                    if img_path.resolve() == new_path.resolve():
                        break
                    new_path = dst_dir / f"{new_name}_{counter}{suffix}"
                    counter += 1

                if img_path.resolve() != new_path.resolve():
                    try:
                        shutil.move(str(img_path), str(new_path))
                        print(f"  ✅ [{original_category}] → [{new_cat}] | {img_path.name[:50]}")
                        total_moved += 1
                        move_log.append({
                            "file": img_path.name,
                            "from": original_category,
                            "to": new_cat
                        })
                    except Exception as e:
                        print(f"  ❌ 移动失败: {img_path} → {new_path}, 错误: {e}")

    # 汇总统计
    print("\n" + "=" * 60)
    print(f"🎉 分类任务完成！共检查 {total_processed} 张图片，重新分类 {total_moved} 张")
    print("=" * 60)

    # 显示各目录最终文件数
    print("\n📊 各分类文件数：")
    total_files = 0
    for cat in CATEGORIES:
        cat_dir = base_path / cat
        if cat_dir.exists():
            c = sum(1 for _ in cat_dir.iterdir() if _.is_file())
            total_files += c
            if c > 0:
                print(f"  {cat}: {c}")

    # 显示旧分类剩余文件
    print("\n📦 旧分类剩余（待后续VLM精细处理）：")
    for cat in LEGACY_CATEGORIES:
        if cat in CATEGORIES:
            continue
        cat_dir = base_path / cat
        if cat_dir.exists():
            c = sum(1 for _ in cat_dir.iterdir() if _.is_file())
            if c > 0:
                total_files += c
                print(f"  {cat}: {c}")

    print(f"\n  总文件数: {total_files}")

    # 迁移流向统计
    if move_log:
        from collections import Counter
        flow = Counter(f"{m['from']} → {m['to']}" for m in move_log)
        print(f"\n📋 迁移流向（top 15）：")
        for f_, n in flow.most_common(15):
            print(f"  {f_}: {n}")


def get_default_base_dir():
    import sys
    from pathlib import Path
    data_dir = get_data_dir()
    config_file = data_dir / "config.json"
    if config_file.exists():
        import json
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            return cfg.get("base_dir", r"e:\Picture")
        except Exception:
            pass
    return r"e:\Picture"

if __name__ == "__main__":
    import sys
    base_directory = get_default_base_dir()
    if len(sys.argv) > 1:
        base_directory = sys.argv[1]
    run_classification_task(base_directory)
