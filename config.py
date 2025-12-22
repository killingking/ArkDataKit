# config.py
import os
from datetime import timedelta

# 强制加载.env（绝对路径）
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(PROJECT_ROOT, ".env")

# ========== 基础请求配置 ==========
BASE_URL = "https://prts.wiki"
TERM_STATIC_URL = f"{BASE_URL}/w/术语释义"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ========== Playwright配置（干员详情解析用） ==========
PLAYWRIGHT_CONFIG = {
    "headless": True,  # 调试时改为False，可看到浏览器操作
    "browser_args": ["--no-sandbox", "--disable-dev-shm-usage"],  # 适配Linux/Windwos
    "timeout": {
        "page_load": timedelta(seconds=20).total_seconds() * 1000,  # 20秒
        "locator_wait": timedelta(seconds=3).total_seconds() * 1000,  # 3秒
        "text_extract": timedelta(seconds=1.5).total_seconds() * 1000  # 1.5秒
    },
    "wait_time": {
        "tooltip_render": 1.2,  # 提示框渲染等待
        "mouse_move": 0.6  # 鼠标移开后等待
    },
    "term_filter": {
        "min_length": 2,  # 术语名最小长度
        "desc_min_length": 5  # 术语描述最小长度
    },
    "tooltip_selectors": [  # PRTS提示框常见选择器
        '[role="tooltip"]', ".tippy-box", ".tippy-content",
        ".tooltip-content", ".mw-tooltip", ".mc-tooltip-content"
    ]
}

# ========== 干员一览配置 ==========
OPERATOR_LIST_CONFIG = {
    "url": f"{BASE_URL}/w/干员一览",
    "json_output": "operators.json",
    # 原始属性→规范字段映射（保留字段含义注释）
    "attr_mapping": {
        'data-zh': 'name_cn',          # 干员中文名
        'data-rarity': 'rarity',       # 稀有度（1-6星，原始0-5需+1）
        'data-profession': 'profession',# 主职业
        'data-subprofession': 'sub_profession', # 职业分支
        'data-logo': 'faction',        # 所属阵营
        'data-sex': 'gender',          # 性别
        'data-position': 'position',   # 部署位置
        'data-tag': 'tags'             # 干员标签
    }
}

# ========== 数据库配置（默认值，优先读.env） ==========
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 3306)),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "arknights"),
    "charset": "utf8mb4"
}

# ========== 输出配置 ==========
#是支持相对路径的
LOG_FILE = "./log/prts_parse_debug.log"
JSON_OUTPUT_DIR = "./output"  # JSON输出目录