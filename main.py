import re
import asyncio
from playwright.async_api import async_playwright
from db_utils import DBHandler

# 配置项
CONFIG = {
    "BASE_URL": "https://prts.wiki",  # PRTS维基地址
    "HEADLESS": True,  # 无头模式（False可看到浏览器操作）
    "PAGE_LOAD_TIMEOUT": 30000,  # 页面加载超时30s
    "OPERATORS_MD_PATH": "operators.md"  # 干员列表md文件路径
}

def parse_operators_md(file_path=None):
    """从operators.md提取干员基础列表（适配新表字段）"""
    file_path = file_path or CONFIG["OPERATORS_MD_PATH"]
    operators = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # 匹配Markdown表格行（格式：| 中文名 | 稀有度 | 职业 | 分支 | 阵营 | 性别 | 位置 | 标签 |）
        pattern = r"\| (.*?) \| (.*?) \| (.*?) \| (.*?) \| (.*?) \| (.*?) \| (.*?) \| (.*?) \|"
        matches = re.findall(pattern, content)
        
        for row in matches:
            if row[0] in ["中文名", "", "—"]:  # 跳过表头/空行/分隔符
                continue
            # 提取字段并清洗
            name = row[0].strip()
            if not name:
                continue
            operators.append({
                "name": name,
                "rarity": row[1].strip(),
                "profession": row[2].strip(),
                "branch": row[3].strip(),
                "faction": row[4].strip(),
                "gender": row[5].strip(),
                "position": row[6].strip(),
                "tags": [t.strip() for t in row[7].split() if t.strip()]
            })
        print(f"📋 从{file_path}提取到 {len(operators)} 名干员")
        return operators
    except FileNotFoundError:
        print(f"❌ 未找到{file_path}文件，请检查路径")
        return []
    except Exception as e:
        print(f"❌ 解析operators.md失败: {str(e)}")
        return []

async def parse_single_operator(page, operator_name):
    """解析单个干员的详细信息（适配新表字段）"""
    operator_name = operator_name.strip()
    if not operator_name:
        return None
    
    url = f"{CONFIG['BASE_URL']}/w/{operator_name}"
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=CONFIG["PAGE_LOAD_TIMEOUT"])
        await page.wait_for_selector("#mw-content-text", timeout=CONFIG["PAGE_LOAD_TIMEOUT"])
        
        # 1. 解析职业分支/特性（适配operators表）
        branch_name = await page.locator("div[data-source='branch'] .pi-data-value").text_content() or ""
        branch_desc = await page.locator("div[data-source='branch_desc'] .pi-data-value").text_content() or ""
        trait_details = await page.locator("div[data-source='trait'] .pi-data-value").text_content() or ""
        
        # 2. 解析基础属性（适配operator_attributes表）
        attr_list = []
        attr_rows = await page.locator("table.wikitable:has(th:has-text('精英等级')) tr").all()
        for row in attr_rows[1:]:  # 跳过表头
            cols = await row.locator("td").all()
            if len(cols) < 5:
                continue
            elite_level = await cols[0].text_content() or ""
            max_hp = await cols[1].text_content() or ""
            atk = await cols[2].text_content() or ""
            def_val = await cols[3].text_content() or ""
            res = await cols[4].text_content() or ""
            attr_list.append({
                "elite_level": elite_level.strip(),
                "max_hp": max_hp.strip(),
                "atk": atk.strip(),
                "def": def_val.strip(),
                "res": res.strip()
            })
        
        # 3. 解析额外属性（适配operator_extra_attrs表）
        extra_attr = {
            "redeployment_time": await page.locator("div[data-source='redeployment'] .pi-data-value").text_content() or "",
            "initial_deployment_cost": await page.locator("div[data-source='cost'] .pi-data-value").text_content() or "",
            "attack_interval": await page.locator("div[data-source='attack_interval'] .pi-data-value").text_content() or "",
            "block_count": await page.locator("div[data-source='block'] .pi-data-value").text_content() or "",
            "hidden_faction": await page.locator("div[data-source='hidden_faction'] .pi-data-value").text_content() or ""
        }
        # 清洗额外属性值
        for k, v in extra_attr.items():
            extra_attr[k] = v.strip()
        
        # 4. 解析天赋（适配operator_talents/talent_details表）
        talents = []
        talent_blocks = await page.locator("div[data-source='talent'] .pi-data-value").all()
        for idx, block in enumerate(talent_blocks):
            talent_html = await block.inner_html()
            # 简易解析（可根据PRTS页面结构细化）
            talents.append({
                "talent_type": f"第{idx+1}天赋",
                "talent_name": await block.locator("b").text_content() or "",
                "trigger_condition": "",
                "description": await block.text_content() or "",
                "potential_enhancement": "",
                "remarks": ""
            })
        
        # 5. 解析技能（适配operator_skills/skill_levels表）
        skills = []
        skill_blocks = await page.locator("div[data-source='skill'] .pi-data-value").all()
        for idx, block in enumerate(skill_blocks):
            skill_name = await block.locator("b").text_content() or ""
            # 解析技能等级（简易版）
            levels = [
                {
                    "level": "7",
                    "initial_sp": "0",
                    "sp_cost": "30",
                    "duration": "20s",
                    "description": await block.text_content() or ""
                }
            ]
            skills.append({
                "skill_number": idx+1,
                "skill_name": skill_name.strip(),
                "skill_type": "",
                "unlock_condition": "",
                "remarks": "",
                "levels": levels
            })
        
        # 整合所有数据
        return {
            "branch_name": branch_name.strip(),
            "branch_description": branch_desc.strip(),
            "trait_details": trait_details.strip(),
            "attributes": attr_list,
            "extra_attrs": extra_attr,
            "talents": talents,
            "skills": skills
        }
    except Exception as e:
        print(f"❌ 解析{operator_name}详细信息失败: {str(e)}")
        return None

