# 在原文件基础上新增：拆分解析逻辑为独立方法，便于复用
class SingleOperatorParser:
    # ... 保留原有解析逻辑 ...

    async def parse_all(self, operator_name):
        """整合所有解析结果"""
        return {
            "operator_name": operator_name,
            "characteristic": await self.parse_characteristic(),  # 特性信息
            "talents": await self.parse_talents(),                # 天赋
            "skills": await self.parse_skills(),                  # 技能
            "terms": await self.parse_terms()                     # 术语（如果有）
        }

# 保持原入口函数，但移除文件保存逻辑（改由数据库存储）
async def parse_single_operator(operator_name: str):
    operator_name = operator_name.strip()
    if not operator_name:
        print("❌ 干员名称为空")
        return None

    url = f"{Config.BASE_URL}/w/{operator_name}"
    print(f"🔍 爬取 {operator_name}: {url}")

    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(
                headless=Config.HEADLESS,
                args=["--no-sandbox"]
            )
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_selector("#mw-content-text", timeout=Config.PAGE_LOAD_TIMEOUT)

            parser = SingleOperatorParser(page)
            result = await parser.parse_all(operator_name)
            await browser.close()
            return result  # 返回解析结果，由主程序处理存储

        except Exception as e:
            print(f"❌ 解析 {operator_name} 出错: {str(e)}")
            return None