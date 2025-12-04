import mysql.connector
from mysql.connector import Error
from dotenv import load_dotenv
import os
from datetime import datetime

load_dotenv()

class DBHandler:
    def __init__(self):
        self.config = {
            "host": os.getenv("DB_HOST"),
            "port": int(os.getenv("DB_PORT", 3306)),
            "user": os.getenv("DB_USER"),
            "password": os.getenv("DB_PASSWORD"),
            "database": os.getenv("DB_NAME", "arknights"),
            "charset": "utf8mb4"
        }
        self.connection = None

    def connect(self):
        """建立数据库连接"""
        try:
            self.connection = mysql.connector.connect(**self.config)
            if self.connection.is_connected():
                print("✅ 数据库连接成功（适配新表结构）")
                return True
        except Error as e:
            print(f"❌ 数据库连接失败: {str(e)}")
        return False

    def close(self):
        """关闭数据库连接"""
        if self.connection and self.connection.is_connected():
            self.connection.close()
            print("🔌 数据库连接已关闭")

    def insert_operator_base(self, base_info):
        """插入干员基础信息（适配新表：补充稀有度/职业等字段）"""
        cursor = self.connection.cursor()
        try:
            # 检查是否已存在（避免重复）
            cursor.execute("SELECT id FROM operators WHERE name = %s AND is_deleted = 0", (base_info["name"],))
            result = cursor.fetchone()
            if result:
                print(f"⚠️ 干员 {base_info['name']} 已存在，跳过基础信息插入")
                return result[0]

            # 插入新干员（适配新表字段）
            sql = """
            INSERT INTO operators (
                name, rarity, profession, branch, faction, gender, position, tags,
                branch_name, branch_description, trait_details
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            values = (
                base_info["name"],
                base_info.get("rarity", ""),
                base_info.get("profession", ""),
                base_info.get("branch", ""),
                base_info.get("faction", ""),
                base_info.get("gender", ""),
                base_info.get("position", ""),
                " ".join(base_info.get("tags", [])),  # 标签用空格拼接
                base_info.get("branch_name", ""),
                base_info.get("branch_description", ""),
                base_info.get("trait_details", "")
            )
            cursor.execute(sql, values)
            self.connection.commit()
            operator_id = cursor.lastrowid
            print(f"✅ 插入干员基础信息: {base_info['name']} (ID: {operator_id})")
            return operator_id
        except Error as e:
            self.connection.rollback()
            print(f"❌ 插入基础信息失败 {base_info['name']}: {str(e)}")
            return None
        finally:
            cursor.close()

    def insert_operator_attributes(self, operator_id, attr_list):
        """插入干员基础属性（适配INT类型字段）"""
        cursor = self.connection.cursor()
        try:
            # 先删除旧数据（避免重复）
            cursor.execute("DELETE FROM operator_attributes WHERE operator_id = %s", (operator_id,))
            
            sql = """
            INSERT INTO operator_attributes (
                operator_id, elite_level, max_hp, atk, def, res
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """
            # 处理数值转换（特殊值如"∞"转为NULL）
            def convert_num(val):
                try:
                    return int(val) if val and val != "∞" else None
                except:
                    return None

            values_list = []
            for attr in attr_list:
                values = (
                    operator_id,
                    attr["elite_level"],
                    convert_num(attr.get("max_hp")),
                    convert_num(attr.get("atk")),
                    convert_num(attr.get("def")),
                    convert_num(attr.get("res"))
                )
                values_list.append(values)
            
            cursor.executemany(sql, values_list)
            self.connection.commit()
            print(f"✅ 插入干员基础属性: ID {operator_id}（共{len(values_list)}条）")
            return True
        except Error as e:
            self.connection.rollback()
            print(f"❌ 插入基础属性失败 ID {operator_id}: {str(e)}")
            return False
        finally:
            cursor.close()

    def insert_operator_extra_attrs(self, operator_id, extra_attr):
        """插入干员额外属性（修正拼写错误redeployment_time）"""
        cursor = self.connection.cursor()
        try:
            # 先删除旧数据
            cursor.execute("DELETE FROM operator_extra_attrs WHERE operator_id = %s", (operator_id,))
            
            sql = """
            INSERT INTO operator_extra_attrs (
                operator_id, redeployment_time, initial_deployment_cost,
                attack_interval, block_count, hidden_faction
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """
            values = (
                operator_id,
                extra_attr.get("redeployment_time", ""),
                int(extra_attr.get("initial_deployment_cost", 0)) if extra_attr.get("initial_deployment_cost") else 0,
                extra_attr.get("attack_interval", ""),
                int(extra_attr.get("block_count", 0)) if extra_attr.get("block_count") else 0,
                extra_attr.get("hidden_faction", "")
            )
            cursor.execute(sql, values)
            self.connection.commit()
            print(f"✅ 插入干员额外属性: ID {operator_id}")
            return True
        except Error as e:
            self.connection.rollback()
            print(f"❌ 插入额外属性失败 ID {operator_id}: {str(e)}")
            return False
        finally:
            cursor.close()

    def insert_operator_talents(self, operator_id, talents):
        """插入干员天赋（基础+详情）"""
        cursor = self.connection.cursor()
        try:
            # 先删除旧数据
            cursor.execute("DELETE FROM operator_talents WHERE operator_id = %s", (operator_id,))
            cursor.execute("DELETE FROM talent_details WHERE talent_id IN (SELECT id FROM operator_talents WHERE operator_id = %s)", (operator_id,))
            
            # 插入天赋基础信息
            talent_ids = []
            talent_sql = """
            INSERT INTO operator_talents (
                operator_id, talent_type, talent_name, remarks
            ) VALUES (%s, %s, %s, %s)
            """
            for talent in talents:
                cursor.execute(talent_sql, (
                    operator_id,
                    talent.get("talent_type", "第一天赋"),
                    talent.get("talent_name", ""),
                    talent.get("remarks", "")
                ))
                talent_id = cursor.lastrowid
                talent_ids.append((talent_id, talent))
            
            # 插入天赋详情
            detail_sql = """
            INSERT INTO talent_details (
                talent_id, trigger_condition, description, potential_enhancement
            ) VALUES (%s, %s, %s, %s)
            """
            detail_values = []
            for talent_id, talent in talent_ids:
                detail_values.append((
                    talent_id,
                    talent.get("trigger_condition", ""),
                    talent.get("description", ""),
                    talent.get("potential_enhancement", "")
                ))
            cursor.executemany(detail_sql, detail_values)
            self.connection.commit()
            print(f"✅ 插入干员天赋: ID {operator_id}（共{len(talents)}个天赋）")
            return True
        except Error as e:
            self.connection.rollback()
            print(f"❌ 插入天赋失败 ID {operator_id}: {str(e)}")
            return False
        finally:
            cursor.close()

    def insert_operator_skills(self, operator_id, skills):
        """插入干员技能（基础+等级）"""
        cursor = self.connection.cursor()
        try:
            # 先删除旧数据
            cursor.execute("DELETE FROM operator_skills WHERE operator_id = %s", (operator_id,))
            cursor.execute("DELETE FROM skill_levels WHERE skill_id IN (SELECT id FROM operator_skills WHERE operator_id = %s)", (operator_id,))
            
            # 插入技能基础信息
            skill_ids = []
            skill_sql = """
            INSERT INTO operator_skills (
                operator_id, skill_number, skill_name, skill_type, unlock_condition, remarks
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """
            for skill in skills:
                cursor.execute(skill_sql, (
                    operator_id,
                    skill.get("skill_number", 1),
                    skill.get("skill_name", ""),
                    skill.get("skill_type", ""),
                    skill.get("unlock_condition", ""),
                    skill.get("remarks", "")
                ))
                skill_id = cursor.lastrowid
                skill_ids.append((skill_id, skill))
            
            # 插入技能等级
            level_sql = """
            INSERT INTO skill_levels (
                skill_id, level, initial_sp, sp_cost, duration, description
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """
            level_values = []
            for skill_id, skill in skill_ids:
                for level in skill.get("levels", []):
                    level_values.append((
                        skill_id,
                        level.get("level", ""),
                        int(level.get("initial_sp", 0)) if level.get("initial_sp") else 0,
                        int(level.get("sp_cost", 0)) if level.get("sp_cost") else 0,
                        level.get("duration", ""),
                        level.get("description", "")
                    ))
            cursor.executemany(level_sql, level_values)
            self.connection.commit()
            print(f"✅ 插入干员技能: ID {operator_id}（共{len(skills)}个技能）")
            return True
        except Error as e:
            self.connection.rollback()
            print(f"❌ 插入技能失败 ID {operator_id}: {str(e)}")
            return False
        finally:
            cursor.close()