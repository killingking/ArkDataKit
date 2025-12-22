# main.py
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
        # 统一类调用方式
        crawler = TermStaticCrawler()
        terms = crawler.run()
        # logger.info(f"terms: {terms}")
        
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
        logger.error(f"❌ 术语同步过程中发生错误: {str(e)}")
    finally:
        db.close()        

def sync_operator_list_to_db():
    """干员一览爬取→批量入库"""
    logger.info("===== 开始同步干员一览数据 =====")
    db = DBHandler()
    
    try:
        # 统一类调用方式
        crawler = OperatorListCrawler()
        ops_list = crawler.run()
        if not ops_list:
            logger.warning("⚠️ 无有效干员一览数据，跳过入库")
            return
            
        if not db.connect():
            logger.error("❌ 数据库连接失败，跳过入库")
            return
            
        db.batch_insert_operator_base(ops_list)
        logger.info(f"✅ 成功入库 {len(ops_list)} 条干员基础信息")
        
    except Exception as e:
        logger.error(f"❌ 干员一览同步过程中发生错误: {str(e)}")
    finally:
        db.close()

async def sync_operator_detail_to_db(operator_name: str):
    """干员详情解析→入库"""
    logger.info(f"===== 开始同步干员 {operator_name} 详情 =====")
    db = DBHandler()
    
    try:
        # 统一类调用方式
        parser = OperatorDetailParser(operator_name)
        operator_data = await parser.run()
        if not operator_data:
            logger.warning("⚠️ 干员解析失败，跳过入库")
            return
        
        # 数据验证
        required_fields = ["operator_name", "characteristic", "attributes"]
        for field in required_fields:
            if field not in operator_data:
                logger.error(f"❌ 缺少必要字段: {field}")
                return
        
        # 整理入库数据
        base_info = {
            "name_cn": operator_data["operator_name"],
            "rarity": "",  # 从干员一览补充（可结合operators_list_get的结果）
            "profession": "",  # 从干员一览补充
            "sub_profession": operator_data["characteristic"].get("branch_name", ""),
            "faction": operator_data["attributes"]["extra_attributes"].get("faction", ""),
            "hidden_faction": operator_data["attributes"]["extra_attributes"].get("hidden_faction", ""),
            "gender": "",  # 从干员一览补充
            "position": "",  # 从干员一览补充
            "tags": "",  # 从干员一览补充
            "branch_description": operator_data["characteristic"].get("branch_description", ""),
            "trait_details": operator_data["characteristic"].get("trait_details", ""),
            "redployment_time": operator_data["attributes"]["extra_attributes"].get("redployment_time", ""),
            "initial_deployment_cost": operator_data["attributes"]["extra_attributes"].get("initial_deployment_cost", ""),
            "block_count": operator_data["attributes"]["extra_attributes"].get("block_count", ""),
            "attack_interval": operator_data["attributes"]["extra_attributes"].get("attack_interval", "")
        }
        
        attr_list = []
        base_attributes = operator_data["attributes"].get("base_attributes", {})
        for attr_type, attr_values in base_attributes.items():
            attr_list.append({
                "attr_type": attr_type,
                "max_hp": attr_values.get("max_hp", ""),
                "atk": attr_values.get("atk", ""),
                "def": attr_values.get("def", ""),
                "res": attr_values.get("res", "")
            })
        
        if not db.connect():
            logger.error("❌ 数据库连接失败，跳过入库")
            return
            
        # 插入基础信息
        db.insert_operator_base(base_info)
        # 插入属性
        if attr_list:
            db.insert_operator_attr(operator_name, attr_list)
        # 插入天赋
        if "talents" in operator_data and operator_data["talents"]:
            db.insert_operator_talent(operator_name, operator_data["talents"])
        # 插入技能
        if "skills" in operator_data and operator_data["skills"]:
            db.insert_operator_skill(operator_name, operator_data["skills"])
        # 插入干员术语关联
        if "terms" in operator_data and operator_data["terms"]:
            term_relations = [
                {"term_name": t.get("term_name", ""), "relation_module": "技能/天赋", "module_id": ""} 
                for t in operator_data["terms"] if t.get("term_name")
            ]
            if term_relations:
                db.insert_operator_term_relation(operator_name, term_relations)
                
        logger.info(f"✅ 干员 {operator_name} 详情同步完成")
        
    except Exception as e:
        logger.error(f"❌ 干员 {operator_name} 详情同步过程中发生错误: {str(e)}")
    finally:
        db.close()

# 调试用：批量同步多个干员
async def batch_sync_operators(operator_names: list[str]):
    """批量同步多个干员详情"""
    if not operator_names:
        logger.warning("⚠️ 干员名称列表为空，跳过批量同步")
        return
        
    logger.info(f"===== 开始批量同步 {len(operator_names)} 个干员详情 =====")
    success_count = 0
    
    for i, name in enumerate(operator_names, 1):
        try:
            logger.info(f"进度: {i}/{len(operator_names)} - 开始同步 {name}")
            await sync_operator_detail_to_db(name)
            success_count += 1
        except Exception as e:
            logger.error(f"❌ 批量同步中干员 {name} 失败: {str(e)}")
        
        # 避免请求过快被反爬
        if i < len(operator_names):  # 最后一个不需要等待
            await asyncio.sleep(2)
    
    logger.info(f"===== 批量同步完成，成功: {success_count}/{len(operator_names)} =====")

if __name__ == "__main__":
    # 可选执行顺序（按需注释/取消注释）
    # 1. 同步干员一览（批量入库基础信息）
    # sync_operator_list_to_db()
    
    # 2. 同步静态术语    # 2. 同步静态术语（先于干员详情同步）
    sync_terms_to_db()

    
    # 3. 同步单个干员详情（补充属性/天赋/技能）
    # asyncio.run(sync_operator_detail_to_db("焰影苇草"))
    
    # 4. 批量同步多个干员
    # asyncio.run(batch_sync_operators(["焰影苇草", "令", "浊心斯卡蒂"]))
    pass