from pydantic import BaseModel
from typing import List, Dict, Optional, Any

# 通用响应格式
class BaseResponse(BaseModel):
    code: int = 200
    msg: str = "success"
    data: Optional[Any] = None

# 配置信息
class ConfigUpdate(BaseModel):
    accounts: Optional[List[Dict]] = None
    api_endpoint: Optional[str] = None
    default_model: Optional[str] = None
    assistant_model: Optional[str] = None
    vlm_prompt_template: Optional[str] = None
    base_dir: Optional[str] = None
    batch_size: Optional[int] = None
    max_retries: Optional[int] = None
    exclude_extensions: Optional[List[str]] = None

# 分类配置更新
class CategoryConfigUpdate(BaseModel):
    categories: List[str]
    legacy_categories: List[str]
    category_keywords: Dict[str, Any]

# AI 辅助生成请求
class AiAssistRequest(BaseModel):
    category_name: str

# 单图分析请求
class ImageAnalyzeRequest(BaseModel):
    image_path: str
    account_index: Optional[int] = 0

# 单图分析响应
class ImageAnalyzeResponse(BaseModel):
    success: bool
    description: Optional[str] = None
    category: Optional[str] = None
    new_filename: Optional[str] = None
    error: Optional[str] = None

# 批量任务启动请求
class BatchStartRequest(BaseModel):
    base_dir: Optional[str] = None
    account_index: Optional[int] = 0
    max_process: Optional[int] = None
    auto_rename: bool = True
    auto_move: bool = True
    run_mode: int = 1

# 批量任务进度响应
class BatchProgressResponse(BaseModel):
    task_id: str
    status: str  # pending, processing, completed, failed
    total: int
    processed: int
    renamed: int
    reclassified: int
    errors: int
    skipped: int
    progress: float
    estimated_time_remaining: Optional[int] = None

# 分类信息
class CategoryInfo(BaseModel):
    name: str
    description: str
    priority: int

# 手动修改和操作请求结构体
class ImageRenameRequest(BaseModel):
    image_path: str
    new_name: str

class ImageMoveRequest(BaseModel):
    image_path: str
    target_category: str

class ImageDeleteRequest(BaseModel):
    image_path: str

