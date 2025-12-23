# utils.py
import re
import string
import logging
import os
from datetime import datetime
from config import LOG_FILE, JSON_OUTPUT_DIR

# ========== 日志工具（替代手写log_debug，更规范） ==========
def init_logger():
    """初始化日志（支持控制台+文件输出，调试更方便）"""
    logger = logging.getLogger("prts_parser")
    logger.setLevel(logging.DEBUG)
    if logger.handlers:  # 避免重复添加handler
        return logger
    
    # 确保日志目录存在
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    
    # 文件handler（保存详细日志）
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
    # 控制台handler（实时输出）
    ch = logging.StreamHandler()
    ch.setFormatter(logging.Formatter("%(levelname)s | %(message)s"))
    
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger

# 初始化全局logger
logger = init_logger()

# ========== 文本处理工具 ==========
def clean_text(tag, replace_plus=True, handle_br=False) -> str:
    """统一文本清理函数（兼容字符串/BeautifulSoup元素，不破坏原有逻辑）"""
    if not tag:
        return ""
    
    # 新增：兼容字符串输入（核心适配，不影响原有bs4元素逻辑）
    if isinstance(tag, str):
        text = tag.strip()
        text = re.sub(r"\s+", " ", text).strip()
        if replace_plus:
            text = text.replace("（+）", "").strip()
        return text
    
    # 原有逻辑（处理bs4元素）完全保留
    if handle_br:
        for br in tag.find_all("br"):
            br.replace_with("\n")
        text = tag.get_text(strip=True, separator="\n")
        text = re.sub(r"\s+", " ", text).strip()
        return text
    
    text = tag.get_text(strip=True)
    if replace_plus:
        text = text.replace("（+）", "").strip()
    return text

def clean_desc(tag) -> str:
    """清理描述中的无用span标签（干员天赋/技能解析用）"""
    if not tag:
        return ""
    # 剔除算法提示、颜色span
    for bad_span in tag.select(
        'span[style*="color:#0098DC"], '
        'span[style*="color:green"], '
        'span[style*="color:#007DFA"], '
        'span[style*="display:none"]'
    ):
        bad_span.replace_with("")
    return clean_text(tag)

# ========== 文件处理工具 ==========
def clean_filename(name: str) -> str:
    """清理文件名特殊字符（避免保存失败）"""
    invalid_chars = set(string.punctuation.replace("_", "") + r":\/?*<>|")
    return "".join(c if c not in invalid_chars else "_" for c in name)

def ensure_output_dir():
    """确保输出目录存在（避免保存文件时报错）"""
    os.makedirs(JSON_OUTPUT_DIR, exist_ok=True)

# ========== 数据去重工具 ==========
def deduplicate_terms(terms: list[dict], key="term_name") -> list[dict]:
    """术语去重（通用）"""
    seen = set()
    unique = []
    for item in terms:
        if item.get(key) not in seen:
            seen.add(item[key])
            unique.append(item)
    return unique