"""
解析器模块：解析 LLM 返回的脚本 JSON
"""
import json
import re
from typing import List, Dict, Optional


def clean_json_text(text: str) -> str:
    """清理 JSON 文本中的 markdown 代码块标记"""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(json)?", "", text, flags=re.MULTILINE)
    if text.endswith("```"):
        text = re.sub(r"```$", "", text, flags=re.MULTILINE)
    return text.strip()


def parse_dialogue_regex_strict(raw_text: str) -> List[Dict[str, str]]:
    """
    最后的防线：只匹配标准的 JSON Key 格式
    """
    script_list = []
    try:
        pattern = r'"speaker"\s*:\s*"(Host [AB])".*?"text"\s*:\s*"(.*?)"'
        matches = re.findall(pattern, raw_text, re.DOTALL)
        if matches:
            print(f"   🛡️ [Regex] 提取到 {len(matches)} 行标准对话。")
            for spk, txt in matches:
                script_list.append({"speaker": spk, "text": txt})
            return script_list
    except Exception:
        pass
    return []


def smart_parse_script(raw_text: str) -> List[Dict[str, str]]:
    """
    智能解析脚本 JSON
    
    信任 Prompt 会输出标准的 [{"speaker": "...", "text": "..."}]
    不再进行任何 'Key Guessing'。
    
    Args:
        raw_text: LLM 返回的原始文本
        
    Returns:
        解析后的对话列表
    """
    if not raw_text:
        return []
        
    clean_text = clean_json_text(raw_text)
    
    try:
        data = json.loads(clean_text)
        
        # 兼容: 如果最外层是 dict (例如 {"script": [...]})
        if isinstance(data, dict):
            for k in ['script', 'dialogue', 'content']:
                if k in data and isinstance(data[k], list):
                    data = data[k]
                    break
        
        # 校验: 必须是 list
        if not isinstance(data, list):
            raise ValueError("Output is not a JSON List")
            
        # 校验: 元素必须包含 speaker 和 text
        valid_data = []
        for item in data:
            if isinstance(item, dict) and 'speaker' in item and 'text' in item:
                valid_data.append(item)
        
        if not valid_data:
            raise ValueError("List contains invalid items (missing speaker/text)")
             
        return valid_data

    except Exception as e:
        print(f"   ⚠️ 解析失败: {e}")
        # 保留唯一的 '暴力兜底'，以防万一 JSON 格式坏了一点点
        return parse_dialogue_regex_strict(raw_text)
