/* 先删除表（按外键依赖倒序删除，避免关联报错） */
-- 8. 干员-术语关联表（依赖operator_base + global_terms）
DROP TABLE IF EXISTS operator_term_relation;
-- 6. 干员技能等级表（依赖operator_skill）
DROP TABLE IF EXISTS operator_skill_level;
-- 5. 干员技能表（依赖operator_base）
DROP TABLE IF EXISTS operator_skill;
-- 4. 干员天赋详情表（依赖operator_talent）
DROP TABLE IF EXISTS operator_talent_detail;
-- 3. 干员天赋表（依赖operator_base）
DROP TABLE IF EXISTS operator_talent;
-- 2. 干员属性表（依赖operator_base）
DROP TABLE IF EXISTS operator_attr;
-- 7. 全局术语表（无依赖）
DROP TABLE IF EXISTS global_terms;
-- 1. 干员基础信息表（主表，最后删）
DROP TABLE IF EXISTS operator_base;

/* 1. 干员基础信息表（核心主表，存储扁平基础信息） */
CREATE TABLE operator_base (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '自增主键',
    name_cn VARCHAR(50) NOT NULL COMMENT '干员中文名称（如：焰影苇草）',
    rarity VARCHAR(10) NOT NULL COMMENT '稀有度（如：6）',
    profession VARCHAR(20) NOT NULL COMMENT '大职业（如：医疗）',
    sub_profession VARCHAR(20) NOT NULL COMMENT '子职业/分支（如：咒愈师）',
    faction VARCHAR(50) COMMENT '所属阵营（如：维多利亚塔拉）',
    hidden_faction VARCHAR(50) DEFAULT '无' COMMENT '隐藏阵营（如：无）',
    gender VARCHAR(10) COMMENT '性别（男/女）',
    position VARCHAR(10) NOT NULL COMMENT '部署位置（远程位/近战位）',
    tags VARCHAR(100) COMMENT '标签（如：治疗 输出 削弱，空格分隔）',
    branch_description VARCHAR(500) COMMENT '分支描述（如：攻击造成法术伤害...）',
    trait_details VARCHAR(500) DEFAULT '' COMMENT '特性详情（JSON中trait_details字段）',
    redployment_time VARCHAR(10) COMMENT '再部署时间（如：70s）',
    initial_deployment_cost VARCHAR(10) COMMENT '初始部署费用（如：15→17）',
    block_count VARCHAR(10) COMMENT '阻挡数（如：1）',
    attack_interval VARCHAR(10) COMMENT '攻击间隔（如：1.6s）',
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '入库时间',
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    UNIQUE KEY uk_name_cn (name_cn) COMMENT '干员名称唯一，避免重复'
) COMMENT '干员基础信息表（无字典表，直接存储所有基础字段）';

/* 2. 干员属性表（仅存储JSON中指定的5类属性维度） */
CREATE TABLE operator_attr (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '自增主键',
    name_cn VARCHAR(50) NOT NULL COMMENT '关联干员名称',
    attr_type VARCHAR(20) NOT NULL COMMENT '属性类型（固定枚举：elite_0_level_1/elite_0_max/elite_1_max/elite_2_max/trust_bonus）',
    max_hp VARCHAR(10) DEFAULT '' COMMENT '最大生命值（JSON中字符串值，如：868）',
    atk VARCHAR(10) DEFAULT '' COMMENT '攻击力（如：192）',
    def VARCHAR(10) DEFAULT '' COMMENT '防御力（如：36）',
    res VARCHAR(10) DEFAULT '' COMMENT '法术抗性（如：10）',
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '入库时间',
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    -- 外键关联：删除/更新干员时同步删除/更新属性（注释用-- 说明，而非COMMENT子句）
    FOREIGN KEY (name_cn) REFERENCES operator_base(name_cn) ON DELETE CASCADE ON UPDATE CASCADE,
    UNIQUE KEY uk_name_attr_type (name_cn, attr_type) COMMENT '干员+属性类型唯一，避免重复'
) COMMENT '干员属性表（仅存储JSON中指定的5类属性）';

/* 3. 干员天赋表（天赋主信息） */
CREATE TABLE operator_talent (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '自增主键',
    name_cn VARCHAR(50) NOT NULL COMMENT '关联干员名称',
    talent_type VARCHAR(20) NOT NULL COMMENT '天赋类型（如：第一天赋/第二天赋）',
    talent_name VARCHAR(50) NOT NULL COMMENT '天赋名称（如：灼痕/映耀）',
    remarks TEXT COMMENT '天赋备注（如：※触发本天赋的当次伤害...）',
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '入库时间',
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    -- 外键关联：删除/更新干员时同步删除/更新天赋（注释用-- 说明）
    FOREIGN KEY (name_cn) REFERENCES operator_base(name_cn) ON DELETE CASCADE ON UPDATE CASCADE,
    UNIQUE KEY uk_name_talent_type (name_cn, talent_type) COMMENT '干员+天赋类型唯一'
) COMMENT '干员天赋主信息表';

