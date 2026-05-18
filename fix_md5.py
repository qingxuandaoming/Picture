import json
import hashlib
from pathlib import Path

BASE_DIR = Path(r"e:\Picture")
LOG_FILE = BASE_DIR / "rename_log.json"
MD5_FILE = BASE_DIR / "processed_md5.txt"

CATEGORIES = [
    "AI生成图片", "B站图片", "人像", "其他",
    "截图", "插画艺术", "海报设计", "照片", "通讯图片", "风景",
    "厚涂", "横屏", "1比1",
]

def file_md5(filepath):
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    print("开始从 rename_log.json 恢复 MD5 记录...")
    
    # 1. 收集磁盘上所有的图片文件
    disk_files = {}
    for cat in CATEGORIES:
        cat_dir = BASE_DIR / cat
        if not cat_dir.exists():
            continue
        for f in cat_dir.iterdir():
            if f.is_file():
                disk_files[f.name] = f

    # 2. 加载已经存在的 MD5
    existing_md5s = set()
    if MD5_FILE.exists():
        with open(MD5_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    parts = line.split("|", 1)
                    if len(parts) == 2:
                        existing_md5s.add(parts[0])
                        
    print(f"当前 processed_md5.txt 中有 {len(existing_md5s)} 条记录。")

    # 3. 读取日志
    if not LOG_FILE.exists():
        print("未找到 rename_log.json")
        return
        
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        log_data = json.load(f)
        
    added_count = 0
    with open(MD5_FILE, "a", encoding="utf-8") as out_f:
        for entry in log_data:
            # 拿到重命名后的文件名
            new_path_str = entry.get("new_path")
            if not new_path_str:
                continue
            
            filename = Path(new_path_str).name
            
            # 尝试在磁盘上找（即使被分类脚本移动了，文件名是不变的）
            if filename in disk_files:
                real_path = disk_files[filename]
                try:
                    md5_val = file_md5(real_path)
                    if md5_val not in existing_md5s:
                        orig_cat = entry.get("original_category", "Unknown")
                        orig_name = Path(entry.get("original_path", "unknown")).name
                        out_f.write(f"{md5_val}|{orig_cat}/{orig_name}\n")
                        existing_md5s.add(md5_val)
                        added_count += 1
                except Exception as e:
                    pass
                    
    print(f"修复完成！成功找回并补充了 {added_count} 条 MD5 记录！")

if __name__ == "__main__":
    main()
