"""
LLM 处理模块：调用大语言模型 API
"""
import requests
from typing import Optional, Tuple, List, Dict

from .config import PodcastConfig
from .parser import smart_parse_script


def call_llm_step(
    config: PodcastConfig,
    prompt: str,
    content: str,
    temperature: float = 0.7,
    max_tokens: int = 2048
) -> Optional[str]:
    """
    调用 LLM API
    
    Args:
        config: 配置对象
        prompt: 系统提示词
        content: 用户输入内容
        temperature: 生成温度
        max_tokens: 最大 token 数
        
    Returns:
        LLM 返回的内容，失败返回 None
    """
    url = "https://api.siliconflow.cn/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": config.llm_model_name,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": content}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=60)
        if response.status_code == 200:
            result = response.json()
            if 'choices' in result:
                return result['choices'][0]['message']['content']
        print(f"❌ LLM API Error: {response.text}")
        return None
    except Exception as e:
        print(f"❌ LLM Exception: {e}")
        return None


def process_article(
    config: PodcastConfig,
    index: int,
    url: str,
    raw_text: str
) -> Tuple[int, str, Optional[str], Optional[List[Dict[str, str]]]]:
    """
    处理单篇文章：分析 + 生成脚本
    
    Args:
        config: 配置对象
        index: 文章索引
        url: 文章 URL
        raw_text: 文章原始内容
        
    Returns:
        (index, url, readable_script, script_json) 元组
    """
    if not raw_text:
        return index, url, None, None

    prompts = config.get_prompts()
    
    print(f"🧠 [Task {index+1}] LLM Analyzing...")
    
    # 第一步：分析文章
    analysis = call_llm_step(
        config,
        prompts["analyst"],
        raw_text[:10000]
    )
    
    if not analysis:
        return index, url, None, None
    
    # 第二步：生成脚本
    script_raw = call_llm_step(
        config,
        prompts["playwright"],
        f"【简报】：\n{analysis}"
    )
    
    # 解析脚本
    script_json = smart_parse_script(script_raw)
    
    if not script_json:
        print(f"\n{'!'*40}")
        print(f"🕵️‍♂️ [DEBUG Task {index+1}] 格式依然错误，请检查 Prompt")
        print(f"📜 原始返回:\n{script_raw[:500] if script_raw else 'None'}")
        print(f"{'!'*40}\n")
        return index, url, None, None
    
    # 生成可读文本
    readable_script = f"Source: {url}\n\n"
    for line in script_json:
        spk = line['speaker']
        txt = line['text']
        readable_script += f"{spk}: {txt}\n"
    readable_script += "\n" + "="*20 + "\n\n"
    
    print(f"✅ [Task {index+1}] Script Ready ({len(script_json)} lines).")
    return index, url, readable_script, script_json
