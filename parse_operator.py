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
    # 提示框选择器（覆盖PRTS常见提示框结构）
    TOOLTIP_SELECTORS = [
        '[role="tooltip"]',
        ".tippy-box",
        ".tippy-content",
        ".tooltip-content",
        ".mw-tooltip",
        ".mc-tooltip-content"
    ]

# --- 工具函数（提取重复逻辑，提升复用性）---
def log_debug(message: str):
    """记录调试信息（含时间戳，方便排查）"""
    with open(Config.LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat()} | {message}\n")

def _txt(tag) -> str:
    """统一文本提取函数（避免重复判断）"""
    if not tag:
        return ""
    return tag.get_text(strip=True).replace("（+）", "").strip()

def _clean_desc(tag) -> str:
    """统一描述清理函数（剔除无用标签）"""
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
    return _txt(tag)

def clean_filename(name: str) -> str:
    """清理文件名特殊字符（避免保存失败）"""
    invalid_chars = set(string.punctuation.replace("_", "") + r":\/?*<>|")
    return "".join(c if c not in invalid_chars else "_" for c in name)

# --- 干员解析核心类 ---
class SingleOperatorParser:
    def __init__(self, page):
        self.page = page
        self.soup = None  # BeautifulSoup对象（延迟初始化）

    async def get_soup(self):
        """延迟初始化Soup对象（避免重复获取页面内容）"""
        if not self.soup:
            content = await self.page.content()
            self.soup = BeautifulSoup(content, "lxml")
        return self.soup

    async def parse_attrs(self):
        """解析属性表（保留原有逻辑，优化变量命名）"""
        await self.get_soup()
        # 初始化基础属性结构（优化字典推导式，更简洁）
        base_attrs = {
            "elite_0_level_1": {},
            "elite_0_max": {},
            "elite_1_max": {},
            "elite_2_max": {},
            "trust_bonus": {}
        }
        base_tbl = self.soup.select_one("table.char-base-attr-table")
        
        if base_tbl:
            headers = [_txt(th) for th in base_tbl.select("tr:first-child th, tr:first-child td")]
            # 优化表头映射逻辑（用列表推导式替代循环）
            key_mapping = [
                "elite_0_level_1" if "精英0 1级" in h else
                "elite_0_max" if "精英0 满级" in h else
                "elite_1_max" if "精英1 满级" in h else
                "elite_2_max" if "精英2 满级" in h else
                "trust_bonus" if "信赖加成上限" in h else
                "" for h in headers
            ]
            attr_mapping = {"生命上限": "max_hp", "攻击": "atk", "防御": "def", "法术抗性": "res"}
            
            # 解析属性行（跳过表头）
            for tr in base_tbl.select("tr")[1:]:
                tds = [_txt(td) for td in tr.select("th, td")]
                if len(tds) < 2:
                    continue
                attr_key = attr_mapping.get(tds[0], tds[0].lower())
                # 填充属性值（优化索引逻辑）
                for idx, val in enumerate(tds[1:], 1):
                    if idx < len(key_mapping) and key_mapping[idx]:
                        base_attrs[key_mapping[idx]][attr_key] = val

        # 解析额外属性
        extra_attrs = {}
        extra_tbl = self.soup.select_one("table.char-extra-attr-table")
        extra_key_map = {
            "再部署时间": "redployment_time",
            "初始部署费用": "initial_deployment_cost",
            "攻击间隔": "attack_interval",
            "阻挡数": "block_count",
            "所属势力": "faction",
            "隐藏势力": "hidden_faction"
        }
        
        if extra_tbl:
            for tr in extra_tbl.select("tr"):
                cells = [_txt(cell) for cell in tr.select("th, td")]
                # 按两两分组解析（避免索引越界）
                for i in range(0, len(cells) - 1, 2):
                    raw_key, val = cells[i], cells[i+1]
                    extra_attrs[extra_key_map.get(raw_key, raw_key)] = val

        return {"base_attributes": base_attrs, "extra_attributes": extra_attrs}

    async def parse_chara(self):
        """解析特性和分支（保留原有逻辑，优化空值处理）"""
        await self.get_soup()
        result = {
            "branch_name": "",
            "branch_description": "",
            "trait_details": ""
        }
        trait_tbl = self.soup.select_one("table.wikitable.logo")
        
        if trait_tbl:
            rows = trait_tbl.select("tr")
            # 解析分支名称和描述（优化索引判断）
            if len(rows) > 1:
                tds = rows[1].find_all("td")
                result["branch_name"] = _txt(tds[0]) if tds else ""
                result["branch_description"] = _txt(tds[1]) if len(tds) > 1 else ""
            
            # 解析分支详情（优化查找逻辑）
            branch_row = trait_tbl.find("tr", string=re.compile("分支信息"))
            if branch_row:
                next_row = branch_row.find_next_sibling("tr")
                if next_row:
                    result["trait_details"] = "".join(_clean_desc(li) for li in next_row.select("li"))

        return result

    async def parse_talents(self):
        """解析天赋（保留原有逻辑，优化重复代码）"""
        await self.get_soup()
        talents = []
        talent_header = self.soup.find("span", id="天赋")
        if not talent_header:
            log_debug("未找到天赋区域")
            return talents

        def parse_single_talent(table, talent_type: str, span_prefix: str) -> dict:
            """提取单个天赋（优化变量初始化）"""
            talent = {
                "talent_type": talent_type,
                "talent_name": "",
                "remarks": "",
                "details": []
            }
            rows = table.find_all("tr")
            is_remark_section = False
            remark_text = ""

            for idx, row in enumerate(rows):
                if idx == 0:
                    continue  # 跳过表头
                tds = row.find_all("td")
                th = row.find("th")

                # 判断是否为备注行
                if idx == len(rows) - 2 and th:
                    is_remark_section = True
                    continue
                if not tds:
                    continue

                # 处理备注
                if is_remark_section:
                    remark_text = _txt(tds[0])
                    break

                # 提取天赋名称（仅首次赋值）
                current_name = _txt(tds[0])
                if not talent["talent_name"] and current_name:
                    talent["talent_name"] = current_name

                # 提取天赋详情（优化选择器逻辑）
                talent["details"].append({
                    "trigger_condition": _txt(tds[1]),
                    "description": _clean_desc(tds[2].select_one(f"span.{span_prefix}潜能_1")),
                    "potential_enhancement": _clean_desc(tds[2].select_one(f"span.{span_prefix}潜能_2"))
                })

            talent["remarks"] = remark_text
            return talent if talent["talent_name"] and talent["details"] else None

        # 解析第一天赋
        first_talent_tbl = talent_header.find_next("table", class_="wikitable")
        if first_talent_tbl:
            first_talent = parse_single_talent(first_talent_tbl, "第一天赋", "第一天赋")
            if first_talent:
                talents.append(first_talent)

        # 解析第二天赋（优化空值判断）
        second_talent_tbl = first_talent_tbl.find_next_sibling("table", class_="wikitable") if first_talent_tbl else None
        if second_talent_tbl:
            second_talent = parse_single_talent(second_talent_tbl, "第二天赋", "第二天赋")
            if second_talent:
                talents.append(second_talent)

        log_debug(f"解析到天赋数量：{len(talents)}")
        return talents

    async def parse_skills(self):
        """解析技能（保留原有逻辑，优化错误处理）"""
        await self.get_soup()
        skills = []
        skill_header = self.soup.find("span", id="技能")
        
        if not skill_header:
            log_debug("未找到技能区域")
            return skills

        # 提取可见文本（优化函数命名和逻辑）
        def extract_visible_text(td_elem) -> str:
            visible_parts = []
            for child in td_elem.contents:
                if isinstance(child, str):
                    stripped = child.strip()
                    if stripped:
                        visible_parts.append(stripped)
                elif child.name == "span" and "display:none" not in child.get("style", ""):
                    span_text = child.get_text(strip=True)
                    if span_text:
                        visible_parts.append(span_text)
            return " ".join(visible_parts)

        # 解析单个技能（优化参数命名）
        def parse_single_skill(table, skill_idx: int) -> dict:
            skill = {
                "skill_number": skill_idx,
                "skill_name": "",
                "skill_type": "",
                "unlock_condition": f"精英{skill_idx}",
                "remark": "",
                "skill_levels": []
            }
            rows = table.find_all("tr")
            is_remark = False

            for idx, row in enumerate(rows):
                tds = row.find_all("td")
                if idx == 0:
                    # 提取技能名称（优化查找逻辑）
                    big_tag = tds[1].find("big")
                    skill["skill_name"] = _txt(big_tag) if big_tag else _txt(tds[1])
                    # 提取技能类型（优化列表推导式）
                    tooltip_spans = tds[2].find_all("span", class_="mc-tooltips")
                    skill["skill_type"] = "|".join(
                        [_txt(span) for span in tooltip_spans if _txt(span)]
                    )
                    continue

                # 提取关键等级（7级和专精3）
                if idx == 8 or idx == 11:
                    if len(tds) >= 5:
                        skill["skill_levels"].append({
                            "level": _txt(tds[0]),
                            "description": extract_visible_text(tds[1]),
                            "initial_sp": _txt(tds[2]),
                            "sp_cost": _txt(tds[3]),
                            "duration": _txt(tds[4])
                        })
                    continue

                # 识别备注行
                if idx == len(rows) - 2 and row.find("th"):
                    is_remark = True
                    continue
                if is_remark:
                    skill["remark"] = _txt(tds[0])
                    break

            return skill

        # 解析3个技能（优化循环逻辑，避免重复代码）
        current_table = skill_header.find_parent("h2").find_next_sibling("table")
        skill_tables = []
        for _ in range(3):
            if current_table and "wikitable" in current_table.get("class", []):
                skill_tables.append(current_table)
                current_table = current_table.find_next_sibling("table", class_="wikitable nomobile logo")
            else:
                log_debug(f"未找到第{len(skill_tables)+1}个技能表格")
                break

        # 批量解析技能
        for idx, table in enumerate(skill_tables, 1):
            skills.append(parse_single_skill(table, idx))

        log_debug(f"解析到技能数量：{len(skills)}")
        return skills

    async def parse_terms(self):
        """最终跑通版术语解析（无重复定义，优化配置依赖）"""
        await self.get_soup()
        terms = []
        term_seen = set()
        total_success = 0
        total_failed = 0

        try:
            # 1. 定位核心内容区
            content_div = self.soup.find("div", id="mw-content-text")
            if not content_div:
                log_debug("未找到核心内容区，跳过术语提取")
                print("⚠️  未找到核心内容区，跳过术语提取")
                return terms

            # 2. 筛选有效术语标签（依赖全局配置，方便调整）
            term_tags = content_div.find_all(
                lambda tag: tag.name == "span"
                and tag.get("class")
                and any("mc-tooltips" in c for c in tag.get("class"))
                and len(_txt(tag).strip()) >= Config.TERM_MIN_LENGTH
                and not _txt(tag).strip().isdigit()
            )
            total_terms = len(term_tags)
            print(f"\n🔍 术语提取开始：共找到 {total_terms} 个有效潜在术语标签")
            if total_terms == 0:
                return terms

            # 3. 逐个处理术语
            for idx, term_tag in enumerate(term_tags, 1):
                term_name = _txt(term_tag).strip()
                # 跳过重复或无效术语
                if not term_name or term_name in term_seen:
                    print(f"⏭️  术语{idx}/{total_terms}：跳过（重复/无效）→ 名称：{term_name}")
                    continue

                try:
                    # 3.1 构建CSS定位器（优化特殊字符处理）
                    class_list = term_tag.get("class", [])
                    valid_classes = [c for c in class_list if "mc-tooltips" in c]
                    if not valid_classes:
                        print(f"⏭️  术语{idx}/{total_terms}：跳过（无有效class）→ 名称：{term_name}")
                        total_failed += 1
                        continue

                    term_class = valid_classes[0]
                    # 处理单引号、双引号、反斜杠等特殊字符
                    safe_name = term_name.replace("'", "\\'").replace('"', '\\"').replace("\\", "\\\\")
                    css_selector = f"span.{term_class}:has-text('{safe_name}')"
                    locator = self.page.locator(css_selector).first  # 仅取第一个，避免严格模式报错

                    # 调试：打印匹配数量
                    match_count = await self.page.locator(css_selector).count()
                    if match_count > 1:
                        log_debug(f"术语{term_name}匹配{match_count}个元素，取第一个")
                        print(f"⚠️  术语{idx}/{total_terms}：定位器匹配{match_count}个元素，已取第一个 → 名称：{term_name}")

                    # 3.2 悬浮触发提示框（依赖配置项，统一管理）
                    await locator.wait_for(state="visible", timeout=Config.LOCATOR_WAIT_TIMEOUT)
                    await locator.scroll_into_view_if_needed()
                    await locator.hover(force=True)
                    await asyncio.sleep(Config.TOOLTIP_RENDER_WAIT)  # 给足渲染时间

                    # 3.3 提取提示框内容（优化循环逻辑）
                    term_type = "无"
                    term_desc = ""
                    tip_found = False

                    for tip_selector in Config.TOOLTIP_SELECTORS:
                        tip_locator = self.page.locator(tip_selector).first
                        if await tip_locator.count() > 0:
                            tip_found = True
                            # 提取<strong>内容（术语类型）
                            strong_handles = await tip_locator.locator("strong").all()
                            strong_texts = []
                            for handle in strong_handles:
                                text = await handle.inner_text(timeout=Config.TEXT_EXTRACT_TIMEOUT)
                                clean_text = text.strip().split(":")[0].rstrip("：:")
                                if clean_text:
                                    strong_texts.append(clean_text)
                            term_type = "，".join(strong_texts) if strong_texts else "无"
                            # 避免类型与名称重复
                            if term_type == term_name:
                                term_type = "无"

                            # 提取正文（排除strong）
                            content_handles = await tip_locator.locator(":not(strong)").all()
                            content_parts = []
                            for handle in content_handles:
                                text = await handle.inner_text(timeout=Config.TEXT_EXTRACT_TIMEOUT)
                                clean_text = text.strip()
                                if clean_text:
                                    content_parts.append(clean_text)
                            term_desc = "\n".join(content_parts) if content_parts else ""

                            # 正文为空时取完整文本
                            if not term_desc:
                                full_text = await tip_locator.inner_text(timeout=Config.TEXT_EXTRACT_TIMEOUT)
                                if term_type != "无":
                                    full_text = full_text.replace(f"{term_type}：", "").replace(f"{term_type}:", "").replace(term_type, "")
                                term_desc = full_text.strip()
                            break

                    if not tip_found:
                        log_debug(f"术语{term_name}未找到提示框")
                        print(f"❌ 术语{idx}/{total_terms}：失败（未找到提示框）→ 名称：{term_name}")
                        total_failed += 1
                        continue

                    # 3.4 过滤无效描述
                    formatted_desc = re.sub(r"\s+", "\n", term_desc).strip()
                    if len(formatted_desc) < Config.DESC_MIN_LENGTH:
                        log_debug(f"术语{term_name}描述过短（{len(formatted_desc)}字），跳过")
                        print(f"⏭️  术语{idx}/{total_terms}：跳过（描述过短）→ 名称：{term_name}")
                        total_failed += 1
                        continue

                    # 3.5 加入结果（去重）
                    if term_name not in term_seen:
                        terms.append({
                            "term_name": term_name,
                            "term_type": term_type,
                            "term_description": formatted_desc
                        })
                        term_seen.add(term_name)
                        total_success += 1
                        print(f"✅ 术语{idx}/{total_terms}：成功 → 名称：{term_name} | 类型：{term_type} | 描述长度：{len(formatted_desc)}字")

                    # 3.6 清理状态（避免影响下一个术语）
                    await self.page.mouse.move(100, 100)
                    await asyncio.sleep(Config.MOUSE_MOVE_WAIT)

                # 精准捕获错误（优化错误日志）
                except PlaywrightTimeoutError:
                    log_debug(f"术语{term_name}提取超时")
                    print(f"❌ 术语{idx}/{total_terms}：失败（超时）→ 名称：{term_name}")
                    total_failed += 1
                    continue
                except AttributeError as e:
                    log_debug(f"术语{term_name}属性错误：{str(e)[:50]}")
                    print(f"❌ 术语{idx}/{total_terms}：失败（属性错误）→ 名称：{term_name} | 错误：{str(e)[:50]}")
                    total_failed += 1
                    continue
                except Exception as e:
                    log_debug(f"术语{term_name}未知错误：{str(e)[:50]}")
                    print(f"❌ 术语{idx}/{total_terms}：失败（未知错误）→ 名称：{term_name} | 错误：{str(e)[:50]}")
                    total_failed += 1
                    continue

        except Exception as e:
            log_debug(f"术语提取主流程错误：{str(e)}")
            print(f"\n⚠️  术语提取主流程错误：{str(e)}")

        # 最终去重（双重保障）
        unique_terms = []
        final_seen = set()
        for term in terms:
            if term["term_name"] not in final_seen:
                final_seen.add(term["term_name"])
                unique_terms.append(term)

        # 打印统计报告
        print(f"\n📊 术语提取完成：总计{total_terms}个有效潜在术语 → 成功{total_success}个 | 失败{total_failed}个 | 去重后{len(unique_terms)}个")
        log_debug(f"术语提取统计：总计{total_terms} | 成功{total_success} | 失败{total_failed} | 去重后{len(unique_terms)}")
        return unique_terms

    async def parse_all(self, operator_name: str):
        """主解析入口（优化返回结构，统一格式）"""
        return {
            "operator_name": operator_name,
            "metadata": {
                "last_updated": datetime.now().isoformat(),
                "source": Config.BASE_URL,
                "version": "v10.0",
                "parser_config": {
                    "headless": Config.HEADLESS,
                    "term_min_length": Config.TERM_MIN_LENGTH,
                    "desc_min_length": Config.DESC_MIN_LENGTH
                }
            },
            "characteristic": await self.parse_chara(),
            "attributes": await self.parse_attrs(),
            "talents": await self.parse_talents(),
            "skills": await self.parse_skills(),
            "terms": await self.parse_terms()
        }

