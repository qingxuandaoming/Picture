import requests
import urllib.parse
from pathlib import Path
import os
import shutil

def recover():
    task_id = "67dbadf6"  # 这是你截图里的任务ID
    print(f"尝试从运行中的后端获取任务 {task_id} 的结果...")
    
    try:
        resp = requests.get(f"http://127.0.0.1:8000/api/batch/progress/{task_id}")
        resp.raise_for_status()
        data = resp.json()["data"]
    except Exception as e:
        print("无法连接到后端，或者任务已被清除。请确保后端仍在运行:", e)
        return

    results = data.get("results", [])
    if not results:
        print("没有找到任何处理结果。")
        return

    recover_count = 0
    fail_count = 0

    print(f"找到 {len(results)} 条记录，开始恢复被错误重命名的文件...")
    
    for res in results:
        if res.get("success") and res.get("new_filename", "").startswith("!CLIENT_ERROR"):
            original_path_str = res.get("original_path")
            new_path_str = res.get("new_path")
            
            if not original_path_str or not new_path_str:
                continue
                
            orig_path = Path(original_path_str)
            new_path = Path(new_path_str)
            
            if new_path.exists():
                try:
                    # 将文件从错误的目标路径移动回原始路径
                    orig_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(new_path), str(orig_path))
                    print(f"已恢复: {new_path.name} -> {orig_path.name}")
                    recover_count += 1
                except Exception as e:
                    print(f"恢复失败: {new_path.name} -> {orig_path.name}，原因: {e}")
                    fail_count += 1
            else:
                print(f"找不到被错改的文件 (可能已被你手动删掉或移动): {new_path}")
                fail_count += 1

    print(f"\n恢复完成！成功恢复 {recover_count} 个文件，失败 {fail_count} 个。")

if __name__ == "__main__":
    recover()
