import requests
import json
import re
from bs4 import BeautifulSoup

# 全局配置
BASE_URL = "https://prts.wiki/w/术语释义"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def _txt(tag) -> str:
    """处理<br>标签，清理文本格式"""
    if not tag:
        return ""
    for br in tag.find_all("br"):
        br.replace_with("\n")
    text = tag.get_text(strip=True, separator="\n")
    text = re.sub(r"\s+", " ", text).strip()
    return text

def parse_terms_static():
    """纯静态爬取，无需浏览器/Playwright"""
    terms = []
    try:
        # 发送请求（模拟浏览器，避免被反爬）
        response = requests.get(BASE_URL, headers=HEADERS, timeout=30)
        response.raise_for_status()
        response.encoding = "utf-8"
        
        # 解析页面
        soup = BeautifulSoup(response.text, "lxml")
        content_div = soup.find("div", id="mw-content-text")
        if not content_div:
            print("⚠️  未找到核心内容区域")
            return terms
        
        # 定位锚点p标签（style=margin:0;padding:0; + 有id）
        anchor_ps = content_div.find_all(
            "p",
            attrs={"style": "margin:0;padding:0;", "id": True}
        )
        print(f"找到锚点p标签数量：{len(anchor_ps)}")
        
        # 解析每个术语
        for anchor_p in anchor_ps:
            term = {"term_name": "", "term_explanation": ""}
            # 从id提取术语名（最准确）
            term_name = anchor_p.get("id", "").strip()
            if not term_name:
                continue
            # 取下一个p标签的解释
            next_p = anchor_p.find_next_sibling("p")
            explanation = _txt(next_p) if next_p else "无详细解释"
            # 剔除解释中重复的术语名
            if term_name in explanation:
                explanation = explanation.replace(term_name, "").strip()
            
            term["term_name"] = term_name
            term["term_explanation"] = explanation
            terms.append(term)
        
        # 去重（避免重复术语）
        seen_terms = set()
        unique_terms = []
        for t in terms:
            if t["term_name"] not in seen_terms:
                seen_terms.add(t["term_name"])
                unique_terms.append(t)
                
    except Exception as e:
        print(f"❌ 爬取失败：{type(e).__name__}: {str(e)}")
        return []
    
    return unique_terms

if __name__ == "__main__":
    print(f"--- 开始静态爬取术语: {BASE_URL} ---")
    terms = parse_terms_static()
    
    print("\n=== 爬取结果汇总 ===")
    print(f"有效术语数量：{len(terms)}")
    if terms:
        # 保存到JSON文件
        with open("prts_terms.json", "w", encoding="utf-8") as f:
            json.dump(terms, f, ensure_ascii=False, indent=2)
        print("✅ 术语已保存到 prts_terms.json")
        # 打印前5个示例
        for idx, t in enumerate(terms[:5], 1):
            print(f"{idx}. 名称：{t['term_name']}")
            print(f"   解释：{t['term_explanation'][:50]}...")
    else:
        print("⚠️  未提取到有效术语")