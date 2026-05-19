from fastapi import FastAPI, HTTPException, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import json
import os
import threading
import time
import uuid
from typing import List, Dict, Optional

from schemas import (
    BaseResponse, ConfigUpdate, ImageAnalyzeRequest, ImageAnalyzeResponse,
    BatchStartRequest, BatchProgressResponse, CategoryInfo
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

CONFIG_FILE = Path(__file__).parent / "config.json"
config = load_config()
BASE_DIR = Path(config["base_dir"])
LOG_FILE = BASE_DIR / "rename_log.json"

# 静态文件服务
if BASE_DIR.exists():
    app.mount("/images", StaticFiles(directory=str(BASE_DIR)), name="images")

# 任务存储
tasks = {}
tasks_lock = threading.Lock()

# ===== 任务处理函数 =====
def process_batch_task(task_id: str, base_dir: str, account_index: int, max_process: Optional[int],
                       auto_rename: bool, auto_move: bool, task_type: str = "rename"):
    """后台批量处理任务"""
    try:
        config = load_config()
        account_info = get_account_info(config, account_index)

        if base_dir:
            task_base_dir = Path(base_dir)
        else:
            task_base_dir = Path(config["base_dir"])

        # 收集图片
        images = collect_images(str(task_base_dir)) if max_process is None else collect_images(str(task_base_dir))[:max_process]

        total = len(images)

        with tasks_lock:
            tasks[task_id] = {
                "id": task_id,
                "name": "规则分类任务" if task_type == "classify" else "VLM重命名任务",
                "status": "processing",
                "progress": 0,
                "create_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                "total": total,
                "processed": 0,
                "renamed": 0,
                "reclassified": 0,
                "errors": 0,
                "skipped": 0,
                "results": []
            }

        for idx, img_info in enumerate(images):
            img_path = img_info["path"]
            original_cat = img_info["original_category"]

            try:
                if task_type == "classify":
                    # 规则分类
                    ratio_cat = check_ratio_category(img_path)
                    if ratio_cat:
                        new_cat = ratio_cat
                    else:
                        # 使用默认描述进行分类
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
                            "path": str(img_path),
                            "category": new_cat
                        })
                else:
                    # VLM重命名
                    result = process_single_image_api(
                        img_info, account_info, auto_rename=auto_rename, auto_move=auto_move
                    )

                    with tasks_lock:
                        if result.get("skipped"):
                            tasks[task_id]["skipped"] += 1
                        elif not result.get("success"):
                            tasks[task_id]["errors"] += 1
                        else:
                            tasks[task_id]["processed"] += 1
                            if result.get("reclassified"):
                                tasks[task_id]["reclassified"] += 1
                            if result.get("description"):
                                tasks[task_id]["renamed"] += 1
                        tasks[task_id]["results"].append(result)

            except Exception as e:
                with tasks_lock:
                    tasks[task_id]["errors"] += 1
                    tasks[task_id]["results"].append({
                        "path": str(img_path),
                        "error": str(e)
                    })

            # 更新进度
            with tasks_lock:
                tasks[task_id]["progress"] = min(100, int((idx + 1) / total * 100))

        # 任务完成
        with tasks_lock:
            tasks[task_id]["status"] = "completed"
            tasks[task_id]["progress"] = 100

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

# ===== 基础接口 =====
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
        safe_config = config.copy()
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
        # 更新配置项
        update_data = config_update.dict(exclude_unset=True)
        current_config.update(update_data)

        # 写入配置文件
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(current_config, f, ensure_ascii=False, indent=2)

        return BaseResponse(msg="配置更新成功", data=current_config)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新配置失败: {str(e)}")

@app.get("/api/categories", response_model=BaseResponse)
async def get_categories():
    """获取所有分类列表"""
    categories = []
    for idx, cat in enumerate(ALL_CATEGORIES):
        categories.append({
            "name": cat,
            "priority": 0 if cat in ("横屏", "1比1") else 1,
            "description": ""
        })
    return BaseResponse(data=categories)

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

# ===== 批量任务接口 =====
@app.post("/api/batch/start", response_model=BaseResponse)
async def start_batch_process(request: BatchStartRequest = Body(...)):
    """启动批量处理任务"""
    try:
        task_id = str(uuid.uuid4())[:8]

        # 启动后台线程处理任务
        thread = threading.Thread(
            target=process_batch_task,
            args=(task_id, request.base_dir, request.account_index,
                  request.max_process, request.auto_rename, request.auto_move,
                  request.task_type if hasattr(request, 'task_type') else "rename")
        )
        thread.daemon = True
        thread.start()

        return BaseResponse(data={"task_id": task_id}, msg="批量任务已启动")
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
        task_id = str(uuid.uuid4())[:8]

        thread = threading.Thread(
            target=process_batch_task,
            args=(task_id, base_dir, 0, max_process, False, auto_move, "classify")
        )
        thread.daemon = True
        thread.start()

        return BaseResponse(data={"task_id": task_id}, msg="规则分类任务已启动")
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
        if not LOG_FILE.exists():
            return BaseResponse(data=[])

        with open(LOG_FILE, "r", encoding="utf-8") as f:
            logs = json.load(f)

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
        processed_paths = set()

        # 先统计已处理文件
        if LOG_FILE.exists():
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                logs = json.load(f)
                for log in logs:
                    if "original_path" in log:
                        processed_paths.add(log["original_path"])

        # 统计当前文件
        for cat in ALL_CATEGORIES:
            cat_dir = base_dir / cat
            if cat_dir.exists():
                count = 0
                for f in cat_dir.iterdir():
                    if f.is_file() and f.suffix.lower() in ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'):
                        count += 1
                        total_files += 1
                category_stats[cat] = count

        # 统计日志数量（已去重）
        total_processed = len(processed_paths)

        return BaseResponse(data={
            "total_files": total_files,
            "total_processed": total_processed,
            "category_stats": category_stats
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取统计失败: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
