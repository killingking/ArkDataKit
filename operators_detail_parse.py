import asyncio
import json
import re
from datetime import datetime
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup
from config import BASE_URL, PLAYWRIGHT_CONFIG, JSON_OUTPUT_DIR  # 补充JSON_OUTPUT_DIR导入
from utils import logger, clean_text, clean_desc, clean_filename, ensure_output_dir

class OperatorDetailParser:
    """干员详情解析器（有状态类封装，维护page/soup）"""
    # ========== 关键修改1：新增全局复用的浏览器/上下文 ==========
    _shared_playwright = None
    _shared_browser = None
    _shared_context = None
    _browser_initialized = False

    # ========== 关键修改2：类方法初始化全局浏览器（只创建1次） ==========
    @classmethod
    async def init_shared_browser(cls):
        """初始化全局复用的浏览器实例（批量爬取时只创建1次）"""
        if cls._browser_initialized:
            return cls._shared_context

        try:
            cls._shared_playwright = await async_playwright().start()
            # 优化浏览器启动参数：禁用沙箱、限制内存、绕过/dev/shm
            browser_args = PLAYWRIGHT_CONFIG["browser_args"] + [
                "--no-sandbox",          # 解决小内存服务器崩溃
                "--disable-gpu",         # 禁用GPU加速
                "--disable-dev-shm-usage",# 绕过共享内存限制
                "--disk-cache-dir=/tmp/playwright-cache",  # 指定缓存目录
                "--max-old-space-size=512",  # 限制Chrome内存（512M）
                "--memory-pressure-off"  # 关闭内存压力检测
            ]
            # 启动浏览器（复用核心）
            cls._shared_browser = await cls._shared_playwright.chromium.launch(
                headless=PLAYWRIGHT_CONFIG["headless"],
                args=browser_args,
                timeout=60000  # 浏览器启动超时延长到60秒
            )
            # 创建复用的上下文
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

    # ========== 关键修改3：类方法关闭全局浏览器（批量结束后调用） ==========
    @classmethod
    async def close_shared_browser(cls):
        """关闭全局浏览器实例（批量爬取结束后执行）"""
        if cls._shared_context:
            await cls._shared_context.close()
        if cls._shared_browser:
            await cls._shared_browser.close()
        if cls._shared_playwright:
            await cls._shared_playwright.stop()
        cls._browser_initialized = False
        cls._shared_playwright = None
        cls._shared_browser = None
        cls._shared_context = None
        logger.info("🔌 全局浏览器实例已关闭")

    def __init__(self, operator_name: str):
        # 初始化配置和状态
        self.operator_name = operator_name.strip()
        self.url = f"{BASE_URL}/w/{self.operator_name}" if self.operator_name else ""
        self.page = None  # Playwright页面对象（状态）
        self.soup = None  # BeautifulSoup对象（状态）
        
        # 从统一配置读取参数
        self.term_min_length = PLAYWRIGHT_CONFIG["term_filter"]["min_length"]
        self.desc_min_length = PLAYWRIGHT_CONFIG["term_filter"]["desc_min_length"]
        self.tooltip_selectors = PLAYWRIGHT_CONFIG["tooltip_selectors"]
        self.wait_times = PLAYWRIGHT_CONFIG["wait_time"]
        self.timeouts = PLAYWRIGHT_CONFIG["timeout"]
        # 原有browser_args保留（但实际用全局的）
        self.browser_args = PLAYWRIGHT_CONFIG["browser_args"]
        self.headless = PLAYWRIGHT_CONFIG["headless"]

    # ========== 关键修改4：重构_init_browser_page，复用全局浏览器 ==========
    async def _init_browser_page(self):
        """内部方法：初始化页面（复用全局浏览器，只新建page）"""
        if not self.operator_name:
            raise ValueError("❌ 干员名称不能为空")
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # 复用全局浏览器上下文，不再新建browser
                context = await self.init_shared_browser()
                self.page = await context.new_page()
                
                # 优化超时配置
                self.page.set_default_timeout(self.timeouts["page_load"] or 60000)  # 至少60秒
                self.page.set_default_navigation_timeout(self.timeouts["page_load"] or 60000)
                
                # 加载页面：改为wait_until="load"（完全加载）+ 延长超时
                await self.page.goto(
                    self.url, 
                    wait_until="load",  # 关键：从domcontentloaded改为load
                    timeout=60000       # 页面加载超时延长到60秒
                )
                # 等待核心内容+网络空闲（解决动态内容加载不全）
                await self.page.wait_for_selector("#mw-content-text", timeout=60000)
                await self.page.wait_for_load_state("networkidle")  # 等待网络空闲
                await asyncio.sleep(1)  # 额外等待1秒
                logger.info(f"✅ 浏览器页面初始化完成：{self.url}")
                return None  # 不再返回browser（全局复用）
                
            except Exception as e:
                if attempt == max_retries - 1:
                    raise Exception(f"❌ 页面初始化失败，已重试{max_retries}次: {str(e)}")
                
                logger.warning(f"⚠️ 页面初始化失败，正在重试 ({attempt + 1}/{max_retries}): {str(e)}")
                # 失败时关闭当前page，避免泄漏
                if self.page:
                    await self.page.close()
                    self.page = None
                await asyncio.sleep(3)  # 重试间隔延长到3秒

    async def _get_soup(self):
        """内部方法：复用soup对象（避免重复解析页面）"""
        if not self.soup and self.page:
            content = await self.page.content()
            self.soup = BeautifulSoup(content, "lxml")
        return self.soup

    async def parse_attrs(self):
        """解析干员属性（基础属性+额外属性）—— 精准适配hidden_faction结构"""
        await self._get_soup()
        # 初始化基础属性结构（原有逻辑保留，无需修改）
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
            attr_mapping = {"生命上限": "max_hp", "攻击": "atk", "防御": "def", "法术抗性": "res"}
            
            for tr in base_tbl.select("tr")[1:]:
                tds = [clean_text(td) for td in tr.select("th, td")]
                if len(tds) < 2:
                    continue
                attr_key = attr_mapping.get(tds[0], tds[0].lower())
                for idx, val in enumerate(tds[1:], 1):
                    if idx < len(key_mapping) and key_mapping[idx]:
                        base_attrs[key_mapping[idx]][attr_key] = val

        # ========== 重点修复：额外属性解析（适配hidden_faction结构） ==========
        extra_attrs = {}
        # 1. 兼容多种额外属性表格选择器
        extra_tbl = self.soup.select_one("table.char-extra-attr-table") or self.soup.select_one("table.wikitable.char-extra-attr")
        if not extra_tbl:
            logger.warning("⚠️ 未找到额外属性表格，跳过额外属性解析")
            return {"base_attributes": base_attrs, "extra_attributes": extra_attrs}

        # 2. 自定义工具函数：提取标签内的纯文本（忽略嵌套span/链接）
        def get_pure_text(elem) -> str:
            """提取元素内的所有可见文本（合并a标签/过滤span图标）"""
            if not elem:
                return ""
            # 先移除图标类span（避免干扰文本）
            for span in elem.find_all("span", class_=["mc-tooltips", "mdi"]):
                span.extract()
            # 提取所有文本（包括a标签内的文本）
            text_parts = [text.strip() for text in elem.stripped_strings if text.strip()]
            return "".join(text_parts)

        # 3. 逐行解析（适配colspan和嵌套标签）
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
                continue  # 跳过无表头/无内容的行

            # 提取<th>的纯文本（移除嵌套的span图标）
            th_text = get_pure_text(ths[0])
            if not th_text:
                continue

            # 匹配目标字段（模糊匹配，只要th文本包含key就绑定）
            matched_field = None
            for map_key, field in extra_key_map.items():
                if map_key in th_text:
                    matched_field = field
                    break
            if not matched_field:
                continue

            # 提取<td>的纯文本（适配colspan=3的情况）
            td_text = get_pure_text(tds[0])
            if td_text:
                extra_attrs[matched_field] = td_text
                logger.debug(f"✅ 解析额外属性：{th_text} → {matched_field} = {td_text}")

        logger.debug(f"📋 解析到的额外属性：{extra_attrs}")
        return {"base_attributes": base_attrs, "extra_attributes": extra_attrs}

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
            # 解析分支名称和描述
            if len(rows) > 1:
                tds = rows[1].find_all("td")
                result["branch_name"] = clean_text(tds[0]) if tds else ""
                result["branch_description"] = clean_text(tds[1]) if len(tds) > 1 else ""
            
            # 解析分支详情
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
            """提取单个天赋（内部工具函数）"""
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
                    remark_text = clean_text(tds[0])
                    break

                # 提取天赋名称（仅首次赋值）
                current_name = clean_text(tds[0])
                if not talent["talent_name"] and current_name:
                    talent["talent_name"] = current_name

                # 提取天赋详情
                talent["details"].append({
                    "trigger_condition": clean_text(tds[1]),
                    "description": clean_desc(tds[2].select_one(f"span.{span_prefix}潜能_1")),
                    "potential_enhancement": clean_desc(tds[2].select_one(f"span.{span_prefix}潜能_2"))
                })

            talent["remarks"] = remark_text
            return talent if talent["talent_name"] and talent["details"] else None

        # 解析第一天赋
        first_talent_tbl = talent_header.find_next("table", class_="wikitable")
        if first_talent_tbl:
            first_talent = parse_single_talent(first_talent_tbl, "第一天赋", "第一天赋")
            if first_talent:
                talents.append(first_talent)

        # 解析第二天赋
        second_talent_tbl = first_talent_tbl.find_next_sibling("table", class_="wikitable") if first_talent_tbl else None
        if second_talent_tbl:
            second_talent = parse_single_talent(second_talent_tbl, "第二天赋", "第二天赋")
            if second_talent:
                talents.append(second_talent)

        logger.debug(f"📊 解析到天赋数量：{len(talents)}")
        return talents

    async def parse_skills(self):
        """解析干员技能（还原你最初的简洁逻辑，只做最小修复）"""
        await self._get_soup()
        skills = []
        skill_header = self.soup.find("span", id="技能")
        
        if not skill_header:
            logger.debug("⚠️  未找到技能区域")
            return skills

        # 提取可见文本（保持你原来的简洁）
        def extract_visible_text(td_elem) -> str:
            visible_parts = []
            for child in td_elem.contents:
                if isinstance(child, str):
                    stripped = child.strip()
                    if stripped:
                        visible_parts.append(stripped)
                elif child.name == "span" and "display:none" not in child.get("style", ""):
                    span_text = clean_text(child)  # 只用clean_text兼容
                    if span_text:
                        visible_parts.append(span_text)
            return " ".join(visible_parts)

        # 解析单个技能（保持你原来的简洁，只加索引防护）
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
                if not tds:  # 最小防护：空tds直接跳过
                    continue

                if idx == 0:
                    # 最小防护：确保索引不越界
                    if len(tds) >= 2:
                        big_tag = tds[1].find("big")
                        skill["skill_name"] = clean_text(big_tag) if big_tag else clean_text(tds[1])
                    if len(tds) >= 3:
                        tooltip_spans = tds[2].find_all("span", class_="mc-tooltips")
                        skill["skill_type"] = "|".join([clean_text(span) for span in tooltip_spans])
                    continue

                # 提取关键等级（7级和专精3）
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

                # 识别备注行
                if idx == len(rows) - 2 and row.find("th"):
                    is_remark = True
                    continue
                if is_remark:
                    skill["remark"] = clean_text(tds[0])
                    break

            return skill

        # ========== 还原你最初的写死3次循环（只修1个问题） ==========
        current_table = skill_header.find_parent("h2").find_next_sibling("table")
        skill_tables = []
        for _ in range(3):
            # 修复：放宽表格class判断（只需要wikitable，不强制nomobile logo）
            if current_table and "wikitable" in current_table.get("class", []):
                skill_tables.append(current_table)
                logger.debug(f"✅ 找到第{len(skill_tables)}个技能表格")
                # 修复：下一个表格也放宽class判断
                current_table = current_table.find_next_sibling("table", class_=lambda c: c and "wikitable" in c)
            else:
                logger.debug(f"⚠️  未找到第{len(skill_tables)+1}个技能表格")
                break

        # 解析技能（保持简洁）
        for idx, table in enumerate(skill_tables, 1):
            skill = parse_single_skill(table, idx)
            if skill["skill_name"]:
                skills.append(skill)
                logger.debug(f"✅ 解析技能{idx}：{skill['skill_name']}")

        logger.debug(f"📊 解析到技能数量：{len(skills)}")
        return skills

    # ========== 关键修改5：优化术语提取，减少资源消耗 ==========
    async def parse_terms(self):
        """解析干员相关术语（优化：限制数量、提前检测崩溃）"""
        await self._get_soup()
        terms = []
        term_seen = set()
        total_success = 0
        total_failed = 0

        try:
            # 1. 定位核心内容区
            content_div = self.soup.find("div", id="mw-content-text")
            if not content_div:
                logger.warning("⚠️  未找到核心内容区，跳过术语提取")
                return terms

            # 2. 筛选有效术语标签
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

            # 3. 检查页面状态，如果页面已崩溃则提前退出
            try:
                await self.page.evaluate("() => document.title")
            except Exception as e:
                logger.error("❌ 页面已崩溃，无法进行术语提取")
                return terms

            # 4. 限制最大处理数量（从50降到20，减少资源消耗）
            max_terms = min(total_terms, 20)  # 关键：限制最多处理20个
            processed_terms = 0

            # 5. 逐个处理术语
            for idx, term_tag in enumerate(term_tags, 1):
                if processed_terms >= max_terms:
                    logger.info(f"⏭️ 已达到最大处理数量 {max_terms}，停止处理")
                    break
                    
                term_name = clean_text(term_tag).strip()
                # 跳过重复或无效术语
                if not term_name or term_name in term_seen:
                    logger.info(f"⏭️  术语{idx}/{total_terms}：跳过（重复/无效）→ 名称：{term_name}")
                    continue

                try:
                    # 3.1 构建CSS定位器
                    class_list = term_tag.get("class", [])
                    valid_classes = [c for c in class_list if "mc-tooltips" in c]
                    if not valid_classes:
                        logger.info(f"⏭️  术语{idx}/{total_terms}：跳过（无有效class）→ 名称：{term_name}")
                        total_failed += 1
                        continue

                    term_class = valid_classes[0]
                    # 处理特殊字符
                    safe_name = term_name.replace("'", "\\'").replace('"', '\\"').replace("\\", "\\\\")
                    css_selector = f"span.{term_class}:has-text('{safe_name}')"
                    locator = self.page.locator(css_selector).first

                    # 调试：打印匹配数量
                    match_count = await self.page.locator(css_selector).count()
                    if match_count > 1:
                        logger.debug(f"⚠️  术语{term_name}匹配{match_count}个元素，取第一个")
                        logger.info(f"⚠️  术语{idx}/{total_terms}：定位器匹配{match_count}个元素，已取第一个 → 名称：{term_name}")

                    # 3.2 悬浮触发提示框（缩短等待时间）
                    await locator.wait_for(state="visible", timeout=self.timeouts["locator_wait"] or 10000)
                    await locator.scroll_into_view_if_needed()
                    await locator.hover(force=True)
                    await asyncio.sleep(self.wait_times["tooltip_render"] or 0.5)  # 缩短到0.5秒

                    # 3.3 提取提示框内容
                    term_type = "无"
                    term_desc = ""
                    tip_found = False

                    for tip_selector in self.tooltip_selectors:
                        tip_locator = self.page.locator(tip_selector).first
                        if await tip_locator.count() > 0:
                            tip_found = True
                            # 提取<strong>内容（术语类型）
                            strong_handles = await tip_locator.locator("strong").all()
                            strong_texts = []
                            for handle in strong_handles:
                                text = await handle.inner_text(timeout=self.timeouts["text_extract"] or 5000)
                                clean_text_val = text.strip().split(":")[0].rstrip("：:")
                                if clean_text_val:
                                    strong_texts.append(clean_text_val)
                            term_type = "，".join(strong_texts) if strong_texts else "无"
                            # 避免类型与名称重复
                            if term_type == term_name:
                                term_type = "无"

                            # 提取正文（排除strong）
                            content_handles = await tip_locator.locator(":not(strong)").all()
                            content_parts = []
                            for handle in content_handles:
                                text = await handle.inner_text(timeout=self.timeouts["text_extract"] or 5000)
                                clean_text_val = text.strip()
                                if clean_text_val:
                                    content_parts.append(clean_text_val)
                            term_desc = "\n".join(content_parts) if content_parts else ""

                            # 正文为空时取完整文本
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

                    # 3.4 过滤无效描述
                    formatted_desc = re.sub(r"\s+", "\n", term_desc).strip()
                    if len(formatted_desc) < self.desc_min_length:
                        logger.info(f"⏭️  术语{idx}/{total_terms}：跳过（描述过短）→ 名称：{term_name}")
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
                        logger.info(f"✅ 术语{idx}/{total_terms}：成功 → 名称：{term_name} | 类型：{term_type} | 描述长度：{len(formatted_desc)}字")

                    processed_terms += 1

                    # 3.6 清理状态（简化，减少资源占用）
                    try:
                        await self.page.mouse.move(100, 100)
                        await asyncio.sleep(0.1)  # 缩短到0.1秒
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
                        break  # 页面崩溃时立即退出
                    logger.info(f"❌ 术语{idx}/{total_terms}：失败（未知错误）→ 名称：{term_name} | 错误：{str(e)[:50]}")
                    total_failed += 1
                    processed_terms += 1
                    continue

        except Exception as e:
            logger.error(f"❌ 术语提取主流程错误：{str(e)}")

        # 最终去重（双重保障）
        unique_terms = []
        final_seen = set()
        for term in terms:
            if term["term_name"] not in final_seen:
                final_seen.add(term["term_name"])
                unique_terms.append(term)

        # 打印统计报告
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

    # ========== 关键修改6：重构run方法，优化资源释放 ==========
    async def run(self):
        """一键执行：初始化→解析→保存（优化资源释放）"""
        if not self.operator_name:
            logger.error("❌ 干员名称为空，无法解析")
            return None

        logger.info(f"=== 开始爬取干员: {self.operator_name} ({self.url}) ===")
        try:
            # 初始化页面（复用全局浏览器）
            await self._init_browser_page()
            # 执行解析
            result = await self.parse_all()
            # 保存结果（注释保留）
            # await self.save(result)

            # 打印调试信息
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
            # ========== 关键：只关闭page，不关闭browser（全局复用） ==========
            if self.page:
                await self.page.close()
                self.page = None
                logger.info("🔌 浏览器页面已关闭（浏览器实例复用）")

# 保留独立执行入口（方便单独调试）
if __name__ == "__main__":
    import sys
    operator_name = "焰影苇草" if len(sys.argv) < 2 else sys.argv[1]
    # 独立运行时手动管理全局浏览器
    async def main():
        try:
            parser = OperatorDetailParser(operator_name)
            await parser.init_shared_browser()
            await parser.run()
        finally:
            await OperatorDetailParser.close_shared_browser()
    
    asyncio.run(main())