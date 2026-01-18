"""
内容抓取模块：使用 Jina 抓取网页内容
"""
import time
import requests
from typing import Optional, Tuple


def fetch_content_with_jina(url: str, max_retries: int = 3) -> Optional[str]:
    """
    使用 Jina Reader 抓取网页内容
    
    Args:
        url: 要抓取的 URL
        max_retries: 最大重试次数
        
    Returns:
        抓取到的文本内容，失败返回 None
    """
    url = url.strip()
    jina_url = f"https://r.jina.ai/{url}"
    headers = {"User-Agent": "Mozilla/5.0"}
    
    for attempt in range(max_retries):
        try:
            response = requests.get(jina_url, headers=headers, timeout=20)
            
            if response.status_code == 200:
                text = response.text
                if not text or "High volume" in text:
                    print(f"   ⚠️ [Attempt {attempt+1}] Jina 繁忙。")
                    time.sleep(2)
                    continue
                return text
                
            elif response.status_code == 429:
                wait = (attempt + 1) * 2
                print(f"      ⏳ Jina 限流 (429)，等待 {wait}秒...")
                time.sleep(wait)
                continue
                
            else:
                print(f"      ❌ Jina Error: {response.status_code}")
                break
                
        except Exception as e:
            print(f"      ⚠️ Exception: {e}")
            time.sleep(1)
            
    return None


def fetch_with_index(task_data: Tuple[int, str]) -> Tuple[int, str, Optional[str]]:
    """
    带索引的抓取任务包装器
    
    Args:
        task_data: (index, url) 元组
        
    Returns:
        (index, url, content) 元组
    """
    index, url = task_data
    print(f"🌍 [Task {index+1}] Fetching: {url[:50]}...")
    text = fetch_content_with_jina(url)
    return index, url, text
