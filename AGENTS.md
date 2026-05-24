# AGENTS.md — 图片智能重命名和分类项目

> 本文件供 AI 编码助手阅读。项目所有代码、注释及交互界面均使用中文。
> 当前版本：**v2.2.1**

---

## 版本号规则

初始版本为 1.6.0，其中 A.B.C 的命名规则如下：
1. C 表示 Bug 修改
2. B 表示小功能更新
3. A 表示大版本更新

**【AI 编码助手必读规范】**：
代码中通过全局变量 `VERSION` 声明当前版本，**AI 在进行任何代码修改后，都必须遵循上述规则自动递增并更新版本号，无需用户提示**。修改时请同步更新脚本顶部注释、`AGENTS.md` 以及 `CLAUDE.md`，并使用新版本号生成打包文件。

---

## 项目概述

本项目是一个基于**视觉语言模型（VLM）**的**图片智能重命名与自动分类**工具，用于对本地大量图片进行批量整理。

核心工作流：
1. 扫描 `e:\Picture` 下的 18 个分类目录（含旧分类兼容），收集待处理图片；
2. 利用多线程并行计算 MD5，跳过已处理过的文件（双重去重）；
3. 将图片压缩并转为 Base64，调用火山引擎（Volces）Ark API（豆包视觉模型）生成 JSON 格式的内容描述和分类建议；
4. 综合 VLM 分类建议、文件名强特征、比例检测进行最终分类决策；
5. 以描述作为新文件名，安全移动（重命名）图片到目标目录；
6. 记录处理日志，支持断点续跑。

项目包含两个脚本：`vlm_rename_v5.py`（主程序）和 `vlm_classify.py`（分类模块，可独立运行迁移任务）。

v2.0.0 新增特性：
- **运行模式选择**：支持 1.默认分类、2.仅重命名不移动、3.整理根目录散落图片（动态扫描文件夹归类）。
- **MD5缓存隔离**：每个照片根目录使用独立的 MD5 和记录缓存文件，允许用户针对特定目录清除缓存。

---

## 技术栈与运行环境

| 项目 | 说明 |
|------|------|
| 语言 | Python 3.14（由 `.venv/pyvenv.cfg` 指定） |
| 虚拟环境 | `.venv/`（使用 `virtualenv` 创建，`include-system-site-packages = false`） |
| 核心依赖 | `Pillow`（图像压缩）、`requests`（HTTP API 调用） |
| 标准库 | `os`, `re`, `json`, `time`, `shutil`, `base64`, `threading`, `sys`, `hashlib`, `traceback`, `queue`, `pathlib`, `collections`, `concurrent.futures`, `io` |
| IDE | IntelliJ IDEA / PyCharm（`.idea/` 目录存在） |
| 操作系统 | Windows（代码中硬编码了 Windows 绝对路径） |

### 安装依赖

由于项目没有 `requirements.txt`，请确保虚拟环境中已安装：

```bash
# 在 PowerShell 或 cmd 中激活虚拟环境后
.\.venv\Scripts\activate
pip install Pillow requests
```

---

## 项目结构

```
E:\Picture\                        # 照片根目录 (BASE_DIR)
├── _app\                          # 所有程序文件
│   ├── .venv\                     # Python 虚拟环境（隐藏）
│   ├── .git\                      # Git 仓库（隐藏）
│   ├── .idea\                     # IDE 配置（隐藏）
│   ├── .claude\                   # 助手配置（隐藏）
│   ├── vlm_rename_v5.py           # 主程序（VLM重命名+分类）
│   ├── vlm_classify.py            # 分类模块（可独立运行迁移任务）
│   ├── main.py                    # FastAPI 后端（Web界面）
│   ├── schemas.py                 # 数据结构定义
│   ├── fix_md5.py                 # MD5去重修复工具
│   ├── config.json                # 配置文件（API Key等敏感信息）
│   ├── config.example.json        # 配置模板
│   ├── requirements.txt           # 依赖列表
│   ├── start.bat / start.ps1      # 启动脚本
│   ├── VLM_Renamer.spec     # PyInstaller 打包配置
│   ├── frontend\                  # 前端源码
│   ├── dist\                      # 打包产物
│   └── AGENTS.md / CLAUDE.md / README.md / LICENSE
│
├── _data\                         # 运行时数据目录（自动创建）
│   ├── rename_log.json            # 处理日志
│   ├── processed_files.txt        # 旧版去重记录
│   ├── processed_md5.txt          # MD5 去重记录
│   ├── error_log.txt              # 错误日志
│   ├── task_stats.json            # 任务统计
│   ├── categories.json            # 分类配置
│   └── .uploads\                  # 上传缓存（隐藏）
│
├── 人像写真\                      # 18 个新分类目录
├── 风景自然\
├── 插画绘画\
├── 艺术风格\
├── AI生成\
├── 学习资料\
├── 好词好句\
├── 聊天记录\
├── 影视动漫\
├── 海报设计\
├── 表情包梗图\
├── 动物萌宠\
├── 美食生活\
├── 软件界面\
├── 横屏\                        # 16:9 比例（壁纸素材）
├── 1比1\                        # 1:1 方形（头像素材）
├── 照片\                        # 相机直出兜底
└── 其他\
```

