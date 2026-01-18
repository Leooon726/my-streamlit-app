"""
LLM 处理模块：调用大语言模型 API
"""
import requests
from typing import Optional, Tuple, List, Dict, Callable

from .config import PodcastConfig
from .parser import smart_parse_script


def call_llm_step(
    config: PodcastConfig,
    prompt: str,
    content: str,
    step_name: str = "LLM",
    temperature: float = 0.7,
    max_tokens: int = 2048,
    log_func: Callable[[str], None] = print
) -> Optional[str]:
    """
    调用 LLM API
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
    
    log_func(f"      📤 [{step_name}] 调用 API...")
    log_func(f"         Model: {config.llm_model_name}")
    log_func(f"         Input: {len(content)} 字符")
    log_func(f"         Prompt: {len(prompt)} 字符")
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=120)
        
        log_func(f"      📥 [{step_name}] HTTP {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            if 'choices' in result and len(result['choices']) > 0:
                output = result['choices'][0]['message']['content']
                log_func(f"      ✅ [{step_name}] 成功，输出 {len(output)} 字符")
                
                if 'usage' in result:
                    usage = result['usage']
                    log_func(f"         Tokens: prompt={usage.get('prompt_tokens', '?')}, completion={usage.get('completion_tokens', '?')}, total={usage.get('total_tokens', '?')}")
                
                return output
            else:
                log_func(f"      ❌ [{step_name}] 响应格式异常:")
                log_func(f"         {str(result)[:500]}")
                return None
        else:
            log_func(f"      ❌ [{step_name}] API 错误:")
            log_func(f"         Status: {response.status_code}")
            log_func(f"         Response: {response.text[:500]}")
            return None
            
    except requests.exceptions.Timeout:
        log_func(f"      ❌ [{step_name}] 请求超时 (120s)")
        return None
    except Exception as e:
        log_func(f"      ❌ [{step_name}] Exception: {type(e).__name__}: {e}")
        return None


def process_article(
    config: PodcastConfig,
    index: int,
    url: str,
    raw_text: str,
    log_func: Callable[[str], None] = print
) -> Tuple[int, str, Optional[str], Optional[List[Dict[str, str]]]]:
    """
    处理单篇文章：分析 + 生成脚本
    """
    if not raw_text:
        log_func(f"🧠 [Task {index+1}] ❌ 输入内容为空")
        return index, url, None, None

    prompts = config.get_prompts()
    
    log_func(f"🧠 [Task {index+1}] 开始处理")
    log_func(f"   URL: {url}")
    log_func(f"   原文: {len(raw_text)} 字符 (截取前 10000)")
    
    # 第一步：分析文章
    log_func(f"   🔍 Step 1/3: 文章分析...")
    analysis = call_llm_step(
        config,
        prompts["analyst"],
        raw_text[:10000],
        step_name="Analyst",
        log_func=log_func
    )
    
    if not analysis:
        log_func(f"🧠 [Task {index+1}] ❌ 文章分析失败")
        return index, url, None, None
    
    log_func(f"   📝 分析结果预览: {analysis[:200]}...")
    
    # 第二步：生成脚本
    log_func(f"   ✍️ Step 2/3: 生成脚本...")
    script_raw = call_llm_step(
        config,
        prompts["playwright"],
        f"【简报】：\n{analysis}",
        step_name="Playwright",
        log_func=log_func
    )
    
    if not script_raw:
        log_func(f"🧠 [Task {index+1}] ❌ 脚本生成失败")
        return index, url, None, None
    
    log_func(f"   📝 脚本原始输出预览: {script_raw[:300]}...")
    
    # 第三步：解析脚本
    log_func(f"   🔧 Step 3/3: 解析 JSON...")
    script_json = smart_parse_script(script_raw)
    
    if not script_json:
        log_func(f"🧠 [Task {index+1}] ❌ JSON 解析失败")
        log_func(f"{'!'*50}")
        log_func(f"📜 完整原始返回:")
        log_func(script_raw if script_raw else 'None')
        log_func(f"{'!'*50}")
        return index, url, None, None
    
    # 生成可读文本
    readable_script = f"Source: {url}\n\n"
    for line in script_json:
        spk = line['speaker']
        txt = line['text']
        readable_script += f"{spk}: {txt}\n"
    readable_script += "\n" + "="*20 + "\n\n"
    
    log_func(f"🧠 [Task {index+1}] ✅ 完成，生成 {len(script_json)} 行对话")
    return index, url, readable_script, script_json
