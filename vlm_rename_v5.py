# -*- coding: utf-8 -*-
"""
图片智能重命名和分类 - v7.0.3
改进点:
1. 重构分类体系 - 18个基于内容语义的分类，废除来源分类（B站/通讯）
2. VLM直接输出分类 - prompt返回JSON格式(description+category)，不再纯靠关键词
3. 新增艺术风格分类 - 油画/厚涂/抽象/水墨等强艺术风格单列
4. 拆分截图垃圾桶 - 截图内容分流到学习资料/聊天记录/软件界面等
5. 照片作为兜底分类 - 优先分到其他类别
6. 文件删除保护 / 线程异常捕获 / 失败重试(3次) / 多线程MD5扫描
7. 账号选择 / 模型选择 / 处理数量选择

v7.0.1 改进:
- 错误处理增强：区分超时/HTTP错误/网络错误，打印具体错误原因
- 缩短重试间隔(0.3s→0.1s)和内部重试次数(3→2)，降低请求超时(30s→15s)

v7.0.3 改进:
- 修复频繁超时：分离连接超时(5s)与读取超时(45s)，VLM推理需要更长读取时间
- 超时指数退避：超时后等待1s→2s→4s，给服务端恢复时间（替代固定0.1s立即重试）
- 缩小图片最大边800→600px，降低VLM推理时间和传输体积
- 单key重试次数2→3，减少因偶发超时直接切key的浪费

v7.0.2 改进:
- 配置分离：将账号、API信息、本地目录、重试次数等硬编码提取到 config.json，确保代码库脱敏
8. 比例分类保留 - 横屏(壁纸)和1比1(头像)优先级最高

版本号规则:
- 小修改（修bug、补充少量关键词等）: 更新后位，如 7.0.0 -> 7.0.1
- 大更改（新增分类、重构核心逻辑等）: 更新主/次版本号，如 7.0.1 -> 7.1.0 或 8.0.0
"""

# 当前版本号，每次修改请按上方规则同步更新
VERSION = "7.0.3"
import os, re, json, time, shutil, base64, requests, io, threading, sys, hashlib, traceback
from pathlib import Path
from PIL import Image
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

CONFIG_FILE = Path(__file__).parent / "config.json"
if not CONFIG_FILE.exists():
    print(f"⚠️ 配置文件不存在: {CONFIG_FILE}")
    print("请复制 config.example.json 为 config.json 并填入正确的配置。")
    sys.exit(1)

with open(CONFIG_FILE, "r", encoding="utf-8") as f:
    config_data = json.load(f)

ACCOUNTS = config_data.get("accounts", [])
if not ACCOUNTS:
    print("⚠️ 配置文件中未提供有效的账号(accounts)配置。")
    sys.exit(1)

API_ENDPOINT = config_data.get("api_endpoint", "https://ark.cn-beijing.volces.com/api/v3/chat/completions")
MODEL = config_data.get("default_model", "doubao-seed-2-0-lite-260428")

BASE_DIR = Path(config_data.get("base_dir", r"e:\Picture"))
LOG_FILE = BASE_DIR / "rename_log.json"
TEMP_FILE = BASE_DIR / "processed_files.txt"
MD5_FILE = BASE_DIR / "processed_md5.txt"
ERROR_LOG = BASE_DIR / "error_log.txt"

BATCH_SIZE = config_data.get("batch_size", 500)
CURRENT_BATCH = 1
MAX_RETRIES = config_data.get("max_retries", 3)

def load_config():
    """加载配置文件"""
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def get_account_info(config, index=0):
    """获取指定索引的账号信息"""
    accounts = config.get("accounts", [])
    if index < 0 or index >= len(accounts):
        return accounts[0] if accounts else None
    return accounts[index]

def collect_images(base_dir=None):
    """收集所有待处理的图片"""
    if base_dir is None:
        base_dir = BASE_DIR
    else:
        base_dir = Path(base_dir)

    all_images = []
    for cat in SCAN_CATEGORIES:
        cat_dir = base_dir / cat
        if not cat_dir.exists():
            continue
        for f in cat_dir.iterdir():
            if f.is_file() and f.suffix.lower() in IMAGE_EXTS:
                all_images.append({"path": f, "original_category": cat})
    return all_images