async def batch_parse_and_save(operators, db_handler):
    """批量解析干员并存储到数据库"""
    async with async_playwright() as p:
        # 启动浏览器（避免重复启动）
        browser = await p.chromium.launch(
            headless=CONFIG["HEADLESS"],
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"]
        )
        context = await browser.new_context()
        page = await context.new_page()
        
        # 逐个解析
        success_count = 0
        fail_count = 0
        for idx, op_base in enumerate(operators, 1):
            print(f"\n===== 处理第 {idx}/{len(operators)} 名干员: {op_base['name']} =====")
            
            # 1. 插入基础信息
            operator_id = db_handler.insert_operator_base(op_base)
            if not operator_id:
                fail_count += 1
                continue
            
            # 2. 解析详细信息
            op_detail = await parse_single_operator(page, op_base["name"])
            if not op_detail:
                fail_count += 1
                continue
            
            # 3. 补充基础信息的分支/特性字段
            op_base.update({
                "branch_name": op_detail["branch_name"],
                "branch_description": op_detail["branch_description"],
                "trait_details": op_detail["trait_details"]
            })
            # 重新插入（覆盖空值）
            db_handler.insert_operator_base(op_base)
            
            # 4. 插入各维度数据
            db_handler.insert_operator_attributes(operator_id, op_detail["attributes"])
            db_handler.insert_operator_extra_attrs(operator_id, op_detail["extra_attrs"])
            db_handler.insert_operator_talents(operator_id, op_detail["talents"])
            db_handler.insert_operator_skills(operator_id, op_detail["skills"])
            
            success_count += 1
        
        # 关闭浏览器
        await browser.close()
        print(f"\n📊 批量处理完成：成功{success_count}个，失败{fail_count}个")

if __name__ == "__main__":
    # 1. 初始化数据库
    db = DBHandler()
    if not db.connect():
        exit(1)
    
    try:
        # 2. 提取干员列表
        all_operators = parse_operators_md()
        if not all_operators:
            print("❌ 未提取到干员列表，退出")
            exit(1)
        
        # 3. 批量解析并存储
        asyncio.run(batch_parse_and_save(all_operators, db))
    finally:
        # 4. 关闭数据库连接
        db.close()