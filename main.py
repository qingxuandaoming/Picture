from fastapi import FastAPI, HTTPException, Body
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import json
import os
import re
import shutil
import threading
import time
import uuid
import urllib.parse
import hashlib
import sys
import webbrowser
from typing import List, Dict, Optional
from PIL import Image
import platformdirs

from schemas import (
    BaseResponse, ConfigUpdate, ImageAnalyzeRequest, ImageAnalyzeResponse,
    BatchStartRequest, BatchProgressResponse, CategoryInfo,
    ImageRenameRequest, ImageMoveRequest, ImageDeleteRequest,
    CategoryConfigUpdate, AiAssistRequest
)
from vlm_rename_v5 import load_config, get_account_info, analyze_image, process_single_image_api, collect_images, CATEGORIES
from vlm_classify import CATEGORIES as ALL_CATEGORIES, suggest_category, check_ratio_category

app = FastAPI(title="AI图片重命名工具API", version="1.0.0")

# 添加CORS支持
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

USER_DATA_DIR = Path(platformdirs.user_data_dir("VLM_Renamer", "AI_Renamer"))
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = USER_DATA_DIR / "config.json"

def get_base_dir() -> Path:
    try:
        cfg = load_config()
        return Path(cfg.get("base_dir", r"e:\Picture"))
    except Exception:
        return Path(r"e:\Picture")

def get_log_file() -> Path:
    return USER_DATA_DIR / "rename_log.json"