from vlm_classify import CATEGORIES, SCAN_CATEGORIES, CATEGORY_KEYWORDS, IMAGE_EXTS, suggest_category, check_ratio_category

# ===== 双重去重系统 =====
processed_keys = set()     # 旧格式: 原分类/原文件名
processed_md5s = set()     # 新格式: MD5 hash

# 加载旧记录
if TEMP_FILE.exists():
    with open(TEMP_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                processed_keys.add(line)

# 加载MD5记录
if MD5_FILE.exists():
    with open(MD5_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                parts = line.split("|", 1)
                if len(parts) == 2:
                    processed_md5s.add(parts[0])

key_hits = 0
md5_hits = 0

# 线程同步
log_lock = threading.Lock()
print_lock = threading.Lock()
error_flag = threading.Event()
stats_lock = threading.Lock()
fail_lock = threading.Lock()
retry_lock = threading.Lock()

stats = {"processed": 0, "renamed": 0, "reclassified": 0, "errors": 0, "skipped": 0, "retried": 0}
consecutive_failures = {acc["name"]: 0 for acc in ACCOUNTS}
retry_count = {}  # 记录每张图片的重试次数

log_data = []
if LOG_FILE.exists():
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        log_data = json.load(f)


def log_error(msg):
    """记录错误日志"""
    with open(ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


def file_md5(filepath):
    """快速MD5计算"""
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def is_processed(img_path, original_cat):
    """双重判断：先查旧格式，再查MD5"""
    global key_hits, md5_hits
    old_key = f"{original_cat}/{img_path.name}"
    if old_key in processed_keys:
        key_hits += 1
        return True
    try:
        md5 = file_md5(img_path)
        if md5 in processed_md5s:
            md5_hits += 1
            return True
    except:
        pass
    return False


def record_processed(old_key, pre_md5=None):
    """记录处理完成（路径+MD5）"""
    processed_keys.add(old_key)
    with open(TEMP_FILE, "a", encoding="utf-8") as f:
        f.write(f"{old_key}\n")
    if pre_md5:
        processed_md5s.add(pre_md5)
        with open(MD5_FILE, "a", encoding="utf-8") as f:
            f.write(f"{pre_md5}|{old_key}\n")
    else:
        with print_lock:
            print(f"  ⚠️ MD5计算失败，仅记录路径: {old_key}")


def record_processed_with_md5(old_key, pre_md5=None):
    """兼容别名"""
    record_processed(old_key, pre_md5)


def check_file_exists(img_path):
    """检查文件是否存在，不存在则记录"""
    if not img_path.exists():
        log_error(f"文件不存在: {img_path}")
        return False
    return True


def compress_image(image_path, max_size_kb=80):
    """压缩图片，带文件存在检查"""
    # 首先检查文件是否存在
    if not check_file_exists(image_path):
        raise FileNotFoundError(f"文件不存在: {image_path}")
    
    try:
        img = Image.open(image_path)
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        elif img.mode != "RGB":
            img = img.convert("RGB")
        max_dim = 600
        w, h = img.size
        if max(w, h) > max_dim:
            ratio = max_dim / max(w, h)
            img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
        for quality in [75, 60, 45, 30]:
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality)
            if buf.tell() / 1024 <= max_size_kb:
                buf.seek(0)
                return base64.b64encode(buf.read()).decode("utf-8")
        w, h = img.size
        img = img.resize((w // 2, h // 2), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=30)
        buf.seek(0)
        return base64.b64encode(buf.read()).decode("utf-8")
    except Exception as e:
        # 如果压缩失败，尝试直接读取原文件
        if check_file_exists(image_path):
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        raise


# VLM分类列表（不含比例分类，比例分类由系统自动判定）
VLM_CATEGORIES = [c for c in CATEGORIES if c not in ("横屏", "1比1")]
VLM_CATEGORY_LIST = "、".join(VLM_CATEGORIES)

VLM_PROMPT = f"""请分析这张图片，返回JSON格式：
{{"description": "简洁中文内容描述，不超过20字，适合作文件名", "category": "从以下类别选一个：{VLM_CATEGORY_LIST}"}}
注意：只返回JSON，不要其他文字。description不要包含特殊字符（/:*?"<>|）"""


def parse_vlm_response(content):
    """解析VLM返回的JSON响应，提取description和category

    支持多种格式：纯JSON、markdown代码块包裹的JSON、纯文本回退
    """
    content = content.strip()

    # 尝试提取JSON（可能被markdown代码块包裹）
    json_match = re.search(r'\{[^}]+\}', content)
    if json_match:
        try:
            data = json.loads(json_match.group())
            desc = data.get("description", "").strip()
            cat = data.get("category", "").strip()
            if desc:
                desc = re.sub(r'[\\/:*?"<>|]', '', desc).replace('\n', ' ').replace('\r', '')
                # 验证category是否有效
                vlm_cat = cat if cat in CATEGORIES else None
                return desc[:30], vlm_cat
        except json.JSONDecodeError:
            pass

    # 回退：当作纯描述文本处理（兼容旧模型不返回JSON的情况）
    content = re.sub(r'[\\/:*?"<>|]', '', content).replace('\n', ' ').replace('\r', '')
    return content[:30], None


def analyze_image(image_path, account_info):
    """分析图片，返回 (description, vlm_category) 元组

    vlm_category 可能为 None（当VLM未返回有效分类时）
    """
    try:
        base64_image = compress_image(image_path)
    except Exception as e:
        log_error(f"压缩图片失败 {image_path}: {str(e)}")
        with print_lock:
            print(f"  ⚠️ 压缩失败: {str(e)[:60]}")
        return None, None

    account_name = account_info["name"]
    # 使用账号自定义模型，否则使用全局默认模型
    current_model = account_info.get("model", MODEL)
    last_error = None

    for key_idx, api_key in enumerate(account_info["keys"]):
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
        payload = {
            "model": current_model,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": VLM_PROMPT},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
            ]}],
            "max_tokens": 150, "temperature": 0.3
        }
        # 单key重试3次，给偶发超时更多恢复机会
        for attempt in range(3):
            try:
                # 分离超时：连接5秒（网络握手够用）+ 读取45秒（VLM推理需要时间）
                resp = requests.post(API_ENDPOINT, headers=headers, json=payload, timeout=(5, 45))
                resp.raise_for_status()
                raw_content = resp.json()['choices'][0]['message']['content'].strip()
                with fail_lock:
                    consecutive_failures[account_name] = 0
                return parse_vlm_response(raw_content)
            except requests.exceptions.Timeout:
                last_error = f"请求超时(key{key_idx+1}, 第{attempt+1}次)"
                # 超时指数退避：1s→2s→4s，给服务端喘息时间
                backoff = min(2 ** attempt, 4)
                time.sleep(backoff)
            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code if e.response else "未知"
                error_body = ""
                try:
                    error_body = e.response.text[:150] if e.response else ""
                except Exception:
                    pass
                last_error = f"HTTP {status_code}: {error_body[:100]}"
                # 429 限流等久一点，其他快速重试
                time.sleep(1.0 if status_code == 429 else 0.1)
            except requests.exceptions.ConnectionError:
                last_error = "网络连接失败"
                time.sleep(1.0)
            except Exception as e:
                last_error = f"{type(e).__name__}: {str(e)[:80]}"
                time.sleep(0.1)
        if key_idx < len(account_info["keys"]) - 1:
            with print_lock:
                print(f"  [{account_name}] 切换备用key (原因: {last_error})")

    # 所有key和重试均失败，打印并记录具体原因
    with print_lock:
        print(f"  ⚠️ [{account_name}] API失败: {last_error}")
    log_error(f"API调用失败 [{account_name}] {image_path.name}: {last_error}")

    with fail_lock:
        consecutive_failures[account_name] += 1
        if consecutive_failures[account_name] >= 3:
            error_flag.set()
    return None, None





def safe_move(src, dst_dir, new_name):
    """安全移动文件"""
    if not check_file_exists(src):
        return None
    dst_dir.mkdir(exist_ok=True)
    suffix = src.suffix.lower()
    new_path = dst_dir / f"{new_name}{suffix}"
    counter = 1
    while new_path.exists():
        new_path = dst_dir / f"{new_name}_{counter}{suffix}"
        counter += 1
    try:
        shutil.move(str(src), str(new_path))
        return new_path.name
    except Exception as e:
        log_error(f"移动文件失败 {src} -> {new_path}: {str(e)}")
        return None


def process_single_image(img_info, account_info, idx, total_tasks):
    """处理单张图片，返回(True成功, False失败, None跳过)"""
    img_path = img_info["path"]
    original_cat = img_info["original_category"]
    old_key = f"{original_cat}/{img_path.name}"
    account_name = account_info["name"]

    # 检查文件是否存在
    if not check_file_exists(img_path):
        with print_lock:
            print(f"  ⚠️ [{account_name}] 文件不存在，跳过: {img_path.name[:30]}")
        return None  # 跳过

    # 双重去重判断
    if is_processed(img_path, original_cat):
        with stats_lock:
            stats["skipped"] += 1
        return None  # 跳过

    with print_lock:
        print(f"[{account_name}][{idx+1}/{total_tasks}] {img_path.name[:45]}...")

    description, vlm_category = analyze_image(img_path, account_info)
    if not description:
        return False  # 失败，需要重试

    # 比例分类优先级最高：16:9 横屏 和 1:1 方形
    ratio_cat = check_ratio_category(img_path)
    if ratio_cat:
        new_cat = ratio_cat
    else:
        new_cat = suggest_category(description, original_cat, img_path, vlm_category=vlm_category)

    # 在移动文件之前，先计算MD5并记录
    pre_md5 = None
    try:
        pre_md5 = file_md5(img_path)
    except:
        pass

    new_filename = safe_move(img_path, BASE_DIR / new_cat, description)

    if not new_filename:
        return False  # 失败，需要重试

    reclassified = new_cat != original_cat
    with stats_lock:
        stats["processed"] += 1
        stats["renamed"] += 1
        if reclassified:
            stats["reclassified"] += 1

    tag = f" ({original_cat}->{new_cat})" if reclassified else ""
    with print_lock:
        print(f"  ✅ [{account_name}] {description}{tag}")

    # 双重记录（MD5已在移动前计算）
    record_processed_with_md5(old_key, pre_md5)

    # 写日志
    log_entry = {
        "original_path": str(img_path),
        "original_category": original_cat,
        "new_category": new_cat,
        "description": description,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    with log_lock:
        log_data.append(log_entry)
        if len(log_data) % 10 == 0:
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(log_data, f, ensure_ascii=False, indent=2)

    return True  # 成功

def process_single_image_api(img_info, account_info, auto_rename: bool = True, auto_move: bool = True):
    """API专用的单图处理函数，返回详细结果字典"""
    img_path = img_info["path"] if isinstance(img_info, dict) else Path(img_info)
    original_cat = img_info.get("original_category", "其他") if isinstance(img_info, dict) else "其他"
    old_key = f"{original_cat}/{img_path.name}"
    account_name = account_info["name"]

    result = {
        "success": False,
        "original_path": str(img_path),
        "original_category": original_cat,
        "description": None,
        "category": None,
        "new_filename": None,
        "new_path": None,
        "reclassified": False,
        "skipped": False,
        "error": None
    }

    # 检查文件是否存在
    if not check_file_exists(img_path):
        result["error"] = "文件不存在"
        result["skipped"] = True
        return result

    # 双重去重判断
    if is_processed(img_path, original_cat):
        result["error"] = "文件已处理过"
        result["skipped"] = True
        return result

    description, vlm_category = analyze_image(img_path, account_info)
    if not description:
        result["error"] = "图片分析失败"
        return result

    result["description"] = description
    result["category"] = vlm_category

    # 比例分类优先级最高：16:9 横屏 和 1:1 方形
    ratio_cat = check_ratio_category(img_path)
    if ratio_cat:
        new_cat = ratio_cat
    else:
        new_cat = suggest_category(description, original_cat, img_path, vlm_category=vlm_category)

    result["category"] = new_cat
    result["reclassified"] = new_cat != original_cat

    if not auto_rename and not auto_move:
        # 仅分析，不重命名不移动
        result["success"] = True
        return result

    # 在移动文件之前，先计算MD5并记录
    pre_md5 = None
    try:
        pre_md5 = file_md5(img_path)
    except:
        pass

    if auto_move:
        target_dir = BASE_DIR / new_cat
    else:
        target_dir = img_path.parent

    new_filename = safe_move(img_path, target_dir, description) if auto_rename else img_path.name

    if not new_filename:
        result["error"] = "文件移动/重命名失败"
        return result

    result["new_filename"] = new_filename
    result["new_path"] = str(target_dir / new_filename)
    result["success"] = True

    # 双重记录（MD5已在移动前计算）
    record_processed_with_md5(old_key, pre_md5)

    # 写日志
    log_entry = {
        "original_path": str(img_path),
        "original_category": original_cat,
        "new_category": new_cat,
        "description": description,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    with log_lock:
        log_data.append(log_entry)
        if len(log_data) % 10 == 0:
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(log_data, f, ensure_ascii=False, indent=2)

    return result


def worker_thread(account_info, task_queue, total_tasks):
    """工作线程 - 带异常捕获"""
    account_name = account_info["name"]

    while True:
        if error_flag.is_set():
            break
        
        try:
            task = task_queue.get(timeout=1)
        except:
            continue
            
        if task is None:
            break

        idx, img_info = task
        img_path = img_info["path"]
        
        # 获取当前重试次数
        with retry_lock:
            current_retries = retry_count.get(str(img_path), 0)

        try:
            result = process_single_image(img_info, account_info, idx, total_tasks)
            
            if result is None:
                # 跳过（已处理或文件不存在）
                task_queue.task_done()
            elif result is True:
                # 成功
                task_queue.task_done()
                time.sleep(0.15)
            else:
                # 失败，检查是否需要重试
                with retry_lock:
                    current_retries = retry_count.get(str(img_path), 0)
                    if current_retries < MAX_RETRIES:
                        retry_count[str(img_path)] = current_retries + 1
                        with stats_lock:
                            stats["retried"] += 1
                        with print_lock:
                            print(f"  🔄 [{account_name}] 第{current_retries+1}次重试: {img_path.name[:30]}")
                        # 重新放入队列
                        task_queue.put((idx, img_info))
                        task_queue.task_done()
                    else:
                        with stats_lock:
                            stats["errors"] += 1
                        with print_lock:
                            print(f"  ❌ [{account_name}] 重试{MAX_RETRIES}次后放弃: {img_path.name[:30]}")
                        log_error(f"处理失败(重试{MAX_RETRIES}次后放弃): {img_path}")
                        task_queue.task_done()
                        
        except Exception as e:
            # 捕获所有异常，防止线程崩溃
            error_msg = f"线程异常 [{account_name}]: {str(e)}\n{traceback.format_exc()}"
            log_error(error_msg)
            with print_lock:
                print(f"  💥 [{account_name}] 异常(已跳过): {str(e)[:60]}")
            
            # 异常后不再重试（文件可能已被另一线程处理）
            with stats_lock:
                stats["errors"] += 1
            
            task_queue.task_done()


def main():
    import queue

    global CURRENT_BATCH, key_hits, md5_hits, ACCOUNTS, BATCH_SIZE

    # 账号选择交互
    print("=== 账号选择 ===")
    print("1 → 仅使用135账号")
    print("2 → 仅使用177账号")
    print("直接回车 → 默认使用双账号")
    user_choice = input("请输入选择：").strip()
    
    # 过滤账号列表
    if user_choice == "1":
        ACCOUNTS = [ACCOUNTS[0]]
        print("✅ 已选择：仅使用135账号")
    elif user_choice == "2":
        ACCOUNTS = [ACCOUNTS[1]]
        print("✅ 已选择：仅使用177账号")
    else:
        print("✅ 已选择：使用双账号并发")
    print()

    # 模型选择交互
    print("=== 模型选择 ===")
    print(f"默认模型: {MODEL}")
    print("直接回车使用默认模型，输入新模型名则切换")
    
    for i, acc in enumerate(ACCOUNTS):
        if len(ACCOUNTS) > 1:
            prompt = f"请输入 {acc['name']} 使用的模型："
        else:
            prompt = "请输入使用的模型："
        
        model_input = input(prompt).strip()
        if model_input:
            # 复制账号对象并修改模型
            acc = acc.copy()
            acc["model"] = model_input
            ACCOUNTS[i] = acc
            print(f"✅ {acc['name']} 已切换为: {model_input}")
        else:
            print(f"✅ {acc['name']} 使用默认模型")
    print()

    # 处理数量选择交互
    print("=== 处理数量选择 ===")
    print(f"默认处理 500 张，输入 0 处理全部")
    count_input = input("请输入要处理的图片数量：").strip()
    
    if count_input:
        try:
            BATCH_SIZE = int(count_input)
            if BATCH_SIZE <= 0:
                BATCH_SIZE = 0
                print("✅ 已选择：处理全部待处理图片")
            else:
                print(f"✅ 已选择：每次处理 {BATCH_SIZE} 张")
        except ValueError:
            print(f"⚠️ 输入无效，使用默认值：每次处理 500 张")
    else:
        print(f"✅ 使用默认值：每次处理 500 张")
    print()

    if len(sys.argv) > 1:
        CURRENT_BATCH = int(sys.argv[1])

    # 清空错误日志
    if ERROR_LOG.exists():
        ERROR_LOG.unlink()

    # 第一步：扫描所有图片（包含新旧分类目录）
    all_images = []
    for cat in SCAN_CATEGORIES:
        cat_dir = BASE_DIR / cat
        if not cat_dir.exists():
            continue
        for f in cat_dir.iterdir():
            if f.is_file() and f.suffix.lower() in IMAGE_EXTS:
                all_images.append({"path": f, "original_category": cat})

    total_all = len(all_images)

    # 第二步：多线程过滤已处理图片（8线程并行MD5计算）
    pending_images = []
    skipped_count = 0

    def check_img_processed(img):
        if is_processed(img["path"], img["original_category"]):
            return True, img
        return False, img

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(check_img_processed, img) for img in all_images]
        for future in as_completed(futures):
            is_skipped, img = future.result()
            if is_skipped:
                skipped_count += 1
            else:
                pending_images.append(img)

    pending_count = len(pending_images)

    print("✅ MD5校验和去重完成，现在开始处理")
    print()

    # 第三步：取前N张待处理图片作为本次处理批次
    if BATCH_SIZE == 0:
        # 不分批，全部处理
        batch_images = pending_images
        batch_label = "全部"
    else:
        # 每次处理最多指定数量张
        batch_images = pending_images[:BATCH_SIZE]
        batch_label = f"单批次(最多{BATCH_SIZE}张)"

    print(f"总文件: {total_all} | 已处理: {skipped_count} | 待处理: {pending_count}")
    print(f"当前批次: {batch_label} (本批{len(batch_images)}张)")
    print(f"去重: 路径命中={key_hits}, MD5命中={md5_hits}")
    print(f"账号: {len(ACCOUNTS)}个账号并发")
    print(f"改进: 先过滤再分批✓ | 文件保护✓ | 异常捕获✓ | 失败重试({MAX_RETRIES}次)✓\n")

    if len(batch_images) == 0:
        print("✅ 没有需要处理的图片，全部完成！")
        return

    task_queue = queue.Queue()
    for idx, img_info in enumerate(batch_images):
        task_queue.put((idx, img_info))

    threads = []
    for acc in ACCOUNTS:
        t = threading.Thread(target=worker_thread, args=(acc, task_queue, len(batch_images)))
        t.daemon = True
        t.start()
        threads.append(t)

    task_queue.join()
    for _ in ACCOUNTS:
        task_queue.put(None)
    for t in threads:
        t.join(timeout=5)

    with log_lock:
        with open(LOG_FILE, "w", encoding="utf-8") as f:
            json.dump(log_data, f, ensure_ascii=False, indent=2)

    had_error = error_flag.is_set()

    print("\n" + "=" * 60)
    print(f"{'⚠️' if had_error else '✅'} 批次 {batch_label} 完成")
    print("=" * 60)
    print(f"  处理: {stats['processed']} | 重分类: {stats['reclassified']}")
    print(f"  重试: {stats['retried']} | 错误: {stats['errors']}")
    print(f"  剩余待处理: {pending_count - stats['processed']}")

    if ERROR_LOG.exists():
        error_count = sum(1 for _ in open(ERROR_LOG, "r", encoding="utf-8"))
        if error_count > 0:
            print(f"\n  错误日志: {ERROR_LOG} ({error_count}条)")

    total_files = 0
    for cat in SCAN_CATEGORIES:
        cat_dir = BASE_DIR / cat
        if cat_dir.exists():
            c = sum(1 for _ in cat_dir.iterdir() if _.is_file())
            if c > 0:
                total_files += c
                print(f"  {cat}: {c}")
    print(f"  总文件: {total_files}")

    if had_error:
        print("\n⚠️ 检测到异常，建议检查后继续。")


if __name__ == "__main__":
    main()
