# db_handler.py
import mysql.connector
from mysql.connector import Error
from config import DB_CONFIG
from utils import logger

class DBHandler:
    def __init__(self):
        self.config = DB_CONFIG
        self.connection = None

    def connect(self):
        """建立数据库连接"""
        try:
            self.connection = mysql.connector.connect(**self.config)
            if self.connection.is_connected():
                logger.info("✅ 数据库连接成功（适配新表结构）")
                return True
        except Error as e:
            logger.error(f"❌ 数据库连接失败: {str(e)}")
        return False

    def close(self):
        """关闭数据库连接"""
        if self.connection and self.connection.is_connected():
            self.connection.close()
            logger.info("🔌 数据库连接已关闭")

    def insert_operator_base(self, base_info):
        """插入干员基础信息（适配operator_base表结构）"""
        cursor = self.connection.cursor()
        try:
            # 检查是否已存在（基于唯一键name_cn）
            cursor.execute("SELECT id FROM operator_base WHERE name_cn = %s", (base_info["name_cn"],))
            result = cursor.fetchone()
            if result:
                logger.warning(f"⚠️ 干员 {base_info['name_cn']} 已存在，跳过基础信息插入")
                return result[0]

            # 插入新干员（严格匹配operator_base字段）
            sql = """
            INSERT INTO operator_base (
                name_cn, rarity, profession, sub_profession, faction, hidden_faction,
                gender, position, tags, branch_description, trait_details,
                redployment_time, initial_deployment_cost, block_count, attack_interval
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            values = (
                base_info["name_cn"],
                base_info.get("rarity", ""),
                base_info.get("profession", ""),
                base_info.get("sub_profession", ""),
                base_info.get("faction", ""),
                base_info.get("hidden_faction", "无"),
                base_info.get("gender", ""),
                base_info.get("position", ""),
                " ".join(base_info.get("tags", [])) if isinstance(base_info.get("tags"), list) else base_info.get("tags", ""),
                base_info.get("branch_description", ""),
                base_info.get("trait_details", ""),
                base_info.get("redployment_time", ""),
                base_info.get("initial_deployment_cost", ""),  # 保留15→17这类字符串
                base_info.get("block_count", ""),
                base_info.get("attack_interval", "")
            )
            cursor.execute(sql, values)
            self.connection.commit()
            operator_id = cursor.lastrowid
            logger.info(f"✅ 插入干员基础信息: {base_info['name_cn']} (ID: {operator_id})")
            return operator_id
        except Error as e:
            self.connection.rollback()
            logger.error(f"❌ 插入基础信息失败 {base_info['name_cn']}: {str(e)}")
            return None
        finally:
            cursor.close()

    def insert_operator_attr(self, name_cn, attr_list):
        """插入干员属性（适配operator_attr表结构）"""
        cursor = self.connection.cursor()
        try:
            # 先删除旧数据（避免重复）
            cursor.execute("DELETE FROM operator_attr WHERE name_cn = %s", (name_cn,))
            
            sql = """
            INSERT INTO operator_attr (
                name_cn, attr_type, max_hp, atk, def, res
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """
            # 保留字符串格式，不强制转int
            values_list = []
            for attr in attr_list:
                values = (
                    name_cn,
                    attr["attr_type"],  # 枚举值：elite_0_level_1/elite_0_max等
                    attr.get("max_hp", ""),
                    attr.get("atk", ""),
                    attr.get("def", ""),
                    attr.get("res", "")
                )
                values_list.append(values)
            
            cursor.executemany(sql, values_list)
            self.connection.commit()
            logger.info(f"✅ 插入干员属性: {name_cn}（共{len(values_list)}条属性记录）")
            return True
        except Error as e:
            self.connection.rollback()
            logger.error(f"❌ 插入属性失败 {name_cn}: {str(e)}")
            return False
        finally:
            cursor.close()

    def insert_operator_talent(self, name_cn, talents):
        """插入干员天赋（适配operator_talent + operator_talent_detail表）"""
        cursor = self.connection.cursor()
        try:
            # 先删除旧数据
            cursor.execute("DELETE FROM operator_talent WHERE name_cn = %s", (name_cn,))
            cursor.execute("DELETE FROM operator_talent_detail WHERE talent_id IN (SELECT id FROM operator_talent WHERE name_cn = %s)", (name_cn,))
            
            # 插入天赋主信息
            talent_ids = []
            talent_sql = """
            INSERT INTO operator_talent (
                name_cn, talent_type, talent_name, remarks
            ) VALUES (%s, %s, %s, %s)
            """
            for talent in talents:
                cursor.execute(talent_sql, (
                    name_cn,
                    talent.get("talent_type", "第一天赋"),
                    talent.get("talent_name", ""),
                    talent.get("remarks", "")
                ))
                talent_id = cursor.lastrowid
                talent_ids.append((talent_id, talent))
            
            # 插入天赋详情
            detail_sql = """
            INSERT INTO operator_talent_detail (
                talent_id, trigger_condition, description, potential_enhancement
            ) VALUES (%s, %s, %s, %s)
            """
            detail_values = []
            for talent_id, talent in talent_ids:
                for detail in talent.get("details", []):
                    detail_values.append((
                        talent_id,
                        detail.get("trigger_condition", ""),
                        detail.get("description", ""),
                        detail.get("potential_enhancement", "")
                    ))
            cursor.executemany(detail_sql, detail_values)
            self.connection.commit()
            logger.info(f"✅ 插入干员天赋: {name_cn}（共{len(talents)}个天赋）")
            return True
        except Error as e:
            self.connection.rollback()
            logger.error(f"❌ 插入天赋失败 {name_cn}: {str(e)}")
            return False
        finally:
            cursor.close()

    def insert_operator_skill(self, name_cn, skills):
        """插入干员技能（适配operator_skill + operator_skill_level表）"""
        cursor = self.connection.cursor()
        try:
            # 先删除旧数据
            cursor.execute("DELETE FROM operator_skill WHERE name_cn = %s", (name_cn,))
            cursor.execute("DELETE FROM operator_skill_level WHERE skill_id IN (SELECT id FROM operator_skill WHERE name_cn = %s)", (name_cn,))
            
            # 插入技能主信息
            skill_ids = []
            skill_sql = """
            INSERT INTO operator_skill (
                name_cn, skill_number, skill_name, skill_type, unlock_condition, remark
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """
            for skill in skills:
                cursor.execute(skill_sql, (
                    name_cn,
                    skill.get("skill_number", 1),
                    skill.get("skill_name", ""),
                    skill.get("skill_type", ""),
                    skill.get("unlock_condition", ""),
                    skill.get("remark", "")
                ))
                skill_id = cursor.lastrowid
                skill_ids.append((skill_id, skill))
            
            # 插入技能等级
            level_sql = """
            INSERT INTO operator_skill_level (
                skill_id, level, description, initial_sp, sp_cost, duration
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """
            level_values = []
            for skill_id, skill in skill_ids:
                for level in skill.get("skill_levels", []):
                    level_values.append((
                        skill_id,
                        level.get("level", ""),
                        level.get("description", ""),
                        level.get("initial_sp", ""),
                        level.get("sp_cost", ""),
                        level.get("duration", "")
                    ))
            cursor.executemany(level_sql, level_values)
            self.connection.commit()
            logger.info(f"✅ 插入干员技能: {name_cn}（共{len(skills)}个技能）")
            return True
        except Error as e:
            self.connection.rollback()
            logger.error(f"❌ 插入技能失败 {name_cn}: {str(e)}")
            return False
        finally:
            cursor.close()
            
    def insert_global_terms(self, terms):
        """插入全局术语"""
        cursor = self.connection.cursor()
        try:
            sql = """
            INSERT INTO global_terms (
                term_name, term_explanation
            ) VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE 
                term_explanation = VALUES(term_explanation)
            """
            values_list = []
            for term in terms:
                values_list.append((
                    term["term_name"],
                    term.get("term_explanation", "")
                ))
            cursor.executemany(sql, values_list)
            self.connection.commit()
            logger.info(f"✅ 插入/更新全局术语（共{len(terms)}条）")
            return True
        except Error as e:
            self.connection.rollback()
            logger.error(f"❌ 插入术语失败: {str(e)}")
            return False
        finally:
            cursor.close()
            
    def count_global_terms(self):
        """统计全局术语数量"""
        cursor = self.connection.cursor()
        try:
            cursor.execute("SELECT COUNT(*) FROM global_terms")
            result = cursor.fetchone()
            return result[0]
        except Error as e:
            logger.error(f"❌ 统计全局术语数量失败: {str(e)}")
            return 0
        finally:
            cursor.close()


    def insert_operator_term_relation(self, name_cn, term_relations):
        """插入干员-术语关联"""
        cursor = self.connection.cursor()
        try:
            # 先删除旧关联
            cursor.execute("DELETE FROM operator_term_relation WHERE name_cn = %s", (name_cn,))
            
            sql = """
            INSERT INTO operator_term_relation (
                name_cn, term_name, relation_module, module_id
            ) VALUES (%s, %s, %s, %s)
            """
            values_list = []
            for relation in term_relations:
                values_list.append((
                    name_cn,
                    relation["term_name"],
                    relation.get("relation_module", ""),  # trait/天赋/技能
                    relation.get("module_id", "")         # 天赋1/技能3等
                ))
            cursor.executemany(sql, values_list)
            self.connection.commit()
            logger.info(f"✅ 插入干员术语关联: {name_cn}（共{len(term_relations)}条）")
            return True
        except Error as e:
            self.connection.rollback()
            logger.error(f"❌ 插入术语关联失败 {name_cn}: {str(e)}")
            return False
        finally:
            cursor.close()

    def batch_insert_operator_base(self, ops_list: list[dict]):
        """批量插入干员基础信息（从干员一览数据）"""
        cursor = self.connection.cursor()
        try:
            # 批量插入SQL（ON DUPLICATE KEY UPDATE 避免重复）
            sql = """
            INSERT INTO operator_base (
                name_cn, rarity, profession, sub_profession, faction,
                gender, position, tags
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                rarity = VALUES(rarity),
                profession = VALUES(profession),
                sub_profession = VALUES(sub_profession),
                faction = VALUES(faction),
                gender = VALUES(gender),
                position = VALUES(position),
                tags = VALUES(tags)
            """
            # 构造批量插入的参数列表
            values_list = []
            for op in ops_list:
                values_list.append((
                    op.get("name_cn", ""),
                    op.get("rarity", ""),
                    op.get("profession", ""),
                    op.get("sub_profession", ""),
                    op.get("faction", ""),
                    op.get("gender", ""),
                    op.get("position", ""),
                    op.get("tags", "")  # 保留原始逗号分隔的标签
                ))
            
            # 执行批量插入
            cursor.executemany(sql, values_list)
            self.connection.commit()
            
            logger.info(f"✅ 批量插入/更新干员基础信息（共{len(ops_list)}条）")
            return True
        except Error as e:
            self.connection.rollback()
            logger.error(f"❌ 批量插入干员基础信息失败: {str(e)}")
            return False
        finally:
            cursor.close()

# 调用示例（可单独调试）
if __name__ == "__main__":
    # 初始化DBHandler
    db = DBHandler()
    if db.connect():
        # 1. 插入干员基础信息示例
        base_info = {
            "name_cn": "焰影苇草",
            "rarity": "6",
            "profession": "医疗",
            "sub_profession": "咒愈师",
            "faction": "维多利亚塔拉",
            "hidden_faction": "无",
            "gender": "女",
            "position": "远程位",
            "tags": ["治疗", "输出", "削弱"],
            "branch_description": "攻击造成法术伤害，攻击敌人时为攻击范围内一名友方干员治疗相当于50%伤害的生命值",
            "trait_details": "治疗量不受目标伤害减免影响",
            "redployment_time": "70s",
            "initial_deployment_cost": "15→17",
            "block_count": "1",
            "attack_interval": "1.6s"
        }
        db.insert_operator_base(base_info)

        # 2. 插入干员属性示例
        attr_list = [
            {
                "attr_type": "elite_0_level_1",
                "max_hp": "868",
                "atk": "192",
                "def": "36",
                "res": "10"
            },
            {
                "attr_type": "elite_2_max",
                "max_hp": "2100",
                "atk": "480",
                "def": "120",
                "res": "20"
            }
        ]
        db.insert_operator_attr("焰影苇草", attr_list)

        # 3. 插入天赋示例
        talents = [
            {
                "talent_type": "第一天赋",
                "talent_name": "灼痕",
                "remarks": "※触发本天赋的当次伤害可受到本天赋加成",
                "details": [{
                    "trigger_condition": "精英1",
                    "description": "造成伤害时有30%概率对敌人施加灼痕效果",
                    "potential_enhancement": "概率提升至35%"
                }]
            }
        ]
        db.insert_operator_talent("焰影苇草", talents)

        # 4. 插入技能示例
        skills = [
            {
                "skill_number": 1,
                "skill_name": "迅捷打击·γ型",
                "skill_type": "自动回复|手动触发",
                "unlock_condition": "精英1",
                "remark": "",
                "skill_levels": [
                    {
                        "level": "7",
                        "description": "攻击力 +34% ，攻击速度 +35",
                        "initial_sp": "10",
                        "sp_cost": "39",
                        "duration": "35"
                    }
                ]
            }
        ]
        db.insert_operator_skill("焰影苇草", skills)

        # 5. 插入全局术语示例
        terms = [
            {
                "term_name": "法术脆弱",
                "term_type": "异常效果",
                "term_explanation": "受到的法术伤害提升相应比例（同名效果取最高）"
            }
        ]
        db.insert_global_terms(terms)

        # 6. 插入干员-术语关联示例
        term_relations = [
            {
                "term_name": "法术脆弱",
                "relation_module": "天赋",
                "module_id": "1"
            }
        ]
        db.insert_operator_term_relation("焰影苇草", term_relations)

        # 关闭连接
        db.close()