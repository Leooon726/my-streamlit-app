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
        log_func(f"      ⚠️ [Segment {index}] 文本为空，跳过")
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
        log_func(f"      ⚠️ [Segment {index}] 未知 speaker '{speaker}'，使用默认音色 A")

    payload = {
        "model": config.tts_model_name,
        "input": text,
        "voice": voice_id,
        "response_format": "mp3",
        "stream": False
    }
    
    text_preview = text[:50].replace('\n', ' ') + ("..." if len(text) > 50 else "")
    log_func(f"      🎤 [Segment {index}] Speaker: {speaker}")
    log_func(f"         Voice: {voice_id}")
    log_func(f"         Text: {text_preview}")
    log_func(f"         Model: {config.tts_model_name}")
    
    last_error = ""
    for attempt in range(3):
        try:
            log_func(f"         📤 发送请求... [Attempt {attempt+1}/3]")
            response = requests.post(url, json=payload, headers=headers, timeout=60)
            
            log_func(f"         📥 HTTP Status: {response.status_code}")
            
            if response.status_code == 200:
                content = response.content
                content_type = response.headers.get('Content-Type', 'unknown')
                log_func(f"         Content-Type: {content_type}")
                log_func(f"         Content-Length: {len(content)} bytes")
                
                if content and len(content) > 100:  # MP3 至少应该有几百字节
                    log_func(f"      ✅ [Segment {index}] 成功!")
                    return index, content, None
                else:
                    # 可能返回的是错误信息而不是音频
                    try:
                        error_text = content.decode('utf-8')[:500]
                        log_func(f"      ❌ [Segment {index}] 返回内容太小，可能是错误:")
                        log_func(f"         {error_text}")
                        last_error = f"返回内容异常: {error_text[:100]}"
                    except:
                        log_func(f"      ❌ [Segment {index}] 返回内容太小: {len(content)} bytes")
                        last_error = f"返回内容太小: {len(content)} bytes"
                    
            elif response.status_code == 429:
                wait = 2 + attempt * 2
                log_func(f"      ⏳ [Segment {index}] 限流 (429)，等待 {wait}秒...")
                time.sleep(wait)
                last_error = "API 限流"
                continue
                
            elif response.status_code == 400:
                error_text = response.text[:500]
                log_func(f"      ❌ [Segment {index}] 请求错误 (400):")
                log_func(f"         {error_text}")
                last_error = f"400 Bad Request: {error_text[:200]}"
                break
                
            elif response.status_code == 401:
                log_func(f"      ❌ [Segment {index}] 认证失败 (401)")
                log_func(f"         API Key 可能无效或已过期")
                last_error = "API Key 无效 (401)"
                break
                
            elif response.status_code == 404:
                error_text = response.text[:500]
                log_func(f"      ❌ [Segment {index}] 资源不存在 (404):")
                log_func(f"         {error_text}")
                log_func(f"         可能是模型名称或音色 ID 错误")
                last_error = f"404 Not Found: {error_text[:200]}"
                break
                
            else:
                error_text = response.text[:500]
                log_func(f"      ❌ [Segment {index}] HTTP {response.status_code}:")
                log_func(f"         {error_text}")
                last_error = f"HTTP {response.status_code}: {error_text[:200]}"
                if attempt < 2:
                    time.sleep(1)
                    
        except requests.exceptions.Timeout:
            log_func(f"      ⏱️ [Segment {index}] 请求超时 (60s) [Attempt {attempt+1}/3]")
            last_error = "请求超时"
            if attempt < 2:
                time.sleep(1)
        except requests.exceptions.ConnectionError as e:
            log_func(f"      ❌ [Segment {index}] 连接错误: {e}")
            last_error = f"连接错误: {str(e)[:100]}"
            if attempt < 2:
                time.sleep(1)
        except Exception as e:
            log_func(f"      ❌ [Segment {index}] 异常: {type(e).__name__}: {e}")
            last_error = f"{type(e).__name__}: {str(e)[:100]}"
            break
    
    log_func(f"      ❌ [Segment {index}] 最终失败: {last_error}")
    return index, None, last_error


