import asyncio
from terms_parse import TermStaticCrawler
from operators_list_get import OperatorListCrawler
from operators_detail_parse import OperatorDetailParser
from db_handler import DBHandler
from utils import logger

def sync_terms_to_db():
    """静态术语爬取→入库"""
    logger.info("===== 开始同步静态术语 =====")
    db = DBHandler()
    
    try:
        crawler = TermStaticCrawler()
        terms = crawler.run()
        if not terms:
            logger.warning("⚠️ 无有效术语，跳过入库")
            return
            
        if not db.connect():
            logger.error("❌ 数据库连接失败，跳过入库")
            return
            
        if db.count_global_terms() >= len(terms):
            logger.warning("⚠️ 术语已存在，跳过入库")
            return
            
        db.insert_global_terms(terms)
        logger.info(f"✅ 成功入库 {len(terms)} 条术语")
        
    except Exception as e:
        logger.error(f"❌ 术语同步过程中发生错误: {str(e)}", exc_info=True)
    finally:
        db.close()        

def sync_operator_list_to_db():
    """干员一览爬取→批量入库"""
    logger.info("===== 开始同步干员一览数据 =====")
    db = DBHandler()
    
    try:
        crawler = OperatorListCrawler()
        ops_list = crawler.run()
        if not ops_list:
            logger.warning("⚠️ 无有效干员一览数据，跳过入库")
            return
            
        if not db.connect():
            logger.error("❌ 数据库连接失败，跳过入库")
            return

        if db.count_operators() >= len(ops_list):
            logger.warning("⚠️ 无新增干员，跳过入库")
            return
        db.batch_insert_operator_base(ops_list)
        logger.info(f"✅ 成功入库 {len(ops_list)} 条干员基础信息")
        
    except Exception as e:
        logger.error(f"❌ 干员一览同步过程中发生错误: {str(e)}", exc_info=True)
    finally:
        db.close()