# --- 外部调用入口 ---
async def parse_single_operator(operator_name: str):
    """解析单个干员（优化错误处理和文件保存）"""
    operator_name = operator_name.strip()
    if not operator_name:
        log_debug("干员名称为空，跳过解析")
        print("❌ 干员名称为空，无法解析")
        return None

    url = f"{Config.BASE_URL}/w/{operator_name}"
    print(f"--- 开始爬取干员: {operator_name} ({url}) ---")
    log_debug(f"开始爬取干员：{operator_name}，URL：{url}")

    async with async_playwright() as p:
        try:
            # 启动浏览器（优化启动参数）
            browser = await p.chromium.launch(
                headless=Config.HEADLESS,
                args=["--no-sandbox", "--disable-dev-shm-usage"]  # 适配Linux环境
            )
            page = await browser.new_page()

            # 页面加载（优化等待逻辑）
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_selector("#mw-content-text", timeout=Config.PAGE_LOAD_TIMEOUT)
            log_debug(f"页面加载完成：{url}")

            # 执行解析
            parser = SingleOperatorParser(page)
            result = await parser.parse_all(operator_name)

            # 保存结果（优化文件名和IO错误处理）
            safe_filename = clean_filename(operator_name)
            output_path = f"{safe_filename}.json"
            try:
                with open(output_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)
                print(f"✅ 成功保存: {output_path}")
                log_debug(f"结果保存成功：{output_path}")
            except IOError as e:
                log_debug(f"保存文件失败：{str(e)}")
                print(f"❌ 保存文件失败：{str(e)}")

            # 打印调试信息（优化格式）
            print("\n=== 解析结果汇总 ===")
            print(f"干员名称: {result['operator_name']}")
            print(f"分支名称: {result['characteristic']['branch_name']}")
            print(f"天赋数量: {len(result['talents'])}")
            print(f"技能数量: {len(result['skills'])}")
            print(f"术语数量: {len(result['terms'])}")
            print("====================")

            return result

        except PlaywrightTimeoutError:
            log_debug(f"爬取{operator_name}超时：{url}")
            print(f"❌ 页面加载超时（{Config.PAGE_LOAD_TIMEOUT/1000}秒）")
            return None
        except Exception as e:
            log_debug(f"爬取{operator_name}未知错误：{str(e)}")
            print(f"❌ 解析错误：{str(e)[:100]}")
            return None
        finally:
            # 确保浏览器关闭（优化资源释放）
            if 'browser' in locals():
                await browser.close()
                log_debug("浏览器已关闭")

# --- 执行入口 ---
if __name__ == "__main__":
    # 支持命令行传入干员名称（优化易用性）
    import sys
    operator_name = "焰影苇草"
    if len(sys.argv) > 1:
        operator_name = sys.argv[1]
    asyncio.run(parse_single_operator(operator_name))