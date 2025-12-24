import asyncio
import json
import re
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup
from config import BASE_URL, PLAYWRIGHT_CONFIG, JSON_OUTPUT_DIR
from utils import logger, clean_text, clean_desc, clean_filename, ensure_output_dir

class OperatorDetailParser:
    """干员详情解析器（有状态类封装，维护page/soup）"""
    # ========== 全局复用的浏览器/上下文（类属性） ==========
    _shared_playwright = None
    _shared_browser = None
    _shared_context = None
    _browser_initialized = False
    _lock = asyncio.Lock()  # 新增：并发锁，避免多实例竞争资源

    # ========== 1. 初始化方法 ==========
    def __init__(self, operator_name: str):
        self.operator_name = operator_name.strip()
        self.url = f"{BASE_URL}/w/{self.operator_name}" if self.operator_name else ""
        self.page = None
        self.soup = None
        
        # 从配置读取参数
        self.term_min_length = PLAYWRIGHT_CONFIG["term_filter"]["min_length"]
        self.desc_min_length = PLAYWRIGHT_CONFIG["term_filter"]["desc_min_length"]
        self.tooltip_selectors = PLAYWRIGHT_CONFIG["tooltip_selectors"]
        self.wait_times = PLAYWRIGHT_CONFIG["wait_time"]
        self.timeouts = PLAYWRIGHT_CONFIG["timeout"]
        self.browser_args = PLAYWRIGHT_CONFIG["browser_args"]
        self.headless = PLAYWRIGHT_CONFIG["headless"]

    # ========== 2. 全局浏览器初始化（加锁+属性检查） ==========
    @classmethod
    async def init_shared_browser(cls):
        """初始化全局复用的浏览器实例（加锁+状态防护）"""
        async with cls._lock:  # 关键：并发安全
            if cls._browser_initialized:
                # 双重检查：对象存在 + 有is_closed方法 + 未关闭
                context_valid = (
                    cls._shared_context 
                    and hasattr(cls._shared_context, 'is_closed') 
                    and not cls._shared_context.is_closed()
                )
                if context_valid:
                    return cls._shared_context
                else:
                    logger.warning("⚠️ 全局上下文无效，清理后重新初始化")
                    await cls.close_shared_browser()

            try:
                cls._shared_playwright = await async_playwright().start()
                browser_args = PLAYWRIGHT_CONFIG["browser_args"] + [
                    "--no-sandbox",
                    "--disable-gpu",
                    "--disable-dev-shm-usage",
                    "--disk-cache-dir=/tmp/playwright-cache",
                    "--max-old-space-size=256",
                    "--memory-pressure-off"
                ]
                cls._shared_browser = await cls._shared_playwright.chromium.launch(
                    headless=cls.headless,
                    args=browser_args,
                    timeout=60000
                )
                cls._shared_context = await cls._shared_browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
                cls._browser_initialized = True
                logger.info("✅ 全局浏览器实例初始化完成（复用模式）")
                return cls._shared_context
            except Exception as e:
                logger.error(f"❌ 全局浏览器初始化失败：{str(e)}")
                await cls.close_shared_browser()
                raise

    # ========== 3. 全局浏览器关闭（加锁+属性检查） ==========
    @classmethod
    async def close_shared_browser(cls):
        """关闭全局浏览器实例（加锁+安全关闭）"""
        async with cls._lock:
            # 关闭上下文（检查对象+方法是否存在）
            if cls._shared_context and hasattr(cls._shared_context, 'is_closed') and not cls._shared_context.is_closed():
                try:
                    await cls._shared_context.close()
                except Exception as e:
                    logger.warning(f"⚠️ 关闭上下文时警告：{str(e)}")
            cls._shared_context = None

            # 关闭浏览器
            if cls._shared_browser and hasattr(cls._shared_browser, 'is_closed') and not cls._shared_browser.is_closed():
                try:
                    await cls._shared_browser.close()
                except Exception as e:
                    logger.warning(f"⚠️ 关闭浏览器时警告：{str(e)}")
            cls._shared_browser = None

            # 停止playwright
            if cls._shared_playwright:
                try:
                    await cls._shared_playwright.stop()
                except Exception as e:
                    logger.warning(f"⚠️ 停止Playwright时警告：{str(e)}")
            cls._shared_playwright = None

            cls._browser_initialized = False
            logger.info("🔌 全局浏览器实例已关闭")

    # ========== 4. 页面初始化（属性检查+异常防护） ==========
    async def _init_browser_page(self):
        """内部方法：初始化页面（安全防护）"""
        if not self.operator_name:
            raise ValueError("❌ 干员名称不能为空")
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # 初始化上下文（加锁确保安全）
                async with self._lock:
                    context = await self.init_shared_browser()
                    # 检查上下文有效性
                    context_valid = (
                        context 
                        and hasattr(context, 'is_closed') 
                        and not context.is_closed()
                    )
                    if not context_valid:
                        raise Exception("全局上下文无效")

                # 关闭旧页面（安全检查）
                if self.page and hasattr(self.page, 'is_closed') and not self.page.is_closed():
                    await self.page.close()
                self.page = await context.new_page()
                
                # 超时配置
                self.page.set_default_timeout(self.timeouts["page_load"] or 60000)
                self.page.set_default_navigation_timeout(self.timeouts["page_load"] or 60000)
                
                # 加载页面
                await self.page.goto(
                    self.url, 
                    wait_until="load",
                    timeout=60000
                )
                await self.page.wait_for_selector("#mw-content-text", timeout=60000)
                await self.page.wait_for_load_state("networkidle")
                await asyncio.sleep(1)
                logger.info(f"✅ 浏览器页面初始化完成：{self.url}")
                return None
                
            except Exception as e:
                error_msg = str(e).lower()
                # 处理崩溃场景
                if "closed" in error_msg or "crashed" in error_msg or "target" in error_msg:
                    logger.error(f"❌ 浏览器/上下文异常，尝试重启（{attempt+1}/{max_retries}）：{str(e)[:50]}")
                    await self.close_shared_browser()
                    await asyncio.sleep(5)
                
                if attempt == max_retries - 1:
                    raise Exception(f"❌ 页面初始化失败，已重试{max_retries}次: {str(e)}")
                
                logger.warning(f"⚠️ 页面初始化失败，正在重试 ({attempt + 1}/{max_retries}): {str(e)}")
                # 关闭当前页面
                if self.page and hasattr(self.page, 'is_closed') and not self.page.is_closed():
                    await self.page.close()
                self.page = None
                await asyncio.sleep(3)

    # ========== 以下方法保持不变，仅复制原有代码 ==========
    async def _get_soup(self):
        """内部方法：复用soup对象（避免重复解析页面）"""
        if not self.soup and self.page:
            content = await self.page.content()
            self.soup = BeautifulSoup(content, "lxml")
        return self.soup

    async def parse_attrs(self):
        """解析干员属性"""
        await self._get_soup()
        base_attrs = {
            "elite_0_level_1": {},
            "elite_0_max": {},
            "elite_1_max": {},
            "elite_2_max": {},
            "trust_bonus": {}
        }
        base_tbl = self.soup.select_one("table.char-base-attr-table")
        
        if base_tbl:
            headers = [clean_text(th) for th in base_tbl.select("tr:first-child th, tr:first-child td")]
            key_mapping = [
                "elite_0_level_1" if "精英0 1级" in h else
                "elite_0_max" if "精英0 满级" in h else
                "elite_1_max" if "精英1 满级" in h else
                "elite_2_max" if "精英2 满级" in h else
                "trust_bonus" if "信赖加成上限" in h else
                "" for h in headers
            ]
            attr_mapping = {
                "生命上限": "max_hp",
                "攻击": "atk",
                "防御": "def",
                "法术抗性": "res"
            }
            
            for tr in base_tbl.select("tr")[1:]:
                tds = [clean_text(td) for td in tr.select("th, td")]
                if len(tds) < 2:
                    continue
                attr_key = attr_mapping.get(tds[0], tds[0].lower())
                for idx, val in enumerate(tds[1:], 1):
                    if idx < len(key_mapping) and key_mapping[idx]:
                        base_attrs[key_mapping[idx]][attr_key] = val

        extra_attrs = {}
        extra_tbl = self.soup.select_one("table.char-extra-attr-table")
        if extra_tbl:
            extra_key_map = {
                "再部署时间": "redployment_time",
                "初始部署费用": "initial_deployment_cost",
                "攻击间隔": "attack_interval",
                "阻挡数": "block_count",
                "所属势力": "faction",
                "隐藏势力": "hidden_faction"
            }
            for tr in extra_tbl.select("tr"):
                ths = tr.select("th")
                tds = tr.select("td")
                if not ths or not tds:
                    continue
                th_text = clean_text(ths[0])
                th_text = th_text.replace('"', '').replace('“', '').replace('”', '').strip()
                td_text = clean_text(tds[0])
                
                if th_text in extra_key_map:
                    extra_attrs[extra_key_map[th_text]] = td_text
                    logger.debug(
                        f"✅ 解析额外属性：{th_text} → {extra_key_map[th_text]} = {td_text}"
                    )

        logger.debug(f"📋 解析到的额外属性：{extra_attrs}")
        return {
            "base_attributes": base_attrs,
            "extra_attributes": extra_attrs
        } 

    async def parse_chara(self):
        """解析干员特性和分支"""
        await self._get_soup()
        result = {
            "branch_name": "",
            "branch_description": "",
            "trait_details": ""
        }
        trait_tbl = self.soup.select_one("table.wikitable.logo")
        
        if trait_tbl:
            rows = trait_tbl.select("tr")
            if len(rows) > 1:
                tds = rows[1].find_all("td")
                result["branch_name"] = clean_text(tds[0]) if tds else ""
                result["branch_description"] = clean_text(tds[1]) if len(tds) > 1 else ""
            
            branch_row = trait_tbl.find("tr", string=re.compile("分支信息"))
            if branch_row:
                next_row = branch_row.find_next_sibling("tr")
                if next_row:
                    result["trait_details"] = "".join(clean_desc(li) for li in next_row.select("li"))

        return result

    async def parse_talents(self):
        """解析干员天赋"""
        await self._get_soup()
        talents = []
        talent_header = self.soup.find("span", id="天赋")
        if not talent_header:
            logger.debug("⚠️  未找到天赋区域")
            return talents

        def parse_single_talent(table, talent_type: str, span_prefix: str) -> dict:
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
                    continue
                tds = row.find_all("td")
                th = row.find("th")

                if idx == len(rows) - 2 and th:
                    is_remark_section = True
                    continue
                if not tds:
                    continue

                if is_remark_section:
                    remark_text = clean_text(tds[0])
                    break

                current_name = clean_text(tds[0])
                if not talent["talent_name"] and current_name:
                    talent["talent_name"] = current_name

                talent["details"].append({
                    "trigger_condition": clean_text(tds[1]),
                    "description": clean_desc(tds[2].select_one(f"span.{span_prefix}潜能_1")),
                    "potential_enhancement": clean_desc(tds[2].select_one(f"span.{span_prefix}潜能_2"))
                })

            talent["remarks"] = remark_text
            return talent if talent["talent_name"] and talent["details"] else None

        first_talent_tbl = talent_header.find_next("table", class_="wikitable")
        if first_talent_tbl:
            first_talent = parse_single_talent(first_talent_tbl, "第一天赋", "第一天赋")
            if first_talent:
                talents.append(first_talent)

        second_talent_tbl = first_talent_tbl.find_next_sibling("table", class_="wikitable") if first_talent_tbl else None
        if second_talent_tbl:
            second_talent = parse_single_talent(second_talent_tbl, "第二天赋", "第二天赋")
            if second_talent:
                talents.append(second_talent)

        logger.debug(f"📊 解析到天赋数量：{len(talents)}")
        return talents

    async def parse_skills(self):
        """解析干员技能"""
        await self._get_soup()
        skills = []
        skill_header = self.soup.find("span", id="技能")
        
        if not skill_header:
            logger.debug("⚠️  未找到技能区域")
            return skills

        def extract_visible_text(td_elem) -> str:
            visible_parts = []
            for child in td_elem.contents:
                if isinstance(child, str):
                    stripped = child.strip()
                    if stripped:
                        visible_parts.append(stripped)
                elif child.name == "span" and "display:none" not in child.get("style", ""):
                    span_text = clean_text(child)
                    if span_text:
                        visible_parts.append(span_text)
            return " ".join(visible_parts)

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
                if not tds:
                    continue

                if idx == 0:
                    if len(tds) >= 2:
                        big_tag = tds[1].find("big")
                        skill["skill_name"] = clean_text(big_tag) if big_tag else clean_text(tds[1])
                    if len(tds) >= 3:
                        tooltip_spans = tds[2].find_all("span", class_="mc-tooltips")
                        skill["skill_type"] = "|".join([clean_text(span) for span in tooltip_spans])
                    continue

                if idx == 8 or idx == 11:
                    if len(tds) >= 5:
                        skill["skill_levels"].append({
                            "level": clean_text(tds[0]),
                            "description": extract_visible_text(tds[1]),
                            "initial_sp": clean_text(tds[2]),
                            "sp_cost": clean_text(tds[3]),
                            "duration": clean_text(tds[4])
                        })
                    continue

                if idx == len(rows) - 2 and row.find("th"):
                    is_remark = True
                    continue
                if is_remark:
                    skill["remark"] = clean_text(tds[0])
                    break

            return skill

        skill_h2 = skill_header.find_parent("h2")
        if not skill_h2:
            logger.debug("⚠️  未找到技能区域的H2标签，跳过技能解析")
            return skills
        
        skill_no = skill_h2.find_next_sibling("p")
        skill_tables = []

        for i in range(1, 4):
            if not skill_no:
                logger.debug(f"⚠️  未找到第{i}个技能表格的锚点P标签，终止查找")
                break

            if clean_text(skill_no).find("技能") > -1:
                current_table = skill_no.find_next_sibling("table")
                if current_table and all(cls in current_table.get("class", []) for cls in ["wikitable", "nomobile", "logo"]):
                    skill_tables.append(current_table)
                    logger.debug(f"✅ 找到第{i}个技能表格")
                    skill_no = skill_no.find_next_sibling("p")
                else:
                    logger.debug(f"⚠️  第{i}个技能表格class不匹配，跳过")
                    skill_no = skill_no.find_next_sibling("p")
            else:
                logger.debug(f"⚠️  第{i}个技能表格的P标签不含“技能”，终止查找")
                break

        logger.debug(f"📊 技能表格查找完成：共找到 {len(skill_tables)} 个有效表格")

        for idx, table in enumerate(skill_tables, 1):
            skill = parse_single_skill(table, idx)
            if skill["skill_name"]:
                skills.append(skill)
                logger.debug(f"✅ 解析技能{idx}：{skill['skill_name']}")

        logger.debug(f"📊 解析到技能数量：{len(skills)}")
        return skills

    async def parse_terms(self):
        """解析干员相关术语"""
        await self._get_soup()
        terms = []
        term_seen = set()
        total_success = 0
        total_failed = 0

        try:
            content_div = self.soup.find("div", id="mw-content-text")
            if not content_div:
                logger.warning("⚠️  未找到核心内容区，跳过术语提取")
                return terms

            term_tags = content_div.find_all(
                lambda tag: tag.name == "span"
                and tag.get("class")
                and any("mc-tooltips" in c for c in tag.get("class"))
                and len(clean_text(tag).strip()) >= self.term_min_length
                and not clean_text(tag).strip().isdigit()
            )
            total_terms = len(term_tags)
            logger.info(f"\n🔍 术语提取开始：共找到 {total_terms} 个有效潜在术语标签")
            if total_terms == 0:
                return terms

            try:
                await self.page.evaluate("() => document.title")
            except Exception as e:
                logger.error(f"❌ 页面状态检查失败，跳过术语提取：{str(e)[:50]}")
                return terms

            max_terms = min(total_terms, 20)
            processed_terms = 0

            for idx, term_tag in enumerate(term_tags, 1):
                if processed_terms >= max_terms:
                    logger.info(f"⏭️ 已达到最大处理数量 {max_terms}，停止处理")
                    break
                    
                term_name = clean_text(term_tag).strip()
                if not term_name or term_name in term_seen:
                    logger.info(f"⏭️  术语{idx}/{total_terms}：跳过（重复/无效）→ 名称：{term_name}")
                    continue

                try:
                    class_list = term_tag.get("class", [])
                    valid_classes = [c for c in class_list if "mc-tooltips" in c]
                    if not valid_classes:
                        logger.info(f"⏭️  术语{idx}/{total_terms}：跳过（无有效class）→ 名称：{term_name}")
                        total_failed += 1
                        continue

                    term_class = valid_classes[0]
                    safe_name = term_name.replace("'", "\\'").replace('"', '\\"').replace("\\", "\\\\")
                    css_selector = f"span.{term_class}:has-text('{safe_name}')"
                    locator = self.page.locator(css_selector).first

                    match_count = await self.page.locator(css_selector).count()
                    if match_count > 1:
                        logger.debug(f"⚠️  术语{term_name}匹配{match_count}个元素，取第一个")
                        logger.info(f"⚠️  术语{idx}/{total_terms}：定位器匹配{match_count}个元素 → 名称：{term_name}")

                    await locator.wait_for(state="visible", timeout=self.timeouts["locator_wait"] or 10000)
                    await locator.scroll_into_view_if_needed()
                    await locator.hover(force=True)
                    await asyncio.sleep(self.wait_times["tooltip_render"] or 0.5)

                    term_type = "无"
                    term_desc = ""
                    tip_found = False

                    for tip_selector in self.tooltip_selectors:
                        tip_locator = self.page.locator(tip_selector).first
                        if await tip_locator.count() > 0:
                            tip_found = True
                            strong_handles = await tip_locator.locator("strong").all()
                            strong_texts = []
                            for handle in strong_handles:
                                text = await handle.inner_text(timeout=self.timeouts["text_extract"] or 5000)
                                clean_text_val = text.strip().split(":")[0].rstrip("：:")
                                if clean_text_val:
                                    strong_texts.append(clean_text_val)
                            term_type = "，".join(strong_texts) if strong_texts else "无"
                            if term_type == term_name:
                                term_type = "无"

                            content_handles = await tip_locator.locator(":not(strong)").all()
                            content_parts = []
                            for handle in content_handles:
                                text = await handle.inner_text(timeout=self.timeouts["text_extract"] or 5000)
                                clean_text_val = text.strip()
                                if clean_text_val:
                                    content_parts.append(clean_text_val)
                            term_desc = "\n".join(content_parts) if content_parts else ""

                            if not term_desc:
                                full_text = await tip_locator.inner_text(timeout=self.timeouts["text_extract"] or 5000)
                                if term_type != "无":
                                    full_text = full_text.replace(f"{term_type}：", "").replace(f"{term_type}:", "").replace(term_type, "")
                                term_desc = full_text.strip()
                            break

                    if not tip_found:
                        logger.info(f"❌ 术语{idx}/{total_terms}：失败（未找到提示框）→ 名称：{term_name}")
                        total_failed += 1
                        continue

                    formatted_desc = re.sub(r"\s+", "\n", term_desc).strip()
                    if len(formatted_desc) < self.desc_min_length:
                        logger.info(f"⏭️  术语{idx}/{total_terms}：跳过（描述过短）→ 名称：{term_name}")
                        total_failed += 1
                        continue

                    if term_name not in term_seen:
                        terms.append({
                            "term_name": term_name,
                            "term_type": term_type,
                            "term_description": formatted_desc
                        })
                        term_seen.add(term_name)
                        total_success += 1
                        logger.info(f"✅ 术语{idx}/{total_terms}：成功 → 名称：{term_name} | 类型：{term_type} | 描述长度：{len(formatted_desc)}字")

                    processed_terms += 1

                    try:
                        await self.page.mouse.move(100, 100)
                        await asyncio.sleep(0.1)
                    except Exception as e:
                        logger.warning(f"⚠️ 鼠标移动失败，继续下一个术语: {str(e)[:30]}")

                except PlaywrightTimeoutError:
                    logger.info(f"❌ 术语{idx}/{total_terms}：失败（超时）→ 名称：{term_name}")
                    total_failed += 1
                    processed_terms += 1
                    continue
                except AttributeError as e:
                    logger.info(f"❌ 术语{idx}/{total_terms}：失败（属性错误）→ 名称：{term_name} | 错误：{str(e)[:50]}")
                    total_failed += 1
                    processed_terms += 1
                    continue
                except Exception as e:
                    error_msg = str(e).lower()
                    if "crashed" in error_msg or "target crashed" in error_msg:
                        logger.error(f"❌ 页面崩溃，停止术语提取：{str(e)[:50]}")
                        break
                    logger.info(f"❌ 术语{idx}/{total_terms}：失败（未知错误）→ 名称：{term_name} | 错误：{str(e)[:50]}")
                    total_failed += 1
                    processed_terms += 1
                    continue

        except Exception as e:
            logger.error(f"❌ 术语提取主流程错误：{str(e)}")

        unique_terms = []
        final_seen = set()
        for term in terms:
            if term["term_name"] not in final_seen:
                final_seen.add(term["term_name"])
                unique_terms.append(term)

        logger.info(f"\n📊 术语提取完成：总计{total_terms}个有效潜在术语 → 成功{total_success}个 | 失败{total_failed}个 | 去重后{len(unique_terms)}个")
        return unique_terms

    async def parse_all(self):
        """整合所有解析结果"""
        return {
            "operator_name": self.operator_name,
            "metadata": {
                "last_updated": datetime.now().isoformat(),
                "source": self.url,
                "version": "v10.0",
                "parser_config": {
                    "headless": self.headless,
                    "term_min_length": self.term_min_length,
                    "desc_min_length": self.desc_min_length
                }
            },
            "characteristic": await self.parse_chara(),
            "attributes": await self.parse_attrs(),
            "talents": await self.parse_talents(),
            "skills": await self.parse_skills(),
            "terms": await self.parse_terms()
        }

    async def save(self, result: dict):
        """保存干员详情到JSON"""
        ensure_output_dir()
        safe_filename = clean_filename(self.operator_name)
        output_path = f"{JSON_OUTPUT_DIR}/{safe_filename}.json"
        try:
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            logger.info(f"✅ 成功保存干员详情: {output_path}")
        except IOError as e:
            logger.error(f"❌ 保存文件失败：{str(e)}")

    async def run(self):
        """一键执行：初始化→解析→保存"""
        if not self.operator_name:
            logger.error("❌ 干员名称为空，无法解析")
            return None

        logger.info(f"=== 开始爬取干员: {self.operator_name} ({self.url}) ===")
        try:
            await self._init_browser_page()
            result = await self.parse_all()
            # await self.save(result)

            logger.info("\n=== 解析结果汇总 ===")
            logger.info(f"干员名称: {result['operator_name']}")
            logger.info(f"分支名称: {result['characteristic']['branch_name']}")
            logger.info(f"天赋数量: {len(result['talents'])}")
            logger.info(f"技能数量: {len(result['skills'])}")
            logger.info(f"术语数量: {len(result['terms'])}")
            logger.info("====================")

            return result
        except PlaywrightTimeoutError:
            logger.error(f"❌ 页面加载超时（{self.timeouts['page_load']/1000}秒）")
            return None
        except Exception as e:
            logger.error(f"❌ 解析错误：{str(e)[:100]}")
            return None
        finally:
            # 安全关闭页面
            if self.page and hasattr(self.page, 'is_closed') and not self.page.is_closed():
                await self.page.close()
                self.page = None
                logger.info("🔌 浏览器页面已关闭（浏览器实例复用）")

if __name__ == "__main__":
    import sys
    operator_name = "焰影苇草" if len(sys.argv) < 2 else sys.argv[1]
    
    async def main():
        try:
            parser = OperatorDetailParser(operator_name)
            await parser.init_shared_browser()
            await parser.run()
        finally:
            await OperatorDetailParser.close_shared_browser()
    
    asyncio.run(main())