def load_logs(log_file_path: Path) -> list:
    """安全地读取混合格式（JSON 数组 + 后来追加的 JSONL）的日志文件"""
    if not log_file_path.exists():
        return []
    try:
        with open(log_file_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
    except Exception:
        return []
    
    if not content:
        return []
        
    logs = []
    if content.startswith('['):
        try:
            logs = json.loads(content)
            if isinstance(logs, list):
                return logs
        except Exception:
            pass
        
        # 匹配第一个 JSON 数组结束 ']' 与下一个 JSON 对象的开始 '{' 之间的边界
        match = re.search(r'\]\s*\{', content)
        if match:
            boundary = match.start()
            array_part = content[:boundary+1]
            jsonl_part = content[boundary+1:]
        else:
            array_part = content
            jsonl_part = ""
            
        try:
            logs = json.loads(array_part)
            if not isinstance(logs, list):
                logs = []
        except Exception:
            logs = []
            
        if jsonl_part:
            for line in jsonl_part.split('\n'):
                line = line.strip()
                if line:
                    try:
                        logs.append(json.loads(line))
                    except Exception:
                        pass
        return logs
    else:
        logs = []
        for line in content.split('\n'):
            line = line.strip()
            if line:
                try:
                    logs.append(json.loads(line))
                except Exception:
                    pass
        return logs


# 任务存储
tasks = {}
tasks_lock = threading.Lock()

# ===== 任务统计持久化 =====
task_stats_lock = threading.Lock()

def _get_task_stats_file() -> Path:
    """获取任务统计文件路径"""
    return USER_DATA_DIR / "task_stats.json"

def load_task_stats():
    """加载任务统计"""
    stats_file = _get_task_stats_file()
    if stats_file.exists():
        try:
            with open(stats_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "total_processed": 0,
        "total_success": 0,
        "total_errors": 0,
        "total_renamed": 0,
        "total_reclassified": 0,
        "total_skipped": 0,
        "last_updated": None
    }

def save_task_stats(stats):
    """保存任务统计"""
    with task_stats_lock:
        stats["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            stats_file = _get_task_stats_file()
            with open(stats_file, "w", encoding="utf-8") as f:
                json.dump(stats, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存任务统计失败: {e}")

def update_task_stats(processed=0, success=0, errors=0, renamed=0, reclassified=0, skipped=0):
    """更新任务统计"""
    stats = load_task_stats()
    stats["total_processed"] += processed
    stats["total_success"] += success
    stats["total_errors"] += errors
    stats["total_renamed"] += renamed
    stats["total_reclassified"] += reclassified
    stats["total_skipped"] += skipped
    save_task_stats(stats)
    return stats

# ===== 任务处理函数 =====
def process_batch_task(task_id: str, base_dir: str, account_index: int, max_process: Optional[int],
                       auto_rename: bool, auto_move: bool, task_type: str = "rename", run_mode: int = 1):
    """后台批量处理任务"""
    import queue
    # 强制热加载 config.json 及 vlm_rename_v5 的全局变量
    from vlm_rename_v5 import load_global_config, is_processed, ACCOUNTS, process_single_image_api, error_flag, retry_count, MAX_RETRIES, log_lock, update_data_paths, reload_dedup_records
    load_global_config()

    try:
        if base_dir:
            task_base_dir = Path(base_dir)
        else:
            task_base_dir = get_base_dir()

        if not task_base_dir.exists():
            raise FileNotFoundError(f"指定的处理根目录不存在: {task_base_dir}")
            
        # 根据当前 run_mode 更新缓存文件路径，并重新加载去重记录
        update_data_paths(task_base_dir, run_mode)
        reload_dedup_records()

        # 收集图片
        images = collect_images(str(task_base_dir), run_mode=run_mode)
        available_folders = [d.name for d in task_base_dir.iterdir() if d.is_dir() and not d.name.startswith(('.', '_'))]

        if task_type == "classify":
            # 规则分类任务 (对应 vlm_classify.py)
            batch_images = images if (max_process is None or max_process <= 0) else images[:max_process]
            total = len(batch_images)

            with tasks_lock:
                if task_id in tasks:
                    tasks[task_id]["total"] = total
                    tasks[task_id]["name"] = "规则分类任务"

            if total == 0:
                with tasks_lock:
                    tasks[task_id]["status"] = "completed"
                    tasks[task_id]["progress"] = 100
                return

            for idx, img_info in enumerate(batch_images):
                img_path = img_info["path"]
                original_cat = img_info["original_category"]

                with tasks_lock:
                    if "processing_files" not in tasks[task_id]:
                        tasks[task_id]["processing_files"] = []
                    tasks[task_id]["processing_files"].append(str(img_path.name))

                try:
                    ratio_cat = check_ratio_category(img_path)
                    if ratio_cat:
                        new_cat = ratio_cat
                    else:
                        new_cat = suggest_category("image", original_cat, img_path, vlm_category=None)

                    # 移动文件
                    if auto_move and new_cat != original_cat:
                        dst_dir = task_base_dir / new_cat
                        dst_dir.mkdir(exist_ok=True)
                        new_path = dst_dir / img_path.name
                        counter = 1
                        while new_path.exists():
                            new_path = dst_dir / f"{img_path.stem}_{counter}{img_path.suffix}"
                            counter += 1
                        img_path.rename(new_path)

                        with tasks_lock:
                            tasks[task_id]["reclassified"] += 1

                    with tasks_lock:
                        tasks[task_id]["processed"] += 1
                        tasks[task_id]["results"].append({
                            "success": True,
                            "original_path": str(img_path),
                            "original_category": original_cat,
                            "category": new_cat,
                            "new_name": img_path.name
                        })
                except Exception as e:
                    with tasks_lock:
                        tasks[task_id]["errors"] += 1
                        tasks[task_id]["results"].append({
                            "success": False,
                            "original_path": str(img_path),
                            "original_category": original_cat,
                            "error": str(e)
                        })
                finally:
                    with tasks_lock:
                        if str(img_path.name) in tasks[task_id]["processing_files"]:
                            tasks[task_id]["processing_files"].remove(str(img_path.name))

                with tasks_lock:
                    tasks[task_id]["progress"] = min(100, int((idx + 1) / total * 100))

            with tasks_lock:
                tasks[task_id]["status"] = "completed"
                tasks[task_id]["progress"] = 100
                # 更新持久化统计
                update_task_stats(
                    processed=tasks[task_id]["processed"],
                    success=tasks[task_id]["processed"],
                    errors=tasks[task_id]["errors"],
                    renamed=0,
                    reclassified=tasks[task_id]["reclassified"],
                    skipped=tasks[task_id]["skipped"]
                )

        else:
            # VLM 智能重命名任务 (对应 vlm_rename_v5.py)
            # 1. 用多线程过滤已处理图片（8线程并行MD5计算）
            from concurrent.futures import ThreadPoolExecutor, as_completed
            pending_images = []
            skipped_count = 0

            def check_img_processed(img):
                if is_processed(img["path"], img["original_category"]):
                    return True, img
                return False, img

            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = [executor.submit(check_img_processed, img) for img in images]
                for future in as_completed(futures):
                    is_skipped, img = future.result()
                    if is_skipped:
                        skipped_count += 1
                    else:
                        pending_images.append(img)

            # 2. 限制处理数量
            if max_process is not None and max_process > 0:
                batch_images = pending_images[:max_process]
            else:
                batch_images = pending_images

            total = len(batch_images)

            with tasks_lock:
                if task_id in tasks:
                    tasks[task_id]["total"] = total
                    tasks[task_id]["skipped"] = skipped_count
                    tasks[task_id]["name"] = "VLM重命名任务"

            if total == 0:
                with tasks_lock:
                    tasks[task_id]["status"] = "completed"
                    tasks[task_id]["progress"] = 100
                # 任务完成，JSONL模式下无需全量落盘

            task_queue = queue.Queue()
            for idx, img_info in enumerate(batch_images):
                task_queue.put((idx, img_info))

            # 3. 确定并发账号
            run_accounts = []
            if account_index == 1:
                if len(ACCOUNTS) >= 1:
                    run_accounts = [ACCOUNTS[0]]
            elif account_index == 2:
                if len(ACCOUNTS) >= 2:
                    run_accounts = [ACCOUNTS[1]]
                elif len(ACCOUNTS) >= 1:
                    run_accounts = [ACCOUNTS[0]]
            else:
                run_accounts = ACCOUNTS

            if not run_accounts:
                run_accounts = ACCOUNTS[:1] if ACCOUNTS else []

            error_flag.clear()
            retry_count.clear()
            retry_lock = threading.Lock()

            def web_worker_thread(account_info):
                while True:
                    if error_flag.is_set():
                        break
                    try:
                        task = task_queue.get(timeout=1)
                    except queue.Empty:
                        continue
                    if task is None:
                        break

                    idx, img_info = task
                    img_path = img_info["path"]

                    with tasks_lock:
                        if "processing_files" not in tasks[task_id]:
                            tasks[task_id]["processing_files"] = []
                        tasks[task_id]["processing_files"].append(str(img_path.name))

                    try:
                        res = process_single_image_api(
                            img_info, account_info, auto_rename=auto_rename, auto_move=auto_move, 
                            run_mode=run_mode, available_folders=available_folders
                        )

                        if res.get("skipped"):
                            with tasks_lock:
                                tasks[task_id]["skipped"] += 1
                                tasks[task_id]["processed"] += 1
                                tasks[task_id]["results"].append(res)
                            task_queue.task_done()
                        elif res.get("success"):
                            with tasks_lock:
                                tasks[task_id]["processed"] += 1
                                if res.get("reclassified"):
                                    tasks[task_id]["reclassified"] += 1
                                if res.get("description"):
                                    tasks[task_id]["renamed"] += 1
                                tasks[task_id]["results"].append(res)
                            task_queue.task_done()
                            time.sleep(0.15)
                        else:
                            # 失败，尝试大步重试
                            with retry_lock:
                                current_retries = retry_count.get(str(img_path), 0)

                            if current_retries < MAX_RETRIES:
                                with retry_lock:
                                    retry_count[str(img_path)] = current_retries + 1
                                task_queue.put((idx, img_info))
                                task_queue.task_done()
                            else:
                                with tasks_lock:
                                    tasks[task_id]["errors"] += 1
                                    tasks[task_id]["results"].append(res)
                                task_queue.task_done()
                    except Exception as e:
                        with tasks_lock:
                            tasks[task_id]["errors"] += 1
                            tasks[task_id]["results"].append({
                                "success": False,
                                "original_path": str(img_path),
                                "original_category": img_info.get("original_category", "其他"),
                                "error": f"线程内异常: {str(e)}"
                            })
                        task_queue.task_done()
                    finally:
                        with tasks_lock:
                            if str(img_path.name) in tasks[task_id]["processing_files"]:
                                tasks[task_id]["processing_files"].remove(str(img_path.name))

                    # 实时更新百分比进度
                    with tasks_lock:
                        processed_so_far = tasks[task_id]["processed"] + tasks[task_id]["errors"]
                        if total > 0:
                            tasks[task_id]["progress"] = min(100, int(processed_so_far / total * 100))

            threads = []
            for acc in run_accounts:
                t = threading.Thread(target=web_worker_thread, args=(acc,))
                t.daemon = True
                t.start()
                threads.append(t)

            task_queue.join()

            for _ in run_accounts:
                task_queue.put(None)
            for t in threads:
                t.join(timeout=5)

            # 4. JSONL模式下无需在此进行全量落盘

            with tasks_lock:
                tasks[task_id]["status"] = "completed"
                tasks[task_id]["progress"] = 100
                # 更新持久化统计
                # 成功数 = 处理数 - 错误数（避免 renamed + reclassified 重复计算同一张图片）
                actual_success = tasks[task_id]["processed"] - tasks[task_id]["errors"]
                update_task_stats(
                    processed=tasks[task_id]["processed"],
                    success=actual_success,
                    errors=tasks[task_id]["errors"],
                    renamed=tasks[task_id]["renamed"],
                    reclassified=tasks[task_id]["reclassified"],
                    skipped=tasks[task_id]["skipped"]
                )

    except Exception as e:
        with tasks_lock:
            if task_id in tasks:
                tasks[task_id]["status"] = "failed"
                tasks[task_id]["error"] = str(e)
            else:
                tasks[task_id] = {
                    "id": task_id,
                    "name": "任务",
                    "status": "failed",
                    "error": str(e),
                    "progress": 0
                }

# ===== 动态静态资源服务 =====
@app.get("/images/{file_path:path}")
async def serve_image(file_path: str):
    """动态安全地提供图片文件服务，支持 base_dir 热加载并防止路径穿越攻击"""
    try:
        base_dir = get_base_dir()
        decoded_path = urllib.parse.unquote(file_path)
        full_path = (base_dir / decoded_path).resolve()
        
        # 安全验证：确保解析出的物理路径在当前图片根目录下
        full_path.relative_to(base_dir.resolve())
        
        if not full_path.exists() or not full_path.is_file():
            raise HTTPException(status_code=404, detail="图片不存在")
            
        return FileResponse(full_path)
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=403, detail="越权访问受限目录")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/thumbnail/{file_path:path}")
async def serve_thumbnail(file_path: str):
    """动态生成并缓存图片缩略图，大幅优化前端加载速度"""
    try:
        base_dir = get_base_dir()
        decoded_path = urllib.parse.unquote(file_path)
        full_path = (base_dir / decoded_path).resolve()
        
        # 安全验证：确保解析出的物理路径在当前图片根目录下
        full_path.relative_to(base_dir.resolve())
        
        if not full_path.exists() or not full_path.is_file():
            raise HTTPException(status_code=404, detail="图片不存在")
            
        # 缓存目录 (移至标准数据目录)
        cache_dir = USER_DATA_DIR / ".cache" / "thumbnails"
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 使用路径和修改时间的 MD5 作为缓存文件名
        file_mtime = str(full_path.stat().st_mtime)
        path_md5 = hashlib.md5((str(full_path) + file_mtime).encode('utf-8')).hexdigest()
        cache_path = cache_dir / f"{path_md5}{full_path.suffix}"
        
        # 检查缓存是否存在
        if cache_path.exists():
            return FileResponse(cache_path)
            
        # 缓存不存在，使用 Pillow 压缩生成
        with Image.open(full_path) as img:
            # 转换为 RGB 模式（处理带 alpha 通道的 png 转 jpeg 等情况）
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            # 缩放为最大 300x300 的缩略图，保持比例
            img.thumbnail((300, 300))
            # 保存到缓存
            img.save(cache_path, quality=80)
            
        return FileResponse(cache_path)
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=403, detail="越权访问受限目录")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ===== 基础接口 =====
import copy

@app.get("/api/health", response_model=BaseResponse)
async def health_check():
    """健康检查接口"""
    return BaseResponse(data={"status": "ok", "version": "1.0.0"})

@app.get("/api/config", response_model=BaseResponse)
async def get_config():
    """获取当前配置"""
    try:
        config = load_config()
        # 隐藏API密钥敏感信息
        safe_config = copy.deepcopy(config)
        for acc in safe_config.get("accounts", []):
            acc["keys"] = ["***" for _ in acc["keys"]]
        return BaseResponse(data=safe_config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取配置失败: {str(e)}")

@app.post("/api/config", response_model=BaseResponse)
async def update_config(config_update: ConfigUpdate = Body(...)):
    """更新配置"""
    try:
        current_config = load_config()
        update_data = config_update.dict(exclude_unset=True)
        
        # 防止前端传回的 *** 覆盖原有真实 key
        if "accounts" in update_data:
            current_accounts = current_config.get("accounts", [])
            for i, acc in enumerate(update_data["accounts"]):
                if "keys" in acc:
                    # 如果传过来全是 ***，说明前端没修改，保留原key
                    if all(k == "***" for k in acc["keys"]):
                        if i < len(current_accounts):
                            acc["keys"] = current_accounts[i].get("keys", [])
                        else:
                            acc["keys"] = []
                    else:
                        # 过滤掉其中的 ***（如果用户修改时部分填了***）
                        acc["keys"] = [k for k in acc["keys"] if k != "***"]

        # 更新配置项
        current_config.update(update_data)

        # 写入配置文件（原子操作，防损坏）
        tmp_file = CONFIG_FILE.with_suffix('.tmp')
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(current_config, f, ensure_ascii=False, indent=2)
        os.replace(tmp_file, CONFIG_FILE)

        return BaseResponse(msg="配置更新成功", data=current_config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新配置失败: {str(e)}")

@app.post("/api/system/open_logs", response_model=BaseResponse)
async def open_logs_dir():
    """打开本地日志目录"""
    import os, platform, subprocess
    try:
        path = str(USER_DATA_DIR)
        if platform.system() == "Windows":
            os.startfile(path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return BaseResponse(msg="日志文件夹已打开")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"无法打开文件夹: {str(e)}")

@app.post("/api/system/shutdown", response_model=BaseResponse)
async def shutdown_system():
    """退出系统（结束后端进程）"""
    import os, threading, time
    def kill_server():
        time.sleep(1)
        os._exit(0)
    threading.Thread(target=kill_server, daemon=True).start()
    return BaseResponse(msg="后端正在关闭...")

@app.post("/api/system/clear_cache", response_model=BaseResponse)
async def clear_system_cache(request: Request):
    """清除当前根目录的处理记录缓存（MD5记录），以便重新处理"""
    from vlm_rename_v5 import TEMP_FILE, MD5_FILE, db_lock, processed_keys, processed_md5s
    
    deleted = 0
    try:
        with db_lock:
            # 清除内存
            processed_keys.clear()
            processed_md5s.clear()
            
            # 删除物理文件 (尝试删除可能存在的各个模式的缓存)
            dir_hash_part = ""
            if MD5_FILE and MD5_FILE.name:
                # 提取哈希部分, eg. processed_md5_12345678.txt -> 12345678
                import re
                m = re.search(r'_([a-f0-9]{8})\.txt$', MD5_FILE.name)
                if m:
                    dir_hash_part = m.group(1)
            
            if dir_hash_part:
                # 删除该目录下的所有模式的去重文件
                import glob
                pattern = str(USER_DATA_DIR / f"*_{dir_hash_part}.txt")
                for fpath in glob.glob(pattern):
                    if "processed_" in fpath:
                        os.remove(fpath)
                        deleted += 1
            else:
                # 兜底：直接删当前的两个变量指向的文件
                if TEMP_FILE and TEMP_FILE.exists():
                    TEMP_FILE.unlink()
                    deleted += 1
                if MD5_FILE and MD5_FILE.exists():
                    MD5_FILE.unlink()
                    deleted += 1
                    
        return BaseResponse(msg=f"成功清除当前目录的缓存记录（已删除 {deleted} 个缓存文件）。您可以重新整理照片了！")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"清除缓存失败: {str(e)}")


@app.get("/api/categories", response_model=BaseResponse)
async def get_categories():
    """获取所有分类列表"""
    import vlm_classify
    categories = []
    for idx, cat in enumerate(vlm_classify.CATEGORIES):
        categories.append({
            "name": cat,
            "priority": 0 if cat in ("横屏", "1比1") else 1,
            "description": ""
        })
    return BaseResponse(data=categories)

@app.get("/api/select_folder", response_model=BaseResponse)
async def select_folder_dialog():
    """打开系统文件夹选择框，返回选择的路径"""
    try:
        import subprocess
        cmd = '''
        Add-Type -AssemblyName System.windows.forms
        $f = New-Object System.Windows.Forms.FolderBrowserDialog
        $f.Description = "请选择图片所在的根目录"
        $f.ShowNewFolderButton = $true
        if ($f.ShowDialog() -eq "OK") {
            Write-Output $f.SelectedPath
        }
        '''
        result = subprocess.run(["powershell", "-NoProfile", "-Command", cmd], capture_output=True, text=True, creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0)
        selected_path = result.stdout.strip()
        if selected_path:
            return BaseResponse(data={"path": selected_path})
        else:
            return BaseResponse(msg="未选择目录", data={"path": ""})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"打开文件夹选择器失败: {str(e)}")

@app.get("/api/categories/config", response_model=BaseResponse)
async def get_categories_config():
    """获取动态分类的配置（categories.json内容）"""
    import vlm_classify
    return BaseResponse(data={
        "categories": vlm_classify.CATEGORIES,
        "legacy_categories": vlm_classify.LEGACY_CATEGORIES,
        "category_keywords": vlm_classify.CATEGORY_KEYWORDS
    })

@app.post("/api/categories/config", response_model=BaseResponse)
async def update_categories_config(update_req: CategoryConfigUpdate = Body(...)):
    """更新动态分类配置并保存到 categories.json"""
    import vlm_classify
    try:
        vlm_classify.CATEGORIES = update_req.categories
        vlm_classify.LEGACY_CATEGORIES = update_req.legacy_categories
        vlm_classify.CATEGORY_KEYWORDS = update_req.category_keywords
        vlm_classify.SCAN_CATEGORIES = list(dict.fromkeys(vlm_classify.CATEGORIES + vlm_classify.LEGACY_CATEGORIES))
        vlm_classify.save_categories()
        return BaseResponse(msg="分类配置更新成功")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存分类失败: {str(e)}")

@app.post("/api/ai_assist/optimize", response_model=BaseResponse)
async def ai_assist_optimize(req: AiAssistRequest = Body(...)):
    """召唤 AI 自动完善分类关键词"""
    import requests
    from vlm_rename_v5 import get_account_info, load_config
    try:
        config = load_config()
        # 找一个可用账号
        account_info = None
        for acc in config.get("accounts", []):
            if "keys" in acc and acc["keys"]:
                account_info = get_account_info(config, 0) # 简写为用第一个账号
                break
        
        if not account_info:
            raise Exception("没有可用的API账号配置")
            
        pro_model = config.get("assistant_model", "doubao-seed-2-0-pro-260215")
        
        prompt = f"""你是一个智能图片整理助手。用户新建了一个图片分类类别叫“{req.category_name}”。
请根据这个类别名称，联想并生成用于匹配该类别图片的关键词(keywords)和文件名常见特征(filename_hints)。
返回JSON格式：
{{
  "keywords": ["关键词1", "关键词2", ...],
  "filename_hints": ["特征1", "特征2", ...]
}}
注意：只要JSON，不要其他文字。"""

        headers = {
            "Authorization": f"Bearer {account_info['keys'][0]}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": pro_model,
            "messages": [
                {"role": "system", "content": "你是一个有用的助手。"},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.5
        }
        
        endpoint = account_info.get("endpoint", config.get("api_endpoint", "https://ark.cn-beijing.volces.com/api/v3/chat/completions"))
        response = requests.post(endpoint, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        resp_json = response.json()
        
        content = resp_json["choices"][0]["message"]["content"].strip()
        import re
        # 尝试提取被 markdown 包裹的代码块
        match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
        if match:
            content = match.group(1).strip()
        else:
            # 尝试直接寻找大括号包裹的 JSON
            match = re.search(r"(\{.*\})", content, re.DOTALL)
            if match:
                content = match.group(1).strip()
                
        result = json.loads(content)
        
        return BaseResponse(data=result, msg="AI 优化成功")
    except Exception as e:
        err_msg = str(e)
        if hasattr(e, 'response') and getattr(e, 'response') is not None:
            err_msg += f" Response: {e.response.text}"
        import traceback
        with open(str(USER_DATA_DIR / "ai_error.log"), "a", encoding="utf-8") as f:
            f.write(f"========= AI ASSIST OPTIMIZE ERROR =========\n{traceback.format_exc()}\nResponse Data: {err_msg}\n============================================\n")
        print(f"========= AI ASSIST OPTIMIZE ERROR =========\n{err_msg}\n============================================")
        raise HTTPException(status_code=500, detail=f"AI 生成失败: {err_msg}")

# ===== 图片处理接口 =====
@app.post("/api/image/analyze", response_model=BaseResponse)
async def analyze_single_image(request: ImageAnalyzeRequest = Body(...)):
    """单张图片分析（仅分析，不修改文件）"""
    try:
        config = load_config()
        account_info = get_account_info(config, request.account_index)
        if not account_info:
            raise HTTPException(status_code=400, detail="无效的账号索引")

        img_path = Path(request.image_path)
        if not img_path.exists():
            raise HTTPException(status_code=404, detail="图片不存在")

        description, category = analyze_image(img_path, account_info)
        if not description:
            raise HTTPException(status_code=500, detail="图片分析失败")

        # 比例分类优先级最高
        ratio_cat = check_ratio_category(img_path)
        if ratio_cat:
            category = ratio_cat

        return BaseResponse(data={
            "description": description,
            "category": category,
            "image_path": str(img_path)
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")

@app.post("/api/image/process", response_model=BaseResponse)
async def process_single_image(
    image_path: str = Body(...),
    account_index: int = Body(0),
    auto_rename: bool = Body(True),
    auto_move: bool = Body(True)
):
    """处理单张图片（重命名+分类）"""
    try:
        config = load_config()
        account_info = get_account_info(config, account_index)
        if not account_info:
            raise HTTPException(status_code=400, detail="无效的账号索引")

        img_path = Path(image_path)
        if not img_path.exists():
            raise HTTPException(status_code=404, detail="图片不存在")

        result = process_single_image_api(
            {"path": img_path, "original_category": img_path.parent.name},
            account_info,
            auto_rename=auto_rename,
            auto_move=auto_move
        )

        return BaseResponse(data=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")

# ===== 交互式整理与文件操作接口 =====
# 待处理图片缓存
_pending_images_cache = None
_cache_timestamp = 0
CACHE_TTL = 30  # 缓存30秒

@app.get("/api/images/pending", response_model=BaseResponse)
async def get_pending_images(limit: int = 50, use_cache: bool = True):
    """获取待处理的图片列表（未整理的图片）- 优化版，带缓存"""
    try:
        global _pending_images_cache, _cache_timestamp
        
        from vlm_rename_v5 import load_global_config, reload_dedup_records, is_processed
        load_global_config()
        
        # 检查缓存是否有效
        current_time = time.time()
        if use_cache and _pending_images_cache is not None and (current_time - _cache_timestamp) < CACHE_TTL:
            # 使用缓存，只返回限制数量
            return BaseResponse(data=_pending_images_cache[:limit])
        
        # 重新加载去重记录
        reload_dedup_records()
        
        base_dir = get_base_dir()
        images = collect_images(str(base_dir))
        
        # 核心优化：按文件最后修改时间倒序排列。
        # 因为未处理的图片通常是刚拷贝进来的新文件，这样排列能让程序优先检查新文件。
        # 配合 limit 限制，只要找到足够数量的未处理图片就会立刻跳出循环，避免对几千张已处理老图片进行缓慢的 MD5 计算。
        try:
            images.sort(key=lambda x: x["path"].stat().st_mtime, reverse=True)
        except Exception:
            pass
        
        pending_list = []
        for img in images:
            img_path = img["path"]
            original_cat = img["original_category"]
            
            # 判断是否已处理过
            if not is_processed(img_path, original_cat):
                # 构造相对路径供前端渲染预览
                try:
                    rel_path = img_path.relative_to(base_dir)
                    rel_path_str = rel_path.as_posix()
                except ValueError:
                    rel_path_str = img_path.name
                
                pending_list.append({
                    "name": img_path.name,
                    "path": str(img_path),
                    "relative_path": rel_path_str,
                    "original_category": original_cat
                })
                if len(pending_list) >= limit:
                    break
        
        # 更新缓存
        _pending_images_cache = pending_list.copy()
        _cache_timestamp = current_time
        
        return BaseResponse(data=pending_list)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取待处理图片失败: {str(e)}")

@app.get("/api/categories/{category_name}/files", response_model=BaseResponse)
async def get_category_files(category_name: str):
    """获取特定分类目录下的图片列表"""
    try:
        base_dir = get_base_dir()
        cat_dir = base_dir / category_name
        
        if not cat_dir.exists():
            return BaseResponse(data=[])
            
        from vlm_rename_v5 import IMAGE_EXTS
        
        files_list = []
        for f in cat_dir.iterdir():
            if f.is_file() and f.suffix.lower() in IMAGE_EXTS:
                stat = f.stat()
                try:
                    rel_path = f.relative_to(base_dir)
                    rel_path_str = rel_path.as_posix()
                except ValueError:
                    rel_path_str = f"{category_name}/{f.name}"
                
                files_list.append({
                    "name": f.name,
                    "path": str(f),
                    "relative_path": rel_path_str,
                    "size": round(stat.st_size / 1024, 2),  # KB
                    "mtime": stat.st_mtime
                })
        
        # 按修改时间倒序排列
        files_list.sort(key=lambda x: x["mtime"], reverse=True)
        return BaseResponse(data=files_list)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取分类文件失败: {str(e)}")

@app.post("/api/image/rename", response_model=BaseResponse)
async def rename_image(request: ImageRenameRequest = Body(...)):
    """手动重命名图片，支持安全校验与同名防冲突"""
    try:
        base_dir = get_base_dir()
        img_path = Path(request.image_path).resolve()
        
        # 安全性验证：必须在 base_dir 范围内，防止目录穿越
        img_path.relative_to(base_dir.resolve())
        
        if not img_path.exists() or not img_path.is_file():
            raise HTTPException(status_code=404, detail="源图片文件不存在")
            
        # 清理新文件名中的非法字符
        new_name = request.new_name.strip()
        new_name = re.sub(r'[\\/:*?"<>|]', '', new_name)
        if not new_name:
            raise HTTPException(status_code=400, detail="无效的新文件名")
            
        suffix = img_path.suffix
        # 确保不重复拼接后缀
        if new_name.lower().endswith(suffix.lower()):
            new_name = new_name[:-len(suffix)]
            
        parent = img_path.parent
        target_path = parent / f"{new_name}{suffix}"
        
        # 名字防冲突递增
        counter = 1
        while target_path.exists() and target_path.resolve() != img_path:
            target_path = parent / f"{new_name}_{counter}{suffix}"
            counter += 1
            
        # 如果新旧路径一致，不进行操作
        if target_path.resolve() != img_path:
            shutil.move(str(img_path), str(target_path))
            
        # 返回新文件的 relative_path 供前端即时渲染
        try:
            rel_path = target_path.relative_to(base_dir)
            rel_path_str = rel_path.as_posix()
        except ValueError:
            rel_path_str = target_path.name
            
        return BaseResponse(
            msg="重命名成功",
            data={
                "old_path": str(img_path),
                "new_path": str(target_path),
                "new_name": target_path.name,
                "relative_path": rel_path_str
            }
        )
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=403, detail="越权访问受限目录")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重命名失败: {str(e)}")

@app.post("/api/image/move", response_model=BaseResponse)
async def move_image(request: ImageMoveRequest = Body(...)):
    """手动移动图片到新的分类目录下，支持同名递增防覆盖"""
    try:
        from vlm_rename_v5 import load_global_config
        load_global_config()
        
        base_dir = get_base_dir()
        img_path = Path(request.image_path).resolve()
        
        # 安全性验证：源文件必须在 base_dir 范围内
        img_path.relative_to(base_dir.resolve())
        
        if not img_path.exists() or not img_path.is_file():
            raise HTTPException(status_code=404, detail="源图片文件不存在")
            
        target_category = request.target_category.strip()
        if target_category not in ALL_CATEGORIES:
            raise HTTPException(status_code=400, detail="目标分类不存在")
            
        target_dir = base_dir / target_category
        target_dir.mkdir(parents=True, exist_ok=True)
        
        filename = img_path.name
        base_name = img_path.stem
        suffix = img_path.suffix
        
        target_path = target_dir / filename
        
        # 防冲突递增
        counter = 1
        while target_path.exists() and target_path.resolve() != img_path:
            target_path = target_dir / f"{base_name}_{counter}{suffix}"
            counter += 1
            
        # 执行移动
        if target_path.resolve() != img_path:
            shutil.move(str(img_path), str(target_path))
            
            # 手动整理后，往去重文件中记录，确保 VLM 和规则分类不会再次拾取
            from vlm_rename_v5 import record_processed, file_md5
            try:
                md5 = file_md5(str(target_path))
                record_processed(f"{target_category}/{target_path.name}", md5)
            except Exception as log_err:
                print(f"写入手动移动日志失败: {log_err}")
                
        try:
            rel_path = target_path.relative_to(base_dir)
            rel_path_str = rel_path.as_posix()
        except ValueError:
            rel_path_str = f"{target_category}/{target_path.name}"
            
        return BaseResponse(
            msg="移动成功",
            data={
                "old_path": str(img_path),
                "new_path": str(target_path),
                "new_name": target_path.name,
                "relative_path": rel_path_str,
                "category": target_category
            }
        )
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=403, detail="越权访问受限目录")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"移动失败: {str(e)}")

@app.delete("/api/image", response_model=BaseResponse)
async def delete_image(request: ImageDeleteRequest = Body(...)):
    """手动删除图片文件，严格限制在 base_dir 范围内"""
    try:
        base_dir = get_base_dir()
        img_path = Path(request.image_path).resolve()
        
        # 安全验证：文件必须在 base_dir 范围内，绝对防止目录穿越
        img_path.relative_to(base_dir.resolve())
        
        if not img_path.exists() or not img_path.is_file():
            raise HTTPException(status_code=404, detail="图片文件不存在")
            
        os.remove(img_path)
        return BaseResponse(msg="图片删除成功", data={"deleted_path": str(img_path)})
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=403, detail="越权删除受限目录")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除图片失败: {str(e)}")

# ===== 批量任务接口 =====
@app.post("/api/batch/start", response_model=BaseResponse)
async def start_batch_process(request: BatchStartRequest = Body(...)):
    """启动批量处理任务"""
    try:
        # 检查是否已有运行中的批量任务
        with tasks_lock:
            for t in tasks.values():
                if t.get("status") == "processing":
                    raise HTTPException(status_code=400, detail="已有批量任务正在运行中，请等待其完成")

        task_id = str(uuid.uuid4())[:8]

        # 同步初始化任务，防止前端轮询时任务不存在返回假数据
        with tasks_lock:
            tasks[task_id] = {
                "id": task_id,
                "name": "VLM重命名任务",
                "status": "processing",
                "progress": 0,
                "create_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "total": 0,
                "processed": 0,
                "renamed": 0,
                "reclassified": 0,
                "errors": 0,
                "skipped": 0,
                "results": [],
                "processing_files": []
            }

        # 启动后台线程处理任务
        thread = threading.Thread(
            target=process_batch_task,
            args=(task_id, request.base_dir, request.account_index,
                  request.max_process, request.auto_rename, request.auto_move,
                  request.task_type if hasattr(request, 'task_type') else "rename", request.run_mode)
        )
        thread.daemon = True
        thread.start()

        return BaseResponse(data={"task_id": task_id}, msg="批量任务已启动")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"启动任务失败: {str(e)}")

@app.post("/api/batch/classify", response_model=BaseResponse)
async def start_classify_task(
    base_dir: Optional[str] = Body(None),
    max_process: Optional[int] = Body(None),
    auto_move: bool = Body(True)
):
    """启动规则分类任务（对应vlm_classify.py）"""
    try:
        # 检查是否已有运行中的批量任务
        with tasks_lock:
            for t in tasks.values():
                if t.get("status") == "processing":
                    raise HTTPException(status_code=400, detail="已有批量任务正在运行中，请等待其完成")

        task_id = str(uuid.uuid4())[:8]

        # 同步初始化任务
        with tasks_lock:
            tasks[task_id] = {
                "id": task_id,
                "name": "规则分类任务",
                "status": "processing",
                "progress": 0,
                "create_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "total": 0,
                "processed": 0,
                "renamed": 0,
                "reclassified": 0,
                "errors": 0,
                "skipped": 0,
                "results": [],
                "processing_files": []
            }

        thread = threading.Thread(
            target=process_batch_task,
            args=(task_id, base_dir, 0, max_process, False, auto_move, "classify")
        )
        thread.daemon = True
        thread.start()

        return BaseResponse(data={"task_id": task_id}, msg="规则分类任务已启动")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"启动任务失败: {str(e)}")

