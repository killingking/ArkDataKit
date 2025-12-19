# terms_parse.py
import requests
import json
from bs4 import BeautifulSoup
from config import TERM_STATIC_URL, HEADERS, JSON_OUTPUT_DIR
from utils import logger, clean_text, deduplicate_terms, ensure_output_dir

class TermStaticCrawler:
    """静态术语爬取器（轻量类封装，无状态）"""
    def __init__(self):
        # 无状态，仅初始化配置引用
        self.url = TERM_STATIC_URL
        self.headers = HEADERS
        self.output_dir = JSON_OUTPUT_DIR
        self.output_filename = "prts_terms.json"

    def fetch(self) -> str:
        """抓取术语页面HTML"""
        try:
            response = requests.get(self.url, headers=self.headers, timeout=30)
            response.raise_for_status()  # 捕获HTTP错误
            response.encoding = "utf-8"
            logger.info(f"✅ 成功抓取术语页面：{self.url}")
            return response.text
        except Exception as e:
            logger.error(f"❌ 抓取失败：{type(e).__name__}: {str(e)}")
            raise

    def parse(self, html: str) -> list[dict]:
        """解析术语数据"""
        terms = []
        soup = BeautifulSoup(html, "lxml")
        content_div = soup.find("div", id="mw-content-text")
        if not content_div:
            logger.warning("⚠️  未找到核心内容区域")
            return terms
        
        # 定位锚点p标签（style=margin:0;padding:0; + 有id）
        anchor_ps = content_div.find_all(
            "p",
            attrs={"style": "margin:0;padding:0;", "id": True}
        )
        logger.info(f"🔍 找到锚点p标签数量：{len(anchor_ps)}")
        
        # 解析每个术语
        for anchor_p in anchor_ps:
            term_name = anchor_p.get("id", "").strip()
            if not term_name:
                continue
            
            # 取下一个p标签的解释（用统一文本处理函数）
            next_p = anchor_p.find_next_sibling("p")
            explanation = clean_text(next_p, handle_br=True) if next_p else ""
            # 剔除解释中重复的术语名
            if term_name in explanation:
                explanation = explanation.replace(term_name, "").strip()
            
            terms.append({
                "term_name": term_name,
                "term_explanation": explanation,
            })
        
        # 去重（用通用去重工具）
        terms = deduplicate_terms(terms)
        logger.info(f"📊 解析完成：有效术语数量 {len(terms)}")
        return terms

    def save(self, terms: list[dict]):
        """保存术语到JSON（确保目录存在）"""
        ensure_output_dir()
        output_path = f"{self.output_dir}/{self.output_filename}"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(terms, f, ensure_ascii=False, indent=2)
        logger.info(f"✅ 术语已保存到 {output_path}")

    def run(self) -> list[dict]:
        """一键执行：抓取→解析→保存（对外核心方法）"""
        logger.info(f"=== 开始静态爬取术语: {self.url} ===")
        try:
            html = self.fetch()
            terms = self.parse(html)
            self.save(terms)
            
            # 打印前5个示例（调试用）
            if terms:
                logger.info("\n=== 爬取结果示例 ===")
                for idx, t in enumerate(terms[:5], 1):
                    logger.info(f"{idx}. 名称：{t['term_name']}")
                    logger.info(f"   解释：{t['term_explanation'][:50]}...")
            else:
                logger.warning("⚠️  未提取到有效术语")
            return terms
        except Exception as e:
            logger.error(f"❌ 爬取流程失败：{str(e)}")
            return []

# 保留独立执行入口（方便单独调试）
if __name__ == "__main__":
    crawler = TermStaticCrawler()
    crawler.run()