/* 4. 干员天赋详情表（天赋不同触发条件的效果） */
CREATE TABLE operator_talent_detail (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '自增主键',
    talent_id INT NOT NULL COMMENT '关联天赋表ID',
    trigger_condition VARCHAR(50) NOT NULL COMMENT '触发条件（如：精英1/精英2 X模组3级）',
    description TEXT NOT NULL COMMENT '天赋描述（如：造成伤害时有30%概率...）',
    potential_enhancement TEXT COMMENT '潜能强化效果（如：造成伤害时有30%概率...）',
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '入库时间',
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    -- 外键关联：删除/更新天赋时同步删除/更新详情（注释用-- 说明）
    FOREIGN KEY (talent_id) REFERENCES operator_talent(id) ON DELETE CASCADE ON UPDATE CASCADE
) COMMENT '干员天赋详情表（不同触发条件的效果）';

/* 5. 干员技能表（技能主信息） */
CREATE TABLE operator_skill (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '自增主键',
    name_cn VARCHAR(50) NOT NULL COMMENT '关联干员名称',
    skill_number TINYINT NOT NULL COMMENT '技能编号（1/2/3）',
    skill_name VARCHAR(50) NOT NULL COMMENT '技能名称（如：迅捷打击·γ型）',
    skill_type VARCHAR(50) NOT NULL COMMENT '技能类型（如：自动回复|手动触发）',
    unlock_condition VARCHAR(50) NOT NULL COMMENT '解锁条件（如：精英1/精英2）',
    remark TEXT COMMENT '技能备注（如：※优先选择部署于地面...）',
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '入库时间',
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    -- 外键关联：删除/更新干员时同步删除/更新技能（注释用-- 说明）
    FOREIGN KEY (name_cn) REFERENCES operator_base(name_cn) ON DELETE CASCADE ON UPDATE CASCADE,
    UNIQUE KEY uk_name_skill_number (name_cn, skill_number) COMMENT '干员+技能编号唯一'
) COMMENT '干员技能主信息表';

/* 6. 干员技能等级表（技能不同等级/专精的效果） */
CREATE TABLE operator_skill_level (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '自增主键',
    skill_id INT NOT NULL COMMENT '关联技能表ID',
    level VARCHAR(20) NOT NULL COMMENT '技能等级（如：7/Rank Ⅲ）',
    description TEXT NOT NULL COMMENT '技能效果描述（如：攻击力 +34% ，攻击速度 +35）',
    initial_sp VARCHAR(10) DEFAULT '' COMMENT '初始技力（如：10）',
    sp_cost VARCHAR(10) DEFAULT '' COMMENT '技力消耗（如：39）',
    duration VARCHAR(10) DEFAULT '' COMMENT '持续时间（如：35）',
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '入库时间',
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    -- 外键关联：删除/更新技能时同步删除/更新等级（注释用-- 说明）
    FOREIGN KEY (skill_id) REFERENCES operator_skill(id) ON DELETE CASCADE ON UPDATE CASCADE,
    UNIQUE KEY uk_skill_level (skill_id, level) COMMENT '技能+等级唯一'
) COMMENT '干员技能等级详情表（无材料字段）';

/* 7. 全局术语表（存储通用术语解释） */
CREATE TABLE global_terms (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '自增主键',
    term_name VARCHAR(50) NOT NULL COMMENT '术语名称（如：法术脆弱/禁疗）',
    term_type VARCHAR(20) DEFAULT '' COMMENT '术语类型（如：术语/异常效果/无）',
    term_explanation TEXT NOT NULL COMMENT '术语解释（完整文本）',
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '入库时间',
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    UNIQUE KEY uk_term_name (term_name) COMMENT '术语名称唯一'
) COMMENT '全局通用术语表';

/* 8. 干员-术语关联表（记录干员涉及的术语及出现位置） */
CREATE TABLE operator_term_relation (
    id INT PRIMARY KEY AUTO_INCREMENT COMMENT '自增主键',
    name_cn VARCHAR(50) NOT NULL COMMENT '关联干员名称',
    term_name VARCHAR(50) NOT NULL COMMENT '关联术语名称（对应global_terms.term_name）',
    relation_module VARCHAR(20) NOT NULL COMMENT '术语出现的模块（固定枚举：trait/天赋/技能）',
    module_id VARCHAR(10) DEFAULT '' COMMENT '模块具体ID：trait填空，天赋填1/2，技能填1/2/3',
    create_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP COMMENT '入库时间',
    update_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    -- 外键关联：删除/更新干员/术语时同步删除关联记录（注释用-- 说明）
    -- FOREIGN KEY (name_cn) REFERENCES operator_base(name_cn) ON DELETE CASCADE ON UPDATE CASCADE,
    -- FOREIGN KEY (term_name) REFERENCES global_terms(term_name) ON DELETE CASCADE ON UPDATE CASCADE,
    -- 唯一索引：避免同一干员-术语-模块重复记录
    UNIQUE KEY uk_op_term_module (name_cn, term_name, relation_module, module_id)
) COMMENT '干员-术语关联表（记录每个干员涉及的术语及出现位置）';
