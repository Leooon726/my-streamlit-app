"""
音频生成模块：使用 TTS API 生成播客音频
"""
import io
import time
import requests
from typing import Optional, Tuple, List, Dict, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed

from pydub import AudioSegment

from .config import PodcastConfig


def generate_audio_segment(
    config: PodcastConfig,
    index: int,
    text: str,
    speaker: str,
    log_func: Callable[[str], None] = print
) -> Tuple[int, Optional[bytes], Optional[str]]:
    """
    生成单段音频
    """
    if not text or len(text.strip()) == 0:
        return index, None, "文本为空"
        
    url = "https://api.siliconflow.cn/v1/audio/speech"
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json"
    }
    
    spk_lower = str(speaker).lower()
    
    # 分配音色
    if "host a" in spk_lower or config.voice_name_host_a.lower() in spk_lower:
        voice_id = config.voice_a_full
    elif "host b" in spk_lower or config.voice_name_host_b.lower() in spk_lower:
        voice_id = config.voice_b_full
    else:
        voice_id = config.voice_a_full

    payload = {
        "model": config.tts_model_name,
        "input": text,
        "voice": voice_id,
        "response_format": "mp3",
        "stream": False
    }
    
    text_preview = text[:40].replace('\n', ' ') + ("..." if len(text) > 40 else "")
    log_func(f"      🎤 [Seg {index}] {speaker} | {text_preview}")
    
    last_error = ""
    for attempt in range(3):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=60)
            
            if response.status_code == 200:
                content = response.content
                if content and len(content) > 100:
                    log_func(f"      ✅ [Seg {index}] {len(content)} bytes")
                    return index, content, None
                else:
                    try:
                        error_text = content.decode('utf-8')[:200]
                        last_error = f"返回异常: {error_text}"
                    except:
                        last_error = f"返回太小: {len(content)} bytes"
                    
            elif response.status_code == 429:
                wait = 2 + attempt * 2
                log_func(f"      ⏳ [Seg {index}] 限流，等待 {wait}s...")
                time.sleep(wait)
                last_error = "API 限流"
                continue
                
            else:
                error_text = response.text[:200]
                log_func(f"      ❌ [Seg {index}] HTTP {response.status_code}: {error_text}")
                last_error = f"HTTP {response.status_code}"
                break
                    
        except requests.exceptions.Timeout:
            log_func(f"      ⏱️ [Seg {index}] 超时 [Attempt {attempt+1}/3]")
            last_error = "超时"
        except Exception as e:
            log_func(f"      ❌ [Seg {index}] {type(e).__name__}: {e}")
            last_error = str(e)
            break
    
    return index, None, last_error


def generate_audio_parallel(
    config: PodcastConfig,
    script_json: List[Dict[str, str]],
    log_func: Callable[[str], None] = print
) -> Tuple[List[Tuple[int, bytes]], List[Tuple[int, str]]]:
    """
    并行生成所有音频段
    
    Returns:
        (成功列表, 失败列表)
    """
    log_func(f"   🚀 并行 TTS 生成")
    log_func(f"      Workers: {config.max_workers_tts}")
    log_func(f"      Segments: {len(script_json)}")
    log_func(f"      Model: {config.tts_model_name}")
    log_func(f"      Voice A: {config.voice_a_full}")
    log_func(f"      Voice B: {config.voice_b_full}")
    log_func(f"")
    
    results = []
    errors = []
    
    # 过滤有效 segments
    valid_segments = []
    for i, line in enumerate(script_json):
        txt = line.get('text', '')
        if txt and txt.strip():
            valid_segments.append((i, txt, line.get('speaker', '')))
    
    log_func(f"   📤 提交 {len(valid_segments)} 个 TTS 任务...")
    
    # 并行执行
    with ThreadPoolExecutor(max_workers=config.max_workers_tts) as executor:
        futures = {}
        for i, txt, speaker in valid_segments:
            future = executor.submit(
                generate_audio_segment,
                config, i, txt, speaker, log_func
            )
            futures[future] = i
        
        completed = 0
        total = len(futures)
        
        for future in as_completed(futures):
            completed += 1
            idx, audio_data, error = future.result()
            
            if audio_data:
                results.append((idx, audio_data))
            else:
                errors.append((idx, error or "未知错误"))
            
            # 每完成 5 个或全部完成时汇报进度
            if completed % 5 == 0 or completed == total:
                log_func(f"   📊 TTS 进度: {completed}/{total}")
    
    log_func(f"")
    log_func(f"   {'='*40}")
    log_func(f"   📊 TTS 并行生成完成")
    log_func(f"      成功: {len(results)}/{total}")
    log_func(f"      失败: {len(errors)}/{total}")
    
    if errors:
        log_func(f"   ⚠️ 失败详情:")
        for idx, err in errors[:5]:
            log_func(f"      - Segment {idx}: {err}")
        if len(errors) > 5:
            log_func(f"      ... 还有 {len(errors) - 5} 个")
    
    log_func(f"   {'='*40}")
    
    return results, errors


def merge_audio_segments(
    audio_segments: List[Tuple[int, bytes]],
    log_func: Callable[[str], None] = print
) -> AudioSegment:
    """
    按顺序合并音频段（单线程）
    
    Args:
        audio_segments: [(index, audio_bytes), ...] 列表
        log_func: 日志函数
        
    Returns:
        合并后的 AudioSegment
    """
    log_func(f"")
    log_func(f"   🔧 单线程合并音频（按顺序拼接）")
    log_func(f"      待合并: {len(audio_segments)} 个片段")
    
    # 按 index 排序
    sorted_segments = sorted(audio_segments, key=lambda x: x[0])
    
    full_track = AudioSegment.empty()
    pause = AudioSegment.silent(duration=400)  # 400ms 停顿
    
    success_count = 0
    fail_count = 0
    
    for idx, audio_bytes in sorted_segments:
        try:
            seg = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
            full_track += seg + pause
            success_count += 1
            log_func(f"      ✅ Segment {idx}: {len(seg)}ms")
        except Exception as e:
            fail_count += 1
            log_func(f"      ❌ Segment {idx}: {type(e).__name__}: {e}")
    
    duration_sec = len(full_track) / 1000
    log_func(f"")
    log_func(f"   🎵 合并完成")
    log_func(f"      成功片段: {success_count}")
    log_func(f"      失败片段: {fail_count}")
    log_func(f"      总时长: {duration_sec:.1f} 秒")
    
    return full_track
