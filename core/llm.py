"""
LLM 处理模块：调用大语言模型 API
"""
import requests
from typing import Optional, Tuple, List, Dict, Callable

from .config import PodcastConfig
from .parser import smart_parse_script


def call_llm_api(
    config: PodcastConfig,
    prompt: str,
    content: str,
    step_name: str = "LLM",
    temperature: float = 0.7,
    max_tokens: int = 4096,
    log_func: Callable[[str], None] = print
) -> Optional[str]:
    """
    调用 LLM API（底层函数）
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
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=180)
        
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
                log_func(f"      ❌ [{step_name}] 响应格式异常")
                return None
        else:
            log_func(f"      ❌ [{step_name}] API 错误: {response.status_code}")
            log_func(f"         {response.text[:500]}")
            return None
            
    except requests.exceptions.Timeout:
        log_func(f"      ❌ [{step_name}] 请求超时 (180s)")
        return None
    except Exception as e:
        log_func(f"      ❌ [{step_name}] Exception: {type(e).__name__}: {e}")
        return None


def analyze_article(
    config: PodcastConfig,
    index: int,
    url: str,
    raw_text: str,
    log_func: Callable[[str], None] = print
) -> Tuple[int, str, Optional[str]]:
    """
    分析单篇文章，提取知识点（不生成脚本）
    
    Returns:
        (index, url, analysis) 元组
    """
    if not raw_text:
        log_func(f"🔍 [Article {index+1}] ❌ 输入内容为空")
        return index, url, None

    prompts = config.get_prompts()
    
    log_func(f"🔍 [Article {index+1}] 开始分析")
    log_func(f"   URL: {url}")
    log_func(f"   原文长度: {len(raw_text)} 字符（发送全文，无截断）")
    
    # 分析文章
    analysis = call_llm_api(
        config,
        prompts["analyst"],
        raw_text,  # 发送全文，不截断
        step_name=f"Analyst-{index+1}",
        log_func=log_func
    )
    
    if not analysis:
        log_func(f"🔍 [Article {index+1}] ❌ 分析失败")
        return index, url, None
    
    log_func(f"🔍 [Article {index+1}] ✅ 分析完成，摘要 {len(analysis)} 字符")
    log_func(f"   预览: {analysis[:150]}...")
    
    return index, url, analysis


def generate_unified_script(
    config: PodcastConfig,
    analyses: List[Tuple[int, str, str]],
    log_func: Callable[[str], None] = print
) -> Optional[List[Dict[str, str]]]:
    """
    根据所有文章的分析结果，统一撰写一个完整的播客脚本
    
    Args:
        config: 配置
        analyses: [(index, url, analysis), ...] 列表
        log_func: 日志函数
        
    Returns:
        解析后的脚本 JSON 列表
    """
    log_func(f"")
    log_func(f"{'='*60}")
    log_func(f"✍️ 统一撰写脚本（单线程，保证连贯性）")
    log_func(f"{'='*60}")
    log_func(f"   输入: {len(analyses)} 篇文章的分析结果")
    
    # 构建汇总内容
    combined_content = "以下是多篇文章的分析简报，请根据这些内容撰写一期完整的播客脚本：\n\n"
    
    for idx, url, analysis in analyses:
        combined_content += f"=== 文章 {idx+1} ===\n"
        combined_content += f"来源: {url}\n"
        combined_content += f"分析:\n{analysis}\n\n"
    
    log_func(f"   汇总内容长度: {len(combined_content)} 字符")
    
    prompts = config.get_prompts()
    
    # 修改 playwright prompt，强调要统一撰写
    unified_prompt = prompts["playwright"] + """

**额外要求**：
- 这是一期完整的播客节目，包含多篇文章的内容
- 请在不同文章之间加入自然的过渡语句
- Host A 负责引导话题转换，如"说完了这篇，我们来看下一个有趣的话题..."
- 确保整体风格统一，像一期连贯的节目
- 对话总行数控制在合理范围（每篇文章约5-10行对话）
"""
    
    log_func(f"   调用 LLM 生成统一脚本...")
    
    script_raw = call_llm_api(
        config,
        unified_prompt,
        combined_content,
        step_name="Playwright-Unified",
        max_tokens=8192,  # 更大的输出限制
        log_func=log_func
    )
    
    if not script_raw:
        log_func(f"   ❌ 脚本生成失败")
        return None
    
    log_func(f"   原始脚本长度: {len(script_raw)} 字符")
    log_func(f"   解析 JSON...")
    
    # 解析脚本
    script_json = smart_parse_script(script_raw)
    
    if not script_json:
        log_func(f"   ❌ JSON 解析失败")
        log_func(f"   原始返回:\n{script_raw[:1000]}")
        return None
    
    log_func(f"   ✅ 脚本解析成功，共 {len(script_json)} 行对话")
    
    # 显示脚本预览
    log_func(f"   脚本预览:")
    for i, line in enumerate(script_json[:5]):
        text_preview = line.get('text', '')[:50].replace('\n', ' ')
        log_func(f"      [{i}] {line.get('speaker', '?')}: {text_preview}...")
    if len(script_json) > 5:
        log_func(f"      ... 还有 {len(script_json) - 5} 行")
    
    return script_json
