-- 先删除旧表（仅无数据时执行！有数据先备份）
DROP TABLE IF EXISTS skill_levels;
DROP TABLE IF EXISTS operator_skills;
DROP TABLE IF EXISTS talent_details;
DROP TABLE IF EXISTS operator_talents;
DROP TABLE IF EXISTS operator_extra_attrs;
DROP TABLE IF EXISTS operator_attributes;
DROP TABLE IF EXISTS operators;

-- 重新创建数据库（确保字符集/排序规则正确）
CREATE DATABASE IF NOT EXISTS arknights 
DEFAULT CHARACTER SET utf8mb4 
COLLATE utf8mb4_unicode_ci 
COMMENT '明日方舟干员数据仓库（ArkDataKit）';

USE arknights;

-- 1. 干员核心基础信息表（补充所有缺失字段，修正类型）
CREATE TABLE operators (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID，自增',
    name VARCHAR(100) NOT NULL UNIQUE COMMENT '干员名称（如：阿米娅、能天使）',
    rarity VARCHAR(10) NOT NULL COMMENT '稀有度（如：6★、5★）',
    profession VARCHAR(50) NOT NULL COMMENT '职业（如：近卫、狙击）',
    branch VARCHAR(50) NOT NULL COMMENT '职业分支（如：领主、速射手）',
    faction VARCHAR(100) COMMENT '所属阵营（如：罗德岛、格拉斯哥帮）',
    gender VARCHAR(10) COMMENT '性别（男/女/未知/女士）',
    position VARCHAR(20) COMMENT '位置（远程位/近战位）',
    tags VARCHAR(200) COMMENT '标签（空格分隔，如：输出 控场）',
    branch_name VARCHAR(100) COMMENT '职业分支名称（冗余补充，如：术师-中坚术师）',
    branch_description TEXT COMMENT '职业分支描述（该分支的核心特性）',
    trait_details TEXT COMMENT '干员特性详情（天赋外的核心被动）',
    is_deleted TINYINT(1) DEFAULT 0 COMMENT '软删除标记：0=未删除，1=已删除',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '数据创建时间',
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '数据更新时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT '明日方舟干员核心基础信息表';

-- 2. 干员基础属性表（数值字段改INT，保留VARCHAR兼容特殊值）
CREATE TABLE operator_attributes (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID，自增',
    operator_id INT NOT NULL COMMENT '关联operators表的主键ID',
    elite_level VARCHAR(50) NOT NULL COMMENT '精英等级+等级标识（如：elite_0_level_1、elite_2_max）',
    max_hp INT COMMENT '最大生命值（特殊值如“∞”存NULL，代码层处理）',
    atk INT COMMENT '攻击力',
    def INT COMMENT '防御力',
    res INT COMMENT '法术抗性',
    is_deleted TINYINT(1) DEFAULT 0 COMMENT '软删除标记',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (operator_id) REFERENCES operators(id) ON DELETE CASCADE,
    -- 复合索引：按干员ID+精英等级查询（高频场景）
    INDEX idx_op_attr (operator_id, elite_level) COMMENT '索引：加快按干员+精英等级查询属性'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT '明日方舟干员基础属性表（删除干员时同步删除属性）';

-- 3. 干员额外属性表（修正拼写错误，补充默认值）
CREATE TABLE operator_extra_attrs (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID，自增',
    operator_id INT NOT NULL COMMENT '关联operators表的主键ID',
    redeployment_time VARCHAR(20) COMMENT '再部署时间（如：70s）',
    initial_deployment_cost INT COMMENT '初始部署费用',
    attack_interval VARCHAR(20) COMMENT '攻击间隔（如：1.0s）',
    block_count INT DEFAULT 0 COMMENT '阻挡数（可阻挡的敌人数量）',
    hidden_faction VARCHAR(100) COMMENT '隐藏阵营（如：萨卡兹、埃拉菲亚）',
    is_deleted TINYINT(1) DEFAULT 0 COMMENT '软删除标记',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (operator_id) REFERENCES operators(id) ON DELETE CASCADE,
    INDEX idx_operator_extra (operator_id) COMMENT '索引：加快按干员ID查询部署/阵营等额外属性'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT '明日方舟干员额外属性表（删除干员时同步删除属性）';

-- 4. 干员天赋基础表（补充默认值）
CREATE TABLE operator_talents (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID，自增',
    operator_id INT NOT NULL COMMENT '关联operators表的主键ID',
    talent_type VARCHAR(50) DEFAULT '第一天赋' COMMENT '天赋类型（如：第一天赋、第二天赋、精英二解锁天赋）',
    talent_name VARCHAR(100) COMMENT '天赋名称（如：精神爆发、战场机动）',
    remarks TEXT COMMENT '天赋备注（如：潜能提升效果说明）',
    is_deleted TINYINT(1) DEFAULT 0 COMMENT '软删除标记',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (operator_id) REFERENCES operators(id) ON DELETE CASCADE,
    -- 复合索引：按干员ID+天赋类型查询
    INDEX idx_op_talent (operator_id, talent_type) COMMENT '索引：加快按干员+天赋类型查询天赋'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT '明日方舟干员天赋基础信息表';

-- 5. 天赋详情表（无变更，补充软删除）
CREATE TABLE talent_details (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID，自增',
    talent_id INT NOT NULL COMMENT '关联operator_talents表的主键ID',
    trigger_condition TEXT COMMENT '天赋触发条件（如：精英二等级90、部署后）',
    description TEXT COMMENT '天赋效果描述（详细的数值/效果说明）',
    potential_enhancement TEXT COMMENT '潜能提升后的天赋增强效果',
    is_deleted TINYINT(1) DEFAULT 0 COMMENT '软删除标记',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (talent_id) REFERENCES operator_talents(id) ON DELETE CASCADE,
    INDEX idx_talent_detail (talent_id) COMMENT '索引：加快按天赋ID查询触发条件/效果'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT '明日方舟干员天赋详情表';

-- 6. 干员技能基础表（补充默认值，复合索引）
CREATE TABLE operator_skills (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID，自增',
    operator_id INT NOT NULL COMMENT '关联operators表的主键ID',
    skill_number INT DEFAULT 1 COMMENT '技能编号（1/2/3，对应第一/二/三技能）',
    skill_name VARCHAR(100) COMMENT '技能名称（如：强力击·γ型、剑雨）',
    skill_type VARCHAR(50) COMMENT '技能类型（如：攻击回复/自动回复、手动触发/自动触发）',
    unlock_condition TEXT COMMENT '技能解锁条件（如：精英一等级1、精英二等级30）',
    remarks TEXT COMMENT '技能备注（如：专精效果说明）',
    is_deleted TINYINT(1) DEFAULT 0 COMMENT '软删除标记',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (operator_id) REFERENCES operators(id) ON DELETE CASCADE,
    -- 复合索引：按干员ID+技能编号查询（高频场景）
    INDEX idx_op_skill (operator_id, skill_number) COMMENT '索引：加快按干员+技能编号查询技能'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT '明日方舟干员技能基础信息表';

-- 7. 技能等级表（补充默认值，复合索引）
CREATE TABLE skill_levels (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '主键ID，自增',
    skill_id INT NOT NULL COMMENT '关联operator_skills表的主键ID',
    level VARCHAR(10) COMMENT '技能等级（如：1/7/专精1/专精3）',
    initial_sp INT DEFAULT 0 COMMENT '初始技力值',
    sp_cost INT DEFAULT 0 COMMENT '技力消耗',
    duration VARCHAR(10) COMMENT '技能持续时间（如：20s、永续）',
    description TEXT COMMENT '该等级下的技能效果描述（含数值）',
    is_deleted TINYINT(1) DEFAULT 0 COMMENT '软删除标记',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (skill_id) REFERENCES operator_skills(id) ON DELETE CASCADE,
    -- 复合索引：按技能ID+等级查询
    INDEX idx_skill_level (skill_id, level) COMMENT '索引：加快按技能+等级查询数值/效果'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT '明日方舟干员技能等级详情表';

CREATE TABLE IF NOT EXISTS terms (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '术语主键ID，自增',
    term_name VARCHAR(100) NOT NULL COMMENT '术语名称（如：法术脆弱、物理易伤，全局唯一）',
    term_explanation TEXT NOT NULL COMMENT '术语完整解释（从PRTS术语释义页爬取）',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '术语入库时间',
    update_time DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '术语更新时间',
    PRIMARY KEY (id),
    UNIQUE KEY uk_term_name (term_name) COMMENT '术语名全局唯一，避免重复',
    KEY idx_term_name (term_name) COMMENT '加快按术语名查询'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='明日方舟PRTS术语基础表';
CREATE TABLE IF NOT EXISTS operator_term_relations (
    id INT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '关联记录主键ID，自增',
    operator_name VARCHAR(50) NOT NULL COMMENT '关联干员名称（对应operators表的name字段）',
    term_name VARCHAR(100) NOT NULL COMMENT '关联术语名称（对应terms表的term_name字段）',
    relation_type VARCHAR(20) NOT NULL COMMENT '术语出现的模块类型：trait=特性、talent=天赋、skill=技能',
    relation_id INT UNSIGNED DEFAULT 0 COMMENT '模块ID：特性填0，天赋填天赋序号（1/2），技能填技能序号（1/2/3）',
    create_time DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '关联记录创建时间',
    PRIMARY KEY (id),
    -- 唯一索引：避免同一干员-模块-术语重复存储（核心去重）
    UNIQUE KEY uk_otr_uniq (operator_name, term_name, relation_type, relation_id),
    -- 外键约束：确保关联的干员/术语存在，删除时级联删除关联记录
    CONSTRAINT fk_otr_operator FOREIGN KEY (operator_name) REFERENCES operators (name) ON DELETE CASCADE,
    CONSTRAINT fk_otr_term FOREIGN KEY (term_name) REFERENCES terms (term_name) ON DELETE CASCADE,
    -- 复合索引：优化「干员查术语」「术语查干员」高频场景
    KEY idx_otr_operator (operator_name, relation_type),
    KEY idx_otr_term (term_name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='干员-术语关联表（记录术语出现在干员的具体模块）';