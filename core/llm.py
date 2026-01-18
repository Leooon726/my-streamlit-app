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
    step_name: str = "LLM",
    temperature: float = 0.7,
    max_tokens: int = 2048
) -> Optional[str]:
    """
    调用 LLM API
    
    Args:
        config: 配置对象
        prompt: 系统提示词
        content: 用户输入内容
        step_name: 步骤名称（用于日志）
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
    
    print(f"      📤 [{step_name}] 调用模型: {config.llm_model_name}")
    print(f"      📤 [{step_name}] 输入长度: {len(content)} 字符")
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=120)
        
        print(f"      📥 [{step_name}] HTTP Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            if 'choices' in result and len(result['choices']) > 0:
                output = result['choices'][0]['message']['content']
                print(f"      ✅ [{step_name}] 成功，输出长度: {len(output)} 字符")
                
                # 显示 token 使用情况
                if 'usage' in result:
                    usage = result['usage']
                    print(f"      📊 [{step_name}] Tokens: prompt={usage.get('prompt_tokens', '?')}, completion={usage.get('completion_tokens', '?')}, total={usage.get('total_tokens', '?')}")
                
                return output
            else:
                print(f"      ❌ [{step_name}] 响应格式异常: {result}")
                return None
        else:
            print(f"      ❌ [{step_name}] API 错误:")
            print(f"         Status: {response.status_code}")
            print(f"         Response: {response.text[:500]}")
            return None
            
    except requests.exceptions.Timeout:
        print(f"      ❌ [{step_name}] 请求超时 (120s)")
        return None
    except Exception as e:
        print(f"      ❌ [{step_name}] Exception: {type(e).__name__}: {e}")
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
        print(f"🧠 [Task {index+1}] ❌ 输入内容为空")
        return index, url, None, None

    prompts = config.get_prompts()
    
    print(f"🧠 [Task {index+1}] 开始处理: {url[:60]}...")
    print(f"   📄 原文长度: {len(raw_text)} 字符 (截取前 10000)")
    
    # 第一步：分析文章
    print(f"   🔍 Step 1: 文章分析...")
    analysis = call_llm_step(
        config,
        prompts["analyst"],
        raw_text[:10000],
        step_name="Analyst"
    )
    
    if not analysis:
        print(f"🧠 [Task {index+1}] ❌ 文章分析失败")
        return index, url, None, None
    
    # 第二步：生成脚本
    print(f"   ✍️ Step 2: 生成脚本...")
    script_raw = call_llm_step(
        config,
        prompts["playwright"],
        f"【简报】：\n{analysis}",
        step_name="Playwright"
    )
    
    if not script_raw:
        print(f"🧠 [Task {index+1}] ❌ 脚本生成失败")
        return index, url, None, None
    
    # 解析脚本
    print(f"   🔧 Step 3: 解析脚本 JSON...")
    script_json = smart_parse_script(script_raw)
    
    if not script_json:
        print(f"🧠 [Task {index+1}] ❌ 脚本解析失败")
        print(f"{'!'*50}")
        print(f"📜 原始返回 (前 800 字符):")
        print(script_raw[:800] if script_raw else 'None')
        print(f"{'!'*50}")
        return index, url, None, None
    
    # 生成可读文本
    readable_script = f"Source: {url}\n\n"
    for line in script_json:
        spk = line['speaker']
        txt = line['text']
        readable_script += f"{spk}: {txt}\n"
    readable_script += "\n" + "="*20 + "\n\n"
    
    print(f"🧠 [Task {index+1}] ✅ 处理完成，生成 {len(script_json)} 行对话")
    return index, url, readable_script, script_json
