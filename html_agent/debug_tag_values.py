#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
简单测试：检查 get_tag_values() 返回的数据结构
"""

import sys
import json
import os

os.chdir(r"c:\Users\fshyit02\Winpython64-3.12.9.0dot\Yiting\html_agent")

from metris import get_tag_values

# Tag IDs to test
tag_ids_to_test = [5, 6, 7, 8]

print("\n" + "="*70)
print("测试 get_tag_values() 返回的数据结构")
print("="*70)

for tag_id in tag_ids_to_test:
    print(f"\n【测试 Tag ID: {tag_id}】")
    try:
        result = get_tag_values(tag_id)
        print(f"✓ 成功获取数据")
        print(f"  类型: {type(result).__name__}")
        print(f"  内容:\n{json.dumps(result, indent=4, ensure_ascii=False, default=str)}")
        
        if isinstance(result, dict):
            print(f"\n  📋 可用字段: {list(result.keys())}")
        
    except Exception as e:
        print(f"✗ 错误: {type(e).__name__}")
        print(f"  消息: {str(e)}")

print("\n" + "="*70)
