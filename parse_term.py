import asyncio
import json
import re
import string
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup

# --- 全局配置（集中管理，方便修改）---
class Config:
    BASE_URL = "https://prts.wiki"
    HEADLESS = True  # 调试时可改为False，查看浏览器操作
    LOG_FILE = "prts_parse_debug.log"
    # 超时配置（统一管理，避免硬编码）
    PAGE_LOAD_TIMEOUT = 20000  # 页面加载超时（20秒）
    LOCATOR_WAIT_TIMEOUT = 3000  # 元素等待超时（3秒）
    TEXT_EXTRACT_TIMEOUT = 1500  # 文本提取超时（1.5秒）
    # 等待时间配置（平衡效率和稳定性）
    TOOLTIP_RENDER_WAIT = 1.2  # 提示框渲染等待时间（秒）
    MOUSE_MOVE_WAIT = 0.6  # 移开鼠标后等待时间（秒）
    # 术语过滤配置
    TERM_MIN_LENGTH = 2  # 术语名最小长度
    DESC_MIN_LENGTH = 5  # 描述最小长度
    
def log_debug(message: str):
    """记录调试信息（含时间戳，方便排查）"""
    with open(Config.LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()} | {message}\n")

def _txt(tag) -> str:
    """统一文本提取函数（避免重复判断）"""
    if not tag:
        return ""
    return tag.get_text(strip=True).replace("（+）", "").strip()
class TermParse:
    def __init__(self,page):
        self.page = page
        self.soup = None

    async def get_soup(self):
        """延迟初始化Soup对象（避免重复获取页面内容）"""
        if not self.soup:
            content = await self.page.content()
            self.soup = BeautifulSoup(content, "lxml")
        return self.soup

    async def parse_terms(self):
        terms = []
        term_ps = self.soup.find_all(attrs={"style": "margin:0;padding:0;"})
        for p in enumerate(term_ps):
            term = {
                "term_name" : "",
                "term_explanation" : ""
            }
            if p:
                term["term_name"] = _txt(p)
                explanation_p = p.find_next_sibling()
                if explanation_p:
                    term["term_explanation"] = _txt(explanation_p)
            terms.append(term)
    
async def get_terms():
    url = f"{Config.BASE_URL}/w/术语释义"
    print(f"--- 开始爬取术语: {operator_name} ({url}) ---")
    log_debug(f"开始爬取术语：{operator_name}，URL：{url}")
    async with async_playwright() as p:
        try:
            # 启动浏览器（优化启动参数）
            browser = await p.chromium.launch(
                headless=Config.HEADLESS,
                args=["--no-sandbox", "--disable-dev-shm-usage"]  # 适配Linux环境
            )
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_selector("#mw-content-text", timeout=Config.PAGE_LOAD_TIMEOUT)
            log_debug(f"页面加载完成：{url}")

            parser = TermParse(page)
            terms = parser.parse_terms()
            print(terms)
        # # 精准捕获错误（优化错误日志）
        # except PlaywrightTimeoutError:
        #     log_debug(f"术语{term_name}提取超时")
        #     print(f"❌ 术语{idx}/{total_terms}：失败（超时）→ 名称：{term_name}")
        #     total_failed += 1
        #     continue
        except Exception as e:
            log_debug(f"术语{terms}未知错误：{str(e)[:50]}")
            print(f"❌ 术语{terms}：失败（未知错误）")
    
if __name__ == "__main__":
    get_terms()


    
        