@app.get("/api/batch/progress/{task_id}", response_model=BaseResponse)
async def get_batch_progress(task_id: str):
    """查询批量任务进度"""
    try:
        with tasks_lock:
            if task_id not in tasks:
                # 返回模拟任务
                return BaseResponse(data={
                    "id": task_id,
                    "name": "示例任务",
                    "status": "completed",
                    "progress": 100,
                    "create_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "total": 100,
                    "processed": 100,
                    "renamed": 80,
                    "reclassified": 50,
                    "errors": 0,
                    "skipped": 0
                })
            return BaseResponse(data=tasks[task_id])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取进度失败: {str(e)}")

@app.get("/api/batch/tasks", response_model=BaseResponse)
async def get_all_tasks():
    """获取所有任务列表"""
    try:
        with tasks_lock:
            task_list = list(tasks.values())
        return BaseResponse(data=task_list)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取任务列表失败: {str(e)}")

# ===== 日志接口 =====
@app.get("/api/logs", response_model=BaseResponse)
async def get_logs(limit: int = 100, offset: int = 0):
    """获取处理日志"""
    try:
        log_file = get_log_file()
        if not log_file.exists():
            return BaseResponse(data=[])

        logs = load_logs(log_file)

        # 按时间倒序
        logs = sorted(logs, key=lambda x: x.get("timestamp", ""), reverse=True)
        total = len(logs)
        logs = logs[offset:offset+limit]

        return BaseResponse(data={
            "total": total,
            "logs": logs
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取日志失败: {str(e)}")

@app.get("/api/stats", response_model=BaseResponse)
async def get_stats():
    """获取统计信息"""
    try:
        config = load_config()
        base_dir = Path(config["base_dir"])

        # 统计各分类文件数量
        category_stats = {}
        total_files = 0
        processed_md5s = set()  # MD5 去重集合

        # 从 MD5 去重记录文件读取已处理记录
        md5_file = USER_DATA_DIR / "processed_md5.txt"
        if md5_file.exists():
            with open(md5_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        parts = line.split("|", 1)
                        if len(parts) >= 1 and parts[0]:
                            processed_md5s.add(parts[0])

        # 统计当前文件
        from vlm_rename_v5 import collect_images
        images = collect_images(str(base_dir), run_mode=1)
        
        for img in images:
            total_files += 1
            cat = img["original_category"]
            category_stats[cat] = category_stats.get(cat, 0) + 1

        # 使用 MD5 去重后的已处理数量
        total_processed = len(processed_md5s)

        # 加载持久化的任务统计
        persisted_stats = load_task_stats()

        # 使用持久化统计
        total_task_processed = persisted_stats["total_processed"]
        total_task_success = persisted_stats["total_success"]
        total_task_errors = persisted_stats["total_errors"]

        # 计算成功率：成功数 / 总处理数 × 100%
        # total_success 是成功处理的图片数，total_errors 是失败的图片数
        # 成功率 = 成功数 / (成功数 + 失败数) × 100%
        if total_task_processed > 0:
            success_rate = round(total_task_success / total_task_processed * 100, 1)
        else:
            success_rate = 0

        return BaseResponse(data={
            "total_files": total_files,
            "total_processed": total_processed,
            "category_stats": category_stats,
            "success_rate": success_rate,
            "task_stats": {
                "total_processed": total_task_processed,
                "success": total_task_success,
                "errors": total_task_errors
            }
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取统计失败: {str(e)}")

# ===== 系统更新接口 =====
import subprocess

def parse_version(v_str):
    """简单解析版本号，便于比较"""
    return [int(x) if x.isdigit() else x for x in v_str.lstrip('v').split('.')]

@app.get("/api/system/check_update", response_model=BaseResponse)
async def check_update():
    """检查应用更新"""
    try:
        from vlm_rename_v5 import VERSION
        current_version = VERSION
        
        # 检查是否在 git 源码环境下
        app_dir = Path(__file__).parent
        git_dir = app_dir / ".git"
        can_auto_update = git_dir.exists() and git_dir.is_dir()

        import requests
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "VLM-Renamer-App"
        }
        api_url = "https://api.github.com/repos/qingxuandaoming/Picture/releases/latest"
        
        try:
            resp = requests.get(api_url, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            latest_version = data.get("tag_name", "").lstrip("v")
            release_notes = data.get("body", "")
            release_url = data.get("html_url", "")
            
            has_update = False
            try:
                if parse_version(latest_version) > parse_version(current_version):
                    has_update = True
            except:
                if latest_version != current_version:
                    has_update = True
                    
        except Exception as api_err:
            print(f"检查更新失败: {api_err}")
            return BaseResponse(data={
                "current_version": current_version,
                "latest_version": "未知",
                "has_update": False,
                "can_auto_update": can_auto_update,
                "release_url": "https://github.com/qingxuandaoming/Picture/releases",
                "release_notes": f"无法连接 GitHub API: {str(api_err)}"
            })

        return BaseResponse(data={
            "current_version": current_version,
            "latest_version": latest_version,
            "has_update": has_update,
            "can_auto_update": can_auto_update,
            "release_url": release_url,
            "release_notes": release_notes
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"检查更新异常: {str(e)}")

@app.post("/api/system/pull_update", response_model=BaseResponse)
async def pull_update():
    """拉取最新版本并覆盖"""
    try:
        app_dir = Path(__file__).parent
        git_dir = app_dir / ".git"
        if not git_dir.exists():
            raise HTTPException(status_code=400, detail="未检测到 Git 源码目录，无法执行自动拉取更新。请前往发布页下载最新版本。")
            
        try:
            # 1. Fetch all
            subprocess.run(["git", "fetch", "--all"], cwd=str(app_dir), check=True, capture_output=True, text=True)
            # 2. Reset hard to origin/master
            subprocess.run(["git", "reset", "--hard", "origin/master"], cwd=str(app_dir), check=True, capture_output=True, text=True)
            
            return BaseResponse(msg="更新成功，请关闭终端窗口并重新运行启动脚本生效。")
        except subprocess.CalledProcessError as sub_err:
            error_msg = sub_err.stderr if sub_err.stderr else "未知错误"
            raise HTTPException(status_code=500, detail=f"Git 操作失败: {error_msg}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"拉取更新异常: {str(e)}")


@app.get("/api/system/check_init", response_model=BaseResponse)
async def check_init():
    """检查系统是否已经初始化（是否存在配置，并且已设置照片根目录）"""
    try:
        from vlm_rename_v5 import CONFIG_FILE, load_config
        if not CONFIG_FILE.exists():
            return BaseResponse(data={"initialized": False, "reason": "no_config"})
            
        config = load_config()
        base_dir = config.get("base_dir")
        accounts = config.get("accounts", [])
        
        if not accounts or not accounts[0].get("keys"):
            return BaseResponse(data={"initialized": False, "reason": "no_keys"})
            
        if not base_dir:
            return BaseResponse(data={"initialized": False, "reason": "no_base_dir"})
            
        # 即使目录不存在，也算作初始化过，只是后端会报错，前端也可以处理
        return BaseResponse(data={"initialized": True})
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"检查初始化状态异常: {str(e)}")


def get_frontend_dist() -> Path:
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS) / "frontend_dist"
    else:
        return Path(__file__).parent / "frontend" / "dist"

frontend_dist = get_frontend_dist()
if frontend_dist.exists():
    # 静态资源挂载
    assets_dir = frontend_dist / "assets"
    if assets_dir.exists():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")
        
    @app.get("/{catchall:path}")
    def serve_spa(catchall: str):
        file_path = frontend_dist / catchall
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(frontend_dist / "index.html")

if __name__ == "__main__":
    import sys
    import os
    
    if getattr(sys, 'frozen', False):
        # 打包模式下，将控制台输出重定向到日志文件
        log_path = USER_DATA_DIR / "backend_console.log"
        sys.stdout = open(log_path, "a", encoding="utf-8")
        sys.stderr = sys.stdout
    else:
        if sys.stdout is None:
            sys.stdout = open(os.devnull, "w")
        if sys.stderr is None:
            sys.stderr = open(os.devnull, "w")

    from vlm_rename_v5 import load_global_config
    
    try:
        load_global_config()
    except:
        pass

    # 3. 自动打开浏览器
    def open_browser(target_port):
        time.sleep(2)
        try:
            import webbrowser
            webbrowser.open(f"http://localhost:{target_port}")
        except Exception as e:
            print(f"打开浏览器失败: {e}")

    # 尝试绑定可用端口，防止 8000 被占用
    import socket
    def get_available_port(start_port, max_ports=5):
        for p in range(start_port, start_port + max_ports):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("0.0.0.0", p))
                    return p
                except OSError:
                    continue
        return start_port
        
    actual_port = get_available_port(8000, max_ports=5)
    
    # 只有当作为独立可执行文件（打包后）运行时，才由后端启动浏览器
    # 否则（源码运行）由 start.bat 启动浏览器，防止弹出两个标签页
    if getattr(sys, 'frozen', False):
        threading.Thread(target=open_browser, args=(actual_port,), daemon=True).start()

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=actual_port)