async def sync_operator_detail_to_db(db: DBHandler, operator_name: str):
    """干员详情解析→入库（复用外部DB连接，修复字段取值+容错+资源释放）"""
    logger.info(f"===== 开始同步干员 {operator_name} 详情 =====")
    if not db or not db.connection or not db.connection.is_connected():
        logger.error(f"❌ 数据库未连接，干员 {operator_name} 跳过入库")
        return False  # 返回执行结果，方便统计
    
    parser = None
    try:
        # 解析干员详情
        parser = OperatorDetailParser(operator_name)
        operator_data = await parser.run()
        if not operator_data:
            logger.warning(f"⚠️ 干员 {operator_name} 解析失败，跳过入库")
            return False
        
        # ========== 原有核心字段验证+入库逻辑（不变） ==========
        # 核心字段验证
        if "operator_name" not in operator_data or "attributes" not in operator_data:
            logger.error(f"❌ 干员 {operator_name} 缺少核心字段，跳过入库")
            return False
        
        # 整理入库数据（增加容错）
        characteristic = operator_data.get("characteristic", {}) or {}
        attributes = operator_data.get("attributes", {}) or {}
        extra_attributes = attributes.get("extra_attributes", {}) or {}
        base_attributes = attributes.get("base_attributes", {}) or {}
        
        base_info = {
            "name_cn": operator_data["operator_name"].strip(),
            "sub_profession": characteristic.get("branch_name", ""),
            # "faction": extra_attributes.get("faction", ""),
            "hidden_faction": extra_attributes.get("hidden_faction", ""),
            "branch_description": characteristic.get("branch_description", ""),
            "trait_details": characteristic.get("trait_details", ""),
            "redployment_time": extra_attributes.get("redployment_time", ""),
            "initial_deployment_cost": extra_attributes.get("initial_deployment_cost", ""),
            "block_count": extra_attributes.get("block_count", ""),
            "attack_interval": extra_attributes.get("attack_interval", "")
        }
        
        # 构造属性列表
        attr_list = []
        if isinstance(base_attributes, dict):
            for attr_type, attr_values in base_attributes.items():
                attr_values = attr_values or {}
                attr_list.append({
                    "attr_type": attr_type,
                    "max_hp": attr_values.get("max_hp", ""),
                    "atk": attr_values.get("atk", ""),
                    "def": attr_values.get("def", ""),
                    "res": attr_values.get("res", "")
                })
        
        # 执行入库操作 - 为每个操作创建独立连接，避免连接失效
        success = True
        
        # 定义数据库操作列表
        operations = []
        
        # 基础信息更新操作
        def update_base_info(op_db):
            update_ok = op_db.update_operator_base(base_info)
            if not update_ok:
                logger.warning(f"⚠️ 干员 {operator_name} 基础信息更新失败（可能不存在），尝试插入")
                op_db.insert_operator_base(base_info)
            return True
        operations.append(("基础信息", update_base_info))
        
        # 属性插入操作
        if attr_list:
            operations.append(("属性", lambda op_db: op_db.insert_operator_attr(operator_name, attr_list)))
        
        # 天赋插入操作
        if "talents" in operator_data and operator_data["talents"]:
            operations.append(("天赋", lambda op_db: op_db.insert_operator_talent(operator_name, operator_data["talents"])))
        
        # 技能插入操作
        if "skills" in operator_data and operator_data["skills"]:
            operations.append(("技能", lambda op_db: op_db.insert_operator_skill(operator_name, operator_data["skills"])))
        
        # 术语关联操作
        if "terms" in operator_data and operator_data["terms"]:
            term_relations = [
                {"term_name": t.get("term_name", "").strip(), "relation_module": "", "module_id": ""} 
                for t in operator_data["terms"] if t.get("term_name") and t.get("term_name").strip()
            ]
            if term_relations:
                operations.append(("术语关联", lambda op_db: op_db.insert_operator_term_relation(operator_name, term_relations)))
        
        # 执行所有操作
        for op_name, op_func in operations:
            op_db = None
            try:
                op_db = DBHandler()
                if not op_db.connect():
                    logger.error(f"❌ 数据库连接失败，跳过{op_name}操作")
                    success = False
                    continue
                    
                result = op_func(op_db)
                if result is False:
                    logger.error(f"❌ {op_name}操作失败")
                    success = False
                else:
                    logger.debug(f"✅ {op_name}操作成功")
                    
            except Exception as e:
                logger.error(f"❌ {op_name}操作异常: {str(e)[:100]}")
                success = False
            finally:
                if op_db:
                    op_db.close()
                
        if success:
            logger.info(f"✅ 干员 {operator_name} 详情同步完成")
        else:
            logger.warning(f"⚠️ 干员 {operator_name} 部分字段同步失败")
        return success
        
    except Exception as e:
        logger.error(f"❌ 干员 {operator_name} 详情同步过程中发生错误: {str(e)}", exc_info=True)
        return False
    finally:
        # 关键：强制关闭当前页面，释放资源（即使解析失败）
        if parser and parser.page and not parser.page.is_closed():
            try:
                await parser.page.close()
            except Exception as e:
                logger.warning(f"⚠️ 关闭干员 {operator_name} 页面时警告：{str(e)}")

