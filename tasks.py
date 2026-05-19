from celery import Celery
import redis
import json
import os
from pathlib import Path
from typing import Dict, List

# 初始化Celery
celery = Celery(
    'image_tasks',
    broker='redis://localhost:6379/0',
    backend='redis://localhost:6379/0'
)

# 初始化Redis客户端
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

# 导入现有工具函数
from vlm_rename_v5 import process_single_image, load_config, get_account_info
from vlm_classify import suggest_category, check_ratio_category

@celery.task(bind=True)
def batch_process_task(self, base_dir: str = None, account_index: int = 0, max_process: int = None, auto_rename: bool = True, auto_move: bool = True):
    """批量处理图片任务"""
    task_id = self.request.id

    # 加载配置
    config = load_config()
    if base_dir is None:
        base_dir = config['base_dir']

    # 获取账号信息
    account_info = get_account_info(config, account_index)

    # 收集待处理图片
    from vlm_rename_v5 import collect_images
    images = collect_images(base_dir)

    if max_process and len(images) > max_process:
        images = images[:max_process]

    total = len(images)
    stats = {
        'total': total,
        'processed': 0,
        'renamed': 0,
        'reclassified': 0,
        'errors': 0,
        'skipped': 0,
        'results': []
    }

    # 初始化进度
    r.set(f"task:{task_id}:stats", json.dumps(stats))
    r.set(f"task:{task_id}:status", "processing")

    for idx, img_info in enumerate(images):
        try:
            # 处理单张图片
            result = process_single_image(img_info, account_info, idx, total, auto_rename=auto_rename, auto_move=auto_move)

            if result is None:
                stats['skipped'] += 1
            elif result is False:
                stats['errors'] += 1
            else:
                stats['processed'] += 1
                if result.get('renamed'):
                    stats['renamed'] += 1
                if result.get('reclassified'):
                    stats['reclassified'] += 1
                stats['results'].append(result)

        except Exception as e:
            stats['errors'] += 1
            stats['results'].append({
                'path': str(img_info['path']),
                'error': str(e)
            })

        # 更新进度
        stats['progress'] = (stats['processed'] + stats['errors'] + stats['skipped']) / total * 100
        r.set(f"task:{task_id}:stats", json.dumps(stats))

        # 更新任务状态
        self.update_state(state='PROGRESS', meta=stats)

    # 任务完成
    r.set(f"task:{task_id}:status", "completed")
    return stats

def get_task_progress(task_id: str) -> Dict:
    """获取任务进度"""
    status = r.get(f"task:{task_id}:status") or "pending"
    stats_str = r.get(f"task:{task_id}:stats")

    if stats_str:
        stats = json.loads(stats_str)
    else:
        stats = {
            'total': 0,
            'processed': 0,
            'renamed': 0,
            'reclassified': 0,
            'errors': 0,
            'skipped': 0,
            'progress': 0
        }

    return {
        'task_id': task_id,
        'status': status,
        **stats
    }
