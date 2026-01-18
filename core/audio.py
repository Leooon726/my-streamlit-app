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
) -> Tuple[int, Optional[bytes], Optional[str]]:
    """
    生成单段音频
    
    Args:
        config: 配置对象
        index: 段落索引
        text: 要转换的文本
        speaker: 说话人标识
        
    Returns:
        (index, audio_bytes, error_message) 元组
    """
    if not text or len(text.strip()) == 0:
        return index, None, "文本为空"
        
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
        voice_id = config.voice_a_full
        print(f"      ⚠️ [Segment {index}] 未知 speaker '{speaker}'，使用默认音色 A")

    payload = {
        "model": config.tts_model_name,
        "input": text,
        "voice": voice_id,
        "response_format": "mp3",
        "stream": False
    }
    
    text_preview = text[:30] + "..." if len(text) > 30 else text
    print(f"      🎤 [Segment {index}] {speaker} -> {voice_id}")
    print(f"         文本: {text_preview}")
    
    last_error = ""
    for attempt in range(3):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=60)
            
            if response.status_code == 200:
                content = response.content
                if content and len(content) > 0:
                    print(f"      ✅ [Segment {index}] 成功，音频大小: {len(content)} bytes")
                    return index, content, None
                else:
                    last_error = "返回内容为空"
                    print(f"      ⚠️ [Segment {index}] 返回内容为空")
                    
            elif response.status_code == 429:
                wait = 2 + attempt * 2
                print(f"      ⏳ [Segment {index}] 限流 (429)，等待 {wait}秒... [Attempt {attempt+1}/3]")
                time.sleep(wait)
                last_error = "API 限流"
                continue
                
            elif response.status_code == 400:
                error_detail = response.text[:300]
                print(f"      ❌ [Segment {index}] 请求错误 (400):")
                print(f"         {error_detail}")
                last_error = f"400: {error_detail}"
                break  # 400 错误不重试
                
            elif response.status_code == 401:
                print(f"      ❌ [Segment {index}] 认证失败 (401): API Key 无效或过期")
                last_error = "API Key 无效"
                break  # 认证错误不重试
                
            else:
                error_detail = response.text[:300]
                print(f"      ❌ [Segment {index}] HTTP {response.status_code}:")
                print(f"         {error_detail}")
                last_error = f"HTTP {response.status_code}"
                if attempt < 2:
                    time.sleep(1)
                    
        except requests.exceptions.Timeout:
            print(f"      ⏱️ [Segment {index}] 请求超时 [Attempt {attempt+1}/3]")
            last_error = "请求超时"
            if attempt < 2:
                time.sleep(1)
        except Exception as e:
            print(f"      ❌ [Segment {index}] Exception: {type(e).__name__}: {e}")
            last_error = str(e)
            break
    
    print(f"      ❌ [Segment {index}] 最终失败: {last_error}")
    return index, None, last_error


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
    print(f"   📋 脚本共 {len(script_json)} 行，开始 TTS 合成...")
    print(f"   🔧 TTS 模型: {config.tts_model_name}")
    print(f"   🎤 音色 A: {config.voice_a_full}")
    print(f"   🎤 音色 B: {config.voice_b_full}")
    
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
        
        print(f"   📤 已提交 {len(future_to_index)} 个 TTS 任务")
                
        results = []
        errors = []
        completed = 0
        total = len(future_to_index)
        
        for future in as_completed(future_to_index):
            idx, audio_data, error = future.result()
            completed += 1
            
            if progress_callback:
                progress_callback(completed, total)
                
            if audio_data:
                results.append((idx, audio_data))
            else:
                errors.append((idx, error))
    
    # 统计结果
    print(f"   📊 TTS 完成: 成功 {len(results)}/{total}, 失败 {len(errors)}/{total}")
    
    if errors:
        print(f"   ⚠️ 失败的段落:")
        for idx, err in errors[:5]:  # 只显示前5个错误
            print(f"      - Segment {idx}: {err}")
        if len(errors) > 5:
            print(f"      ... 还有 {len(errors) - 5} 个错误")
                
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
            print(f"   ⚠️ 合成 Segment {idx} 失败: {type(e).__name__}: {e}")
    
    duration_sec = len(full_track) / 1000
    print(f"   🎵 最终音频时长: {duration_sec:.1f} 秒")
            
    return full_track
