# operators_list_get.py
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import time
import json
import requests
from bs4 import BeautifulSoup
from config import HEADERS, OPERATOR_LIST_CONFIG, JSON_OUTPUT_DIR
from utils import logger, ensure_output_dir

class OperatorListCrawler:
    """干员一览爬取器（轻量类封装，无状态）"""
    def __init__(self):
        self.url = OPERATOR_LIST_CONFIG["url"]
        self.headers = HEADERS
        self.attr_mapping = OPERATOR_LIST_CONFIG["attr_mapping"]
        self.output_dir = JSON_OUTPUT_DIR
        self.output_filename = OPERATOR_LIST_CONFIG["json_output"]

    def fetch(self) -> str:
        """抓取干员一览页面HTML"""
        try:
            resp = requests.get(self.url, headers=self.headers, timeout=30)
            resp.raise_for_status()
            resp.encoding = 'utf-8'
            logger.info(f"✅ 成功获取干员一览页面：{self.url}")
            return resp.text
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ 网络请求失败：{str(e)}（检查网络或URL是否有效）")
            raise

    def parse(self, html: str) -> list[dict]:
        """解析干员一览数据"""
        soup = BeautifulSoup(html, 'lxml')
        data_container = soup.select_one('div#filter-data')
        if not data_container:
            raise RuntimeError('❌ 页面结构变更：未找到核心数据容器 <div id="filter-data">')
        
        ops_list = []
        # 遍历每个干员的div节点（仅直接子节点，避免递归）
        for op_div in data_container.find_all('div', recursive=False):
            # 提取原始属性值
            raw_data = {attr: op_div.get(attr, '').strip() for attr in self.attr_mapping.keys()}
            
            # 关键修正：稀有度+1（PRTS原始数据是0-5，对应1-6星）
            raw_rarity = raw_data['data-rarity'] or '0'
            raw_data['data-rarity'] = str(int(raw_rarity) + 1)
            
            # 映射为规范的英文字段
            op_data = {self.attr_mapping[old_key]: value for old_key, value in raw_data.items()}
            ops_list.append(op_data)
        
        logger.info(f"📊 解析完成：共提取 {len(ops_list)} 名干员基础信息")
        return ops_list

    def save(self, ops_list: list[dict]):
        """保存干员一览数据到JSON"""
        # 排序规则：稀有度降序（6星在前）→ 中文名升序（拼音排序）
        ops_list.sort(key=lambda x: (-int(x['rarity']), x['name_cn']))
        
        # 构造最终的JSON数据结构
        final_json = {
            "meta_info": {  # 元信息（基础统计）
                "update_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
                "total_operators": len(ops_list),
                "data_source": self.url
            },
            "operators": ops_list  # 干员数据列表（核心数据）
        }
        
        # 确保输出目录存在
        ensure_output_dir()
        output_path = f"{self.output_dir}/{self.output_filename}"
        
        # 写入JSON文件
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(final_json, f, ensure_ascii=False, indent=2)
        
        logger.info(f"✅ 干员一览数据保存完成！文件路径：{output_path}")
        logger.info(f"📊 抓取统计：共 {len(ops_list)} 名干员")

    def run(self) -> list[dict]:
        """一键执行：抓取→解析→保存"""
        logger.info("=== 开始抓取PRTS干员一览数据 ===")
        try:
            html = self.fetch()
            ops_data = self.parse(html)
            self.save(ops_data)
            return ops_data
        except RuntimeError as e:
            logger.error(f"❌ 数据解析失败：{str(e)}（可能是PRTS页面结构变更）")
            raise
        except Exception as e:
            logger.error(f"❌ 程序执行失败：{type(e).__name__} - {str(e)}")
            raise

# 保留独立执行入口（方便单独调试）
if __name__ == '__main__':
    crawler = OperatorListCrawler()
    crawler.run()