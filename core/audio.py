"""
音频生成模块：使用 TTS API 生成播客音频
"""
import io
import time
import requests
from typing import Optional, Tuple, List, Dict
from concurrent.futures import ThreadPoolExecutor, as_completed

from pydub import AudioSegment

from .config import PodcastConfig


def generate_audio_segment(
    config: PodcastConfig,
    index: int,
    text: str,
    speaker: str
) -> Tuple[int, Optional[bytes]]:
    """
    生成单段音频
    
    Args:
        config: 配置对象
        index: 段落索引
        text: 要转换的文本
        speaker: 说话人标识
        
    Returns:
        (index, audio_bytes) 元组
    """
    if not text or len(text.strip()) == 0:
        return index, None
        
    url = "https://api.siliconflow.cn/v1/audio/speech"
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json"
    }
    
    spk_lower = str(speaker).lower()
    
    # 简单明确的分配
    if "host a" in spk_lower or config.voice_name_host_a.lower() in spk_lower:
        voice_id = config.voice_a_full
    elif "host b" in spk_lower or config.voice_name_host_b.lower() in spk_lower:
        voice_id = config.voice_b_full
    else:
        # 默认给 A，防止 Unknown 导致静音
        print(f"   ⚠️ [Row {index}] Unknown speaker '{speaker}', defaulting to A.")
        voice_id = config.voice_a_full

    payload = {
        "model": config.tts_model_name,
        "input": text,
        "voice": voice_id,
        "response_format": "mp3",
        "stream": False
    }
    
    for attempt in range(3):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            if response.status_code == 200:
                return index, response.content
            elif response.status_code == 429:
                time.sleep(1 + attempt)
                continue
            else:
                if attempt == 2:
                    print(f"   ❌ TTS Fail: {response.text}")
                break
        except Exception as e:
            print(f"   ❌ TTS Except: {e}")
            break
            
    return index, None


def generate_audio_for_script(
    config: PodcastConfig,
    script_json: List[Dict[str, str]],
    progress_callback=None
) -> AudioSegment:
    """
    为整个脚本生成音频
    
    Args:
        config: 配置对象
        script_json: 脚本 JSON 列表
        progress_callback: 进度回调函数 (current, total)
        
    Returns:
        合成后的 AudioSegment
    """
    with ThreadPoolExecutor(max_workers=config.max_workers_tts) as executor:
        future_to_index = {}
        
        for i, line in enumerate(script_json):
            txt = line.get('text', '')
            if txt:
                future = executor.submit(
                    generate_audio_segment,
                    config,
                    i,
                    txt,
                    line.get('speaker', '')
                )
                future_to_index[future] = i
                
        results = []
        completed = 0
        total = len(future_to_index)
        
        for future in as_completed(future_to_index):
            idx, audio_data = future.result()
            completed += 1
            
            if progress_callback:
                progress_callback(completed, total)
                
            if audio_data:
                results.append((idx, audio_data))
                
    # 按顺序排列
    results.sort(key=lambda x: x[0])
    
    # 合成音频
    full_track = AudioSegment.empty()
    pause = AudioSegment.silent(duration=400)
    
    for idx, audio_bytes in results:
        try:
            seg = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
            full_track += seg + pause
        except Exception as e:
            print(f"   ⚠️ Failed to process audio segment {idx}: {e}")
            
    return full_track
