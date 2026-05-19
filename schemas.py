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
    base_dir: Optional[str] = None
    batch_size: Optional[int] = None
    max_retries: Optional[int] = None

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