> **目录分离设计**：所有程序文件在 `_app/`，运行时数据在 `_data/`，照片目录直接在根目录下。程序通过 `config.json` 中的 `base_dir` 字段定位照片根目录。

---

## 构建与运行命令

本项目无需编译，直接解释执行。代码和虚拟环境均在 `_app/` 目录下。

```bash
# 1. 进入应用目录
cd _app

# 2. 激活虚拟环境
.\.venv\Scripts\activate

# 3. 运行主程序
python vlm_rename_v5.py

# 或使用启动脚本一键启动前后端
.\start.bat
```

### 运行时的交互流程

脚本启动后会在终端依次提示：

1. **账号选择**
   - `1` → 仅使用“账号A（135RPM）”
   - `2` → 仅使用“账号B（177RPM）”
   - 直接回车 → 双账号并发

2. **模型选择**
   - 直接回车 → 使用默认模型 `doubao-seed-2-0-lite-260428`
   - 输入新模型名 → 为当前选中账号切换模型

3. **运行模式选择**
   - `1` (默认) → 默认模式：分析重命名，并移动到分类目录
   - `2` → 仅重命名：分析重命名，保留在原目录
   - `3` → 整理根目录散落图片：扫描并分析根目录下未分类的文件，移动到已有的有效子文件夹中。

4. **处理数量选择**
   - 直接回车 → 默认每批处理 **500 张**
   - 输入数字 → 按指定数量处理
   - 输入 `0` → 处理全部待处理图片

---

## 核心模块与代码组织

项目分为两个文件：

**`vlm_classify.py`**（分类模块）：
- `CATEGORIES` / `SCAN_CATEGORIES` — 新分类体系与扫描目录列表
- `CATEGORY_KEYWORDS` — 各分类的关键词和文件名特征
- `LEGACY_MAPPING` — 旧分类→新分类映射
- `suggest_category(description, original_category, img_path, vlm_category)` — 分类决策
- `check_ratio_category(img_path)` — 比例分类检测
- `run_classification_task()` — 独立运行的非VLM迁移任务

**`vlm_rename_v5.py`**（主程序）：
- `VLM_PROMPT` / `parse_vlm_response()` — JSON格式prompt与响应解析
- `analyze_image()` — 返回 `(description, vlm_category)` 元组
- `process_single_image()` — 去重 → VLM分析 → 比例/VLM/关键词分类 → 移动 → 日志
- `worker_thread()` / `main()` — 多线程任务调度

---

## 关键业务逻辑

### 1. 图片压缩

- 将图片转换为 `RGB` 模式；
- 长边缩放到 **800px**；
- 按 JPEG 质量 `75 → 60 → 45 → 30` 逐级尝试，目标体积 **≤ 80 KB**；
- 若仍超限，尺寸减半后再保存；
- 压缩失败则回退为直接读取原文件并 Base64 编码。

### 2. 双重去重系统

- **旧格式**：`processed_files.txt` 记录 `分类/原文件名`，用于兼容历史数据；
- **新格式**：`processed_md5.txt` 记录 `md5|分类/原文件名`，防止同一文件被重复处理（即使路径或文件名已改变）。

启动时先加载两套记录，处理时先查旧格式，再计算 MD5 查新格式。

### 3. 失败重试与线程保护

- 单张图片处理失败（如 API 异常、网络超时）会自动重新入队，最多重试 **3 次**；
- 每个账号维护 `consecutive_failures` 计数，连续失败 **3 次** 则触发全局 `error_flag`，终止所有工作线程；
- 工作线程内使用 `try/except` 捕获所有异常，防止单线程崩溃拖垮整个进程。

### 4. 文件名安全与防冲突

- VLM 返回的描述会经正则过滤掉 Windows 非法字符：`\/:*?"<>|`；
- 若目标目录已存在同名文件，自动追加 `_1`、`_2` … 递增序号；
- 所有文件操作前均调用 `check_file_exists()`，防止文件被外部删除后导致异常。

---

## 分类体系 (可动态配置)

现在所有的分类都存储在 `categories.json` 中，默认有18个初始分类。
下面是默认分类，可以通过前端配置界面进行调整：