def generate_audio_for_script(
    config: PodcastConfig,
    script_json: List[Dict[str, str]],
    progress_callback: Callable[[int, int], None] = None,
    log_func: Callable[[str], None] = print
) -> AudioSegment:
    """
    为整个脚本生成音频
    """
    # 验证 log_func 是否可用
    log_func(f"   ========== generate_audio_for_script 开始 ==========")
    log_func(f"   📋 脚本共 {len(script_json)} 行")
    log_func(f"   🔧 TTS 配置:")
    log_func(f"      Model: {config.tts_model_name}")
    log_func(f"      Voice A: {config.voice_a_full}")
    log_func(f"      Voice B: {config.voice_b_full}")
    log_func(f"      Workers: {config.max_workers_tts}")
    
    # 验证 API Key
    if not config.api_key:
        log_func(f"   ❌ API Key 为空!")
        return AudioSegment.empty()
    log_func(f"      API Key: {config.api_key[:10]}...{config.api_key[-4:]}")
    
    # 显示脚本内容预览
    log_func(f"   📜 脚本预览:")
    for i, line in enumerate(script_json[:3]):  # 只显示前3行
        text_preview = line.get('text', '')[:40].replace('\n', ' ')
        log_func(f"      [{i}] {line.get('speaker', '?')}: {text_preview}...")
    if len(script_json) > 3:
        log_func(f"      ... 还有 {len(script_json) - 3} 行")
    
    log_func(f"   🚀 开始顺序 TTS 合成（便于调试）...")
    
    results = []
    errors = []
    
    # 顺序处理（便于调试）
    valid_segments = []
    for i, line in enumerate(script_json):
        txt = line.get('text', '')
        if txt and txt.strip():
            valid_segments.append((i, txt, line.get('speaker', '')))
        else:
            log_func(f"      ⚠️ [Segment {i}] 跳过空文本")
    
    log_func(f"   📤 共 {len(valid_segments)} 个有效 TTS 任务")
    
    total = len(valid_segments)
    for completed, (i, txt, speaker) in enumerate(valid_segments, 1):
        log_func(f"")
        log_func(f"   --- Segment {i}/{total} ---")
        
        try:
            idx, audio_data, error = generate_audio_segment(
                config, i, txt, speaker, log_func
            )
            
            if progress_callback:
                progress_callback(completed, total)
                
            if audio_data:
                results.append((idx, audio_data))
                log_func(f"   ✅ Segment {i} 完成")
            else:
                errors.append((idx, error))
                log_func(f"   ❌ Segment {i} 失败: {error}")
        except Exception as e:
            log_func(f"   ❌ Segment {i} 异常: {type(e).__name__}: {e}")
            errors.append((i, str(e)))
    
    # 汇总统计
    log_func(f"")
    log_func(f"   {'='*40}")
    log_func(f"   📊 TTS 合成统计:")
    log_func(f"      成功: {len(results)}/{total}")
    log_func(f"      失败: {len(errors)}/{total}")
    
    if errors:
        log_func(f"   ⚠️ 失败详情:")
        for idx, err in errors:
            log_func(f"      - Segment {idx}: {err}")
    log_func(f"   {'='*40}")
                
    # 按顺序排列
    results.sort(key=lambda x: x[0])
    
    # 合成音频
    log_func(f"   🔧 合并音频片段...")
    full_track = AudioSegment.empty()
    pause = AudioSegment.silent(duration=400)
    
    for idx, audio_bytes in results:
        try:
            seg = AudioSegment.from_file(io.BytesIO(audio_bytes), format="mp3")
            full_track += seg + pause
            log_func(f"      ✅ Segment {idx}: {len(seg)}ms")
        except Exception as e:
            log_func(f"      ❌ Segment {idx} 合并失败: {type(e).__name__}: {e}")
    
    duration_sec = len(full_track) / 1000
    log_func(f"   🎵 最终音频: {duration_sec:.1f} 秒 ({len(full_track)}ms)")
            
    return full_track