# 批量同步多个干员（复用DB连接，优化性能）
# main.py 中批量同步函数
async def batch_sync_operators(db: DBHandler, operator_names: list[str]):
    """批量同步多个干员详情（整合全局浏览器复用+崩溃恢复+延迟优化）"""
    if not operator_names:
        logger.warning("⚠️ 干员名称列表为空，跳过批量同步")
        return 0
    
    # ========== 初始化全局浏览器（提前创建，避免首次爬取时初始化） ==========
    try:
        await OperatorDetailParser.init_shared_browser()
    except Exception as e:
        logger.error(f"❌ 全局浏览器初始化失败，批量同步终止：{str(e)}")
        return 0
    
    # ========== 数据库长连接检查 ==========
    if not db.connect():
        await OperatorDetailParser.close_shared_browser()
        return 0
    
    logger.info(f"===== 开始批量同步 {len(operator_names)} 个干员详情 =====")
    success_count = 0
    valid_names = [name.strip() for name in operator_names if name and name.strip()]
    
    for i, name in enumerate(valid_names, 1):
        # 关键1：每爬取20个干员，重启一次浏览器（避免内存泄漏）
        if i % 20 == 0:
            logger.info(f"\n🔄 爬取达20个干员，重启浏览器释放内存...")
            await OperatorDetailParser.close_shared_browser()
            await asyncio.sleep(5)
            await OperatorDetailParser.init_shared_browser()
        
        try:
            logger.info(f"进度: {i}/{len(valid_names)} - 开始同步 {name}")
            # 检查数据库连接（失效则重连）
            if not db.is_connected():
                logger.warning(f"⚠️ 数据库连接失效，尝试重连...")
                if not db.reconnect():
                    logger.error(f"❌ 数据库重连失败，跳过干员 {name}")
                    continue
            
            # 执行同步（增加单次失败重试）
            sync_retry = 0
            sync_success = False
            while sync_retry < 2 and not sync_success:
                try:
                    sync_success = await sync_operator_detail_to_db(db, name)
                except Exception as e:
                    error_msg = str(e).lower()
                    if "closed" in error_msg or "crashed" in error_msg:
                        logger.warning(f"⚠️ 干员 {name} 同步失败（浏览器崩溃），重试 ({sync_retry+1}/2)")
                        await OperatorDetailParser.close_shared_browser()
                        await asyncio.sleep(5)
                        await OperatorDetailParser.init_shared_browser()
                    sync_retry += 1
                    await asyncio.sleep(2)
            
            if sync_success:
                success_count += 1
        
        except Exception as e:
            logger.error(f"❌ 批量同步中干员 {name} 失败: {str(e)}", exc_info=True)
            # 异常后重置页面，避免影响下一个
            continue
        finally:
            # 关键2：增加爬取间隔（延长到3秒，降低浏览器压力）
            if i < len(valid_names):
                await asyncio.sleep(3)  # 核心：从1.5秒延长到3秒
    
    # ========== 批量结束后清理资源 ==========
    logger.info(f"===== 批量同步完成，成功: {success_count}/{len(valid_names)} =====")
    await OperatorDetailParser.close_shared_browser()  # 关闭全局浏览器
    db.close()  # 关闭数据库长连接
    return success_count

def sync_operators_detail():
    """同步干员一览→批量同步干员详情（核心优化：DB连接复用）"""
    logger.info("===== 开始同步干员详情 =====")
    db = DBHandler()
    success_count = 0
    valid_names = []
    
    try:          
        # 1. 单次创建DB连接，复用整个批量同步流程
        if not db.connect():
            logger.error("❌ 数据库连接失败，跳过入库")
            return
        
        # 2. 提取有效干员名称（修复元组转字符串）
        operators = db.select_all_operators()
        if not operators:
            logger.warning("⚠️ 无有效干员一览数据，跳过入库")
            return
        
        # 假设operator_base表中name_cn是第二个字段（索引1），根据实际表结构调整
        for op in operators:
            try:
                if len(op) >= 2 and op[1] and op[1].strip():
                    valid_names.append(op[1].strip())
            except:
                continue
        
        if not valid_names:
            logger.warning("⚠️ 无有效干员名称，跳过同步")
            return
            
        # 3. 批量同步（复用DB连接）
        success_count = asyncio.run(batch_sync_operators(db, valid_names))
        
    except Exception as e:
        logger.error(f"❌ 干员详情同步过程中发生错误: {str(e)}", exc_info=True)
    finally:
        # 4. 统一关闭DB连接（无论成功失败）
        try:
            db.close()
        except:
            pass
    
    logger.info(f"===== 干员详情同步总览：成功 {success_count}/{len(valid_names)} =====")

if __name__ == "__main__":
    # 可选执行顺序（按需注释/取消注释）
    # 1. 同步干员一览（批量入库基础信息）
    sync_operator_list_to_db()
    
    # 2. 同步静态术语（先于干员详情同步）
    sync_terms_to_db()

    # 3. 同步所有干员详情（复用DB连接，优化性能）
    sync_operators_detail()
    
    # 4. 手动批量同步多个干员（复用DB连接）
    # db = DBHandler()
    # if db.connect():
    #     asyncio.run(batch_sync_operators(db, ["焰影苇草", "令", "浊心斯卡蒂"]))
    #     db.close()