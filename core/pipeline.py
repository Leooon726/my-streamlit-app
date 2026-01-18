"""
主流程模块：协调各模块完成播客生成
"""
import io
from typing import Optional, Callable, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from functools import partial

from pydub import AudioSegment

from .config import PodcastConfig
from .fetcher import fetch_content_with_jina
from .llm import process_article
from .audio import generate_audio_for_script


@dataclass
class PipelineResult:
    """流程执行结果"""
    success: bool
    script_text: str = ""
    audio_data: Optional[bytes] = None
    error_message: str = ""
    stats: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.stats is None:
            self.stats = {}


class PodcastPipeline:
    """播客生成流水线"""
    
    def __init__(self, config: PodcastConfig):
        self.config = config
        self.log_callback: Optional[Callable[[str], None]] = None
        self.progress_callback: Optional[Callable[[str, float], None]] = None
        
    def set_log_callback(self, callback: Callable[[str], None]):
        """设置日志回调"""
        self.log_callback = callback
        
    def set_progress_callback(self, callback: Callable[[str, float], None]):
        """设置进度回调 (stage, progress)"""
        self.progress_callback = callback
        
    def log(self, message: str):
        """记录日志"""
        print(message)
        if self.log_callback:
            self.log_callback(message)
            
    def update_progress(self, stage: str, progress: float):
        """更新进度"""
        if self.progress_callback:
            self.progress_callback(stage, progress)
    
    def _fetch_task(self, task_data):
        """抓取任务包装器"""
        index, url = task_data
        self.log(f"🌍 [Task {index+1}] 开始抓取")
        self.log(f"   URL: {url}")
        text = fetch_content_with_jina(url, log_func=self.log)
        
        if text:
            self.log(f"🌍 [Task {index+1}] ✅ 抓取完成: {len(text)} 字符")
        else:
            self.log(f"🌍 [Task {index+1}] ❌ 抓取失败")
            
        return index, url, text
    
    def _process_task(self, fetch_result):
        """LLM 处理任务包装器"""
        index, url, raw_text = fetch_result
        return process_article(
            self.config,
            index,
            url,
            raw_text,
            log_func=self.log
        )
    
    def run(self) -> PipelineResult:
        """
        执行完整的播客生成流程
        
        Returns:
            PipelineResult 对象
        """
        # 验证配置
        valid, error = self.config.validate()
        if not valid:
            return PipelineResult(success=False, error_message=error)
        
        # 打印配置信息
        self.log(f"{'='*60}")
        self.log(f"📋 配置信息:")
        self.log(f"   模式: {self.config.podcast_mode}")
        self.log(f"   LLM 模型: {self.config.llm_model_name}")
        self.log(f"   TTS 模型: {self.config.tts_model_name}")
        self.log(f"   音色 A: {self.config.voice_a_full}")
        self.log(f"   音色 B: {self.config.voice_b_full}")
        self.log(f"   音频生成: {'启用' if self.config.enable_audio_generation else '禁用'}")
        self.log(f"   并发设置:")
        self.log(f"      Jina: {self.config.max_workers_jina}")
        self.log(f"      LLM: {self.config.max_workers_llm}")
        self.log(f"      TTS: {self.config.max_workers_tts}")
        self.log(f"{'='*60}")
            
        urls = self.config.urls
        stats = {
            "total_urls": len(urls),
            "fetched": 0,
            "processed": 0,
            "audio_generated": 0
        }
        
        full_text_log = "=== AI Podcast Script ===\n\n"
        final_mix = AudioSegment.empty()
        transition = AudioSegment.silent(duration=1000)
        
        # 容器
        fetched_data = []  # (index, url, raw_text)
        processed_scripts = [None] * len(urls)  # (readable, json)
        
        # ==========================================
        # Stage 1: Jina Fetching
        # ==========================================
        self.log(f"")
        self.log(f"{'='*60}")
        self.log(f"🚀 STAGE 1: Jina Fetching")
        self.log(f"{'='*60}")
        self.log(f"Workers: {self.config.max_workers_jina}")
        self.log(f"URLs ({len(urls)}):")
        for i, url in enumerate(urls):
            self.log(f"   [{i+1}] {url}")
        self.log(f"")
        
        self.update_progress("fetching", 0.0)
        
        tasks = [(i, u) for i, u in enumerate(urls)]
        
        # 顺序执行以便日志更清晰（Jina 并发度低）
        for i, task in enumerate(tasks):
            res = self._fetch_task(task)
            self.update_progress("fetching", (i + 1) / len(tasks))
            
            if res[2]:
                fetched_data.append(res)
                stats["fetched"] += 1
            self.log(f"")
        
        self.log(f"📊 Stage 1 完成: {stats['fetched']}/{len(urls)} 成功")
                    
        if not fetched_data:
            self.log(f"❌ 所有链接抓取失败，停止运行")
            return PipelineResult(
                success=False,
                error_message="所有链接抓取失败",
                stats=stats
            )
            
        # ==========================================
        # Stage 2: LLM Processing
        # ==========================================
        self.log(f"")
        self.log(f"{'='*60}")
        self.log(f"🚀 STAGE 2: LLM Processing")
        self.log(f"{'='*60}")
        self.log(f"Workers: {self.config.max_workers_llm}")
        self.log(f"待处理: {len(fetched_data)} 篇文章")
        self.log(f"")
        
        self.update_progress("processing", 0.0)
        
        # 顺序执行以便日志更清晰
        for i, fetch_result in enumerate(fetched_data):
            idx, url, r_text, s_json = self._process_task(fetch_result)
            self.update_progress("processing", (i + 1) / len(fetched_data))
            
            if s_json:
                processed_scripts[idx] = (r_text, s_json)
                full_text_log += r_text
                stats["processed"] += 1
            self.log(f"")
        
        self.log(f"📊 Stage 2 完成: {stats['processed']}/{len(fetched_data)} 成功")
        self.log(f"📄 文本脚本生成完成")
        
        # ==========================================
        # Stage 3: Audio Generation (Optional)
        # ==========================================
        audio_bytes = None
        
        if self.config.enable_audio_generation:
            self.log(f"")
            self.log(f"{'='*60}")
            self.log(f"🚀 STAGE 3: Audio Generation")
            self.log(f"{'='*60}")
            self.log(f"Workers: {self.config.max_workers_tts}")
            
            scripts_to_process = [(i, s) for i, s in enumerate(processed_scripts) if s]
            self.log(f"待合成: {len(scripts_to_process)} 篇文章")
            
            total_lines = sum(len(s[1]) for _, s in scripts_to_process)
            self.log(f"总对话行数: {total_lines}")
            self.log(f"")
            
            self.update_progress("audio", 0.0)
            
            processed_lines = 0
            
            for article_idx, (i, script_data) in enumerate(scripts_to_process):
                r_text, s_json = script_data
                self.log(f"🎙️ Article {i+1}: 开始合成 {len(s_json)} 行对话")
                self.log(f"   调用 generate_audio_for_script...")
                
                def audio_progress(current, total):
                    nonlocal processed_lines
                    overall = (processed_lines + current) / total_lines if total_lines > 0 else 0
                    self.update_progress("audio", overall)
                
                try:
                    article_audio = generate_audio_for_script(
                        self.config,
                        s_json,
                        progress_callback=audio_progress,
                        log_func=self.log
                    )
                    
                    self.log(f"   generate_audio_for_script 返回，音频长度: {len(article_audio)}ms")
                    
                except Exception as e:
                    self.log(f"   ❌ generate_audio_for_script 异常:")
                    self.log(f"      {type(e).__name__}: {e}")
                    import traceback
                    self.log(f"      Traceback: {traceback.format_exc()}")
                    article_audio = AudioSegment.empty()
                
                processed_lines += len(s_json)
                
                if len(article_audio) > 0:
                    final_mix += article_audio
                    final_mix += transition
                    stats["audio_generated"] += 1
                    self.log(f"✅ Article {i+1} 完成，时长: {len(article_audio)/1000:.1f}s")
                else:
                    self.log(f"❌ Article {i+1} 音频为空")
                
                self.log(f"")
                        
            # 导出音频
            if len(final_mix) > 0:
                buffer = io.BytesIO()
                final_mix.export(buffer, format="mp3")
                audio_bytes = buffer.getvalue()
                self.log(f"🎉 音频导出完成!")
                self.log(f"   总时长: {len(final_mix)/1000:.1f} 秒")
                self.log(f"   文件大小: {len(audio_bytes)/1024:.1f} KB")
            else:
                self.log(f"⚠️ 未生成任何音频")
        else:
            self.log(f"")
            self.log(f"⚪ 音频生成已跳过（未启用）")
        
        self.log(f"")
        self.log(f"{'='*60}")
        self.log(f"📊 最终统计")
        self.log(f"{'='*60}")
        self.log(f"   链接总数: {stats['total_urls']}")
        self.log(f"   抓取成功: {stats['fetched']}")
        self.log(f"   LLM 处理成功: {stats['processed']}")
        self.log(f"   音频生成成功: {stats['audio_generated']}")
        self.log(f"{'='*60}")
            
        self.update_progress("complete", 1.0)
        
        return PipelineResult(
            success=True,
            script_text=full_text_log,
            audio_data=audio_bytes,
            stats=stats
        )
