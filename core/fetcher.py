"""
内容抓取模块：使用 Jina 抓取网页内容
"""
import time
import requests
from typing import Optional, Tuple, Callable


def fetch_content_with_jina(
    url: str, 
    max_retries: int = 3,
    log_func: Callable[[str], None] = print
) -> Optional[str]:
    """
    使用 Jina Reader 抓取网页内容
    """
    url = url.strip()
    jina_url = f"https://r.jina.ai/{url}"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    log_func(f"   📡 Jina URL: {jina_url[:100]}...")
    
    for attempt in range(max_retries):
        try:
            log_func(f"   🔄 [Attempt {attempt+1}/{max_retries}] 发送请求...")
            response = requests.get(jina_url, headers=headers, timeout=30)
            
            log_func(f"   📥 HTTP Status: {response.status_code}")
            
            if response.status_code == 200:
                text = response.text
                if not text:
                    log_func(f"   ⚠️ 返回内容为空")
                    time.sleep(2)
                    continue
                if "High volume" in text:
                    log_func(f"   ⚠️ Jina 繁忙 (High volume)")
                    time.sleep(2)
                    continue
                log_func(f"   ✅ 抓取成功: {len(text)} 字符")
                return text
                
            elif response.status_code == 429:
                wait = (attempt + 1) * 3
                log_func(f"   ⏳ 限流 (429)，等待 {wait}秒...")
                time.sleep(wait)
                continue
                
            else:
                log_func(f"   ❌ HTTP Error: {response.status_code}")
                log_func(f"      Response: {response.text[:300]}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                break
                
        except requests.exceptions.Timeout:
            log_func(f"   ⏱️ 请求超时 (30s)")
            if attempt < max_retries - 1:
                time.sleep(2)
        except requests.exceptions.ConnectionError as e:
            log_func(f"   ❌ 连接错误: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
        except Exception as e:
            log_func(f"   ❌ Exception: {type(e).__name__}: {e}")
            time.sleep(1)
    
    log_func(f"   ❌ 抓取失败，已重试 {max_retries} 次")
    return None


def fetch_with_index(
    task_data: Tuple[int, str],
    log_func: Callable[[str], None] = print
) -> Tuple[int, str, Optional[str]]:
    """
    带索引的抓取任务包装器
    """
    index, url = task_data
    log_func(f"🌍 [Task {index+1}] 开始抓取")
    log_func(f"   URL: {url}")
    text = fetch_content_with_jina(url, log_func=log_func)
    
    if text:
        log_func(f"🌍 [Task {index+1}] ✅ 抓取完成: {len(text)} 字符")
    else:
        log_func(f"🌍 [Task {index+1}] ❌ 抓取失败")
        
    return index, url, text
