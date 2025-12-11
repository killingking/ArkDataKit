#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
在线抓取 prts.wiki 干员一览（稀有度+1修正）
输出 JSON 格式（规范英文字段，字段含义仅在代码内注释）
pip install requests beautifulsoup4
"""

import time
import json
import requests
from bs4 import BeautifulSoup

# 配置项
URL = 'https://prts.wiki/w/干员一览'
JSON_FILE = 'operators.json'  # JSON输出文件
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# 原始HTML属性名 → 规范英文字段名（代码内注释说明字段含义，不输出到JSON）
# --- 字段含义注释 ---
# name_cn: 干员中文名称（如：令、浊心斯卡蒂）
# rarity: 稀有度（PRTS原始值0-5，已+1修正为1-6星，对应1★-6★）
# profession: 干员主职业（如：先锋、医疗、近卫、重装）
# sub_profession: 职业分支（如：驭械术师、深海治疗师、术战者）
# faction: 所属阵营（如：炎、深海猎人、罗德岛、莱茵生命）
# gender: 性别（值仅为：男/女/无）
# position: 部署位置（值仅为：远程/近战）
# tags: 干员标签（多个标签用中文逗号分隔，如：费用回复,输出,召唤）
ATTR_MAPPING = {
    'data-zh': 'name_cn',          # 干员中文名
    'data-rarity': 'rarity',       # 稀有度（1-6星）
    'data-profession': 'profession',# 主职业
    'data-subprofession': 'sub_profession', # 职业分支
    'data-logo': 'faction',        # 所属阵营
    'data-sex': 'gender',          # 性别
    'data-position': 'position',   # 部署位置
    'data-tag': 'tags'             # 干员标签
}

def fetch_html() -> str:
    """获取prts干员一览页面的HTML源码"""
    resp = requests.get(URL, headers=HEADERS, timeout=30)
    resp.raise_for_status()  # 捕获HTTP请求错误（如404/500）
    resp.encoding = 'utf-8'  # 强制UTF-8编码，避免中文乱码
    return resp.text

def parse_ops(html: str) -> list[dict]:
    """
    解析干员数据
    :param html: 页面HTML源码
    :return: 干员数据列表（每个元素为英文字段的字典）
    """
    soup = BeautifulSoup(html, 'lxml')
    # 定位干员数据核心容器（PRTS页面的干员数据都在这个div里）
    data_container = soup.select_one('div#filter-data')
    if not data_container:
        raise RuntimeError('页面结构变更：未找到核心数据容器 <div id="filter-data">')
    
    ops_list = []
    # 遍历每个干员的div节点（仅直接子节点，避免递归）
    for op_div in data_container.find_all('div', recursive=False):
        # 提取原始属性值
        raw_data = {attr: op_div.get(attr, '').strip() for attr in ATTR_MAPPING.keys()}
        
        # 关键修正：稀有度+1（PRTS原始数据是0-5，对应1-6星）
        raw_rarity = raw_data['data-rarity'] or '0'
        raw_data['data-rarity'] = str(int(raw_rarity) + 1)
        
        # 映射为规范的英文字段
        op_data = {ATTR_MAPPING[old_key]: value for old_key, value in raw_data.items()}
        ops_list.append(op_data)
    
    return ops_list

def save_json(ops_list: list[dict]):
    """
    将干员数据保存为JSON文件（简洁结构，仅含元信息+干员列表）
    :param ops_list: 解析后的干员数据列表
    """
    # 排序规则：稀有度降序（6星在前）→ 中文名升序（拼音排序）
    ops_list.sort(key=lambda x: (-int(x['rarity']), x['name_cn']))
    
    # 构造最终的JSON数据结构（仅保留元信息+干员列表，无额外注释节点）
    final_json = {
        "meta_info": {  # 元信息（基础统计）
            "update_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            "total_operators": len(ops_list),
            "data_source": URL
        },
        "operators": ops_list  # 干员数据列表（核心数据）
    }
    
    # 写入JSON文件（ensure_ascii=False保留中文，indent=2格式化）
    with open(JSON_FILE, 'w', encoding='utf-8') as f:
        json.dump(final_json, f, ensure_ascii=False, indent=2)
    
    # 输出执行结果
    print(f"✅ 数据保存完成！文件路径：{JSON_FILE}")
    print(f"📊 抓取统计：共 {len(ops_list)} 名干员")

def main():
    """主执行流程（异常捕获+友好提示）"""
    try:
        print("🔍 开始抓取PRTS干员数据...")
        html = fetch_html()
        ops_data = parse_ops(html)
        save_json(ops_data)
    except requests.exceptions.RequestException as e:
        print(f"❌ 网络请求失败：{str(e)}（检查网络或URL是否有效）")
    except RuntimeError as e:
        print(f"❌ 数据解析失败：{str(e)}（可能是PRTS页面结构变更）")
    except Exception as e:
        print(f"❌ 程序执行失败：{type(e).__name__} - {str(e)}")

if __name__ == '__main__':
    main()