| 默认分类 | 说明 | 判定方式 |
|------|------|---------|
| 人像写真 | 真人人像、明星、coser、自拍 | VLM + 关键词 |
| 风景自然 | 风景、城市夜景、星空 | VLM + 关键词 |
| 插画绘画 | 漫画、动漫、CG、二次元 | VLM + 关键词 |
| 艺术风格 | 油画、厚涂、抽象、水墨、国画 | VLM + 关键词 |
| AI生成 | 明确由AI工具生成 | VLM + 文件名强特征 |
| 学习资料 | 笔记、课件、试卷、考题 | VLM + 关键词 |
| 好词好句 | 语录、诗词、名言、文案 | VLM + 关键词 |
| 聊天记录 | 微信/QQ聊天截图 | VLM + 文件名强特征 |
| 影视动漫 | 电影/电视剧/动漫截图 | VLM + 关键词 |
| 海报设计 | 海报、广告、封面、平面设计 | VLM + 关键词 |
| 表情包梗图 | 搞笑图、梗图、表情包 | VLM + 关键词 |
| 动物萌宠 | 猫、狗等动物图片 | VLM + 关键词 |
| 美食生活 | 食物、菜品、生活场景 | VLM + 关键词 |
| 软件界面 | APP/网页/系统截图 | VLM + 关键词 |
| 横屏 | 16:9宽屏比例（壁纸素材） | **纯比例判定**，优先级最高 |
| 1比1 | 1:1方形（头像素材） | **纯比例判定**，优先级最高 |
| 照片 | 相机/手机直出照片 | **兜底**，优先分到其他类别 |
| 其他 | 无法归入上述类别 | 最终兜底 |

> **分类决策流程**：比例检测（最高优先）→ VLM直接分类 → 文件名强特征覆盖 → 关键词得分制 → 原分类保护

---

## 代码风格与开发约定

- **语言**：代码注释、变量名（混合拼音与英文）、用户交互文本均以**中文**为主；
- **格式**：使用 4 空格缩进；
- **路径处理**：混合使用 `pathlib.Path` 与字符串路径；`BASE_DIR` 使用原始字符串 `r"e:\Picture"`；
- **全局状态**：大量使用模块级全局变量（`stats`、`processed_keys`、各类 `Lock`），未封装为类；
- **配置分离**：API Key 和本地路径已抽离到 `config.json`，不再硬编码在源码中；
- **无类型注解**：函数参数与返回值未使用类型提示。

---

## 测试策略

本项目**没有单元测试或自动化测试框架**。验证方式以手动运行为主：

1. 运行脚本，观察终端统计输出（处理数、重分类数、错误数、跳过数）；
2. 检查 `_data/rename_log.json` 是否正确追加记录；
3. 检查目标目录下文件是否按预期重命名和移动；
4. 若出现错误，查看 `_data/error_log.txt`（运行前会被自动清空）。

---

## 安全与敏感信息注意事项

- **配置分离**：所有敏感信息（如 API Key 和本地路径）均存储在 `config.json` 中，已在 `.gitignore` 排除，**切勿提交此文件**；
- **本地文件系统操作**：脚本直接对指定的目录进行移动、重命名、删除（日志清空），运行前建议备份重要图片；
- **网络请求**：仅向 `https://ark.cn-beijing.volces.com/api/v3/chat/completions` 发送请求，携带 `Authorization: Bearer <api_key>`；
- **无输入校验**：外部输入仅限于交互式菜单，不涉及 Web 接口或文件上传，SQL 注入、XSS 等风险不存在。

---

## 常见问题与调试

| 现象 | 排查建议 |
|------|---------|
| 启动时报路径不存在 | 检查 `config.json` 中的 `base_dir` 路径是否有效，`_data/` 目录会自动创建 |
| 所有图片都被跳过 | 检查 `_data/processed_files.txt` 和 `_data/processed_md5.txt` 是否被意外清空或覆盖 |
| API 持续报错 | 检查 API Key 是否过期；检查 `consecutive_failures` 是否已达上限；查看 `_data/error_log.txt` |
| 处理速度极慢 | 默认使用双账号并发 + 8 线程 MD5 预扫描，瓶颈通常在 API 响应时间；可尝试切换账号或调整 `BATCH_SIZE` |
| 虚拟环境缺少依赖 | 在 `.venv` 中手动 `pip install Pillow requests` |

---

## 文件清单与职责

| 文件 | 职责 |
|------|------|
| `vlm_rename_v5.py` | 主程序：VLM调用、重命名、多线程调度 |
| `vlm_classify.py` | 分类模块：分类体系定义、分类决策逻辑、独立迁移任务 |
| `main.py` | FastAPI 后端：Web界面API、批量任务调度 |
| `schemas.py` | 数据结构定义（Pydantic模型） |
| `fix_md5.py` | MD5去重记录修复工具 |
| `_data/rename_log.json` | 人类可读的 JSON 处理历史，支持审计 |
| `_data/processed_files.txt` | 旧版去重白名单，纯文本，一行一条 |
| `_data/processed_md5.txt` | 新版 MD5 去重白名单，格式 `md5|path` |
| `_data/categories.json` | 动态分类配置 |
| `_data/task_stats.json` | 任务统计持久化 |
| `.venv/pyvenv.cfg` | 虚拟环境元数据，指明 Python 3.14 |
