"""
主流程模块：协调各模块完成播客生成

架构：
- Stage 1: Jina 抓取 (并行)
- Stage 2: LLM 分析 (并行)
- Stage 3: LLM 统一撰写脚本 (串行)
- Stage 4: TTS 生成音频 (并行)
- Stage 5: 音频合并 (串行)
"""
import io
from typing import Optional, Callable, List, Dict, Any, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from pydub import AudioSegment

from .config import PodcastConfig
from .fetcher import fetch_content_with_jina
from .llm import analyze_article, generate_unified_script
from .audio import generate_audio_parallel, merge_audio_segments


@dataclass
class PipelineResult:
    """流程执行结果"""
    success: bool
    title: str = ""
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
    
    def run(self) -> PipelineResult:
        """
        执行完整的播客生成流程
        """
        # 验证配置
        valid, error = self.config.validate()
        if not valid:
            return PipelineResult(success=False, error_message=error)
        
        # 打印配置信息和架构说明
        self.log(f"{'='*60}")
        self.log(f"🎙️ AI Podcast Generator")
        self.log(f"{'='*60}")
        self.log(f"")
        self.log(f"📋 配置信息:")
        self.log(f"   模式: {self.config.podcast_mode}")
        self.log(f"   LLM: {self.config.llm_model_name}")
        self.log(f"   TTS: {self.config.tts_model_name}")
        self.log(f"   音色 A: {self.config.voice_a_full}")
        self.log(f"   音色 B: {self.config.voice_b_full}")
        self.log(f"   音频生成: {'启用' if self.config.enable_audio_generation else '禁用'}")
        self.log(f"")
        self.log(f"🏗️ 处理架构:")
        self.log(f"   Stage 1: Jina 抓取    [并行 x{self.config.max_workers_jina}]")
        self.log(f"   Stage 2: LLM 分析     [并行 x{self.config.max_workers_llm}]")
        self.log(f"   Stage 3: 统一撰写脚本 [串行 - 保证连贯性]")
        self.log(f"   Stage 4: TTS 生成     [并行 x{self.config.max_workers_tts}]")
        self.log(f"   Stage 5: 音频合并     [串行 - 按顺序拼接]")
        self.log(f"{'='*60}")
            
        urls = self.config.urls
        stats = {
            "total_urls": len(urls),
            "fetched": 0,
            "analyzed": 0,
            "script_lines": 0,
            "audio_segments": 0,
        }
        
        # ==========================================
        # Stage 1: Jina Fetching (并行)
        # ==========================================
        self.log(f"")
        self.log(f"{'='*60}")
        self.log(f"🚀 STAGE 1: Jina 抓取 [并行 x{self.config.max_workers_jina}]")
        self.log(f"{'='*60}")
        self.log(f"   URLs ({len(urls)}):")
        for i, url in enumerate(urls):
            self.log(f"      [{i+1}] {url}")
        self.log(f"")
        
        self.update_progress("fetching", 0.0)
        
        fetched_data = []  # [(index, url, content), ...]
        
        with ThreadPoolExecutor(max_workers=self.config.max_workers_jina) as executor:
            futures = {}
            for i, url in enumerate(urls):
                future = executor.submit(
                    self._fetch_task, i, url
                )
                futures[future] = i
            
            for future in as_completed(futures):
                idx, url, content = future.result()
                self.update_progress("fetching", len(fetched_data) / len(urls))
                
                if content:
                    fetched_data.append((idx, url, content))
                    stats["fetched"] += 1
                    self.log(f"   ✅ [{idx+1}] 成功: {len(content)} 字符")
                else:
                    self.log(f"   ❌ [{idx+1}] 失败: {url[:50]}...")
        
        self.update_progress("fetching", 1.0)
        self.log(f"")
        self.log(f"📊 Stage 1 完成: {stats['fetched']}/{len(urls)} 成功")
                    
        if not fetched_data:
            self.log(f"❌ 所有链接抓取失败")
            return PipelineResult(
                success=False,
                error_message="所有链接抓取失败",
                stats=stats
            )
            
        # ==========================================
        # Stage 2: LLM 分析 (并行)
        # ==========================================
        self.log(f"")
        self.log(f"{'='*60}")
        self.log(f"🚀 STAGE 2: LLM 分析 [并行 x{self.config.max_workers_llm}]")
        self.log(f"{'='*60}")
        self.log(f"   待分析: {len(fetched_data)} 篇文章")
        self.log(f"   注意: 发送全文，无字数截断")
        self.log(f"")
        
        self.update_progress("analyzing", 0.0)
        
        analyses = []  # [(index, url, analysis), ...]
        
        with ThreadPoolExecutor(max_workers=self.config.max_workers_llm) as executor:
            futures = {}
            for idx, url, content in fetched_data:
                future = executor.submit(
                    analyze_article,
                    self.config, idx, url, content, self.log
                )
                futures[future] = idx
            
            completed = 0
            for future in as_completed(futures):
                completed += 1
                self.update_progress("analyzing", completed / len(fetched_data))
                
                idx, url, analysis = future.result()
                if analysis:
                    analyses.append((idx, url, analysis))
                    stats["analyzed"] += 1
        
        self.log(f"")
        self.log(f"📊 Stage 2 完成: {stats['analyzed']}/{len(fetched_data)} 成功")
        
        if not analyses:
            self.log(f"❌ 所有文章分析失败")
            return PipelineResult(
                success=False,
                error_message="所有文章分析失败",
                stats=stats
            )
        
        # ==========================================
        # Stage 3: 统一撰写脚本 (串行)
        # ==========================================
        self.log(f"")
        self.log(f"{'='*60}")
        self.log(f"🚀 STAGE 3: 统一撰写脚本 [串行 - 保证前后文连贯]")
        self.log(f"{'='*60}")
        
        self.update_progress("writing", 0.0)
        
        # 按原始顺序排序
        analyses.sort(key=lambda x: x[0])
        
        generated_title, script_json = generate_unified_script(
            self.config,
            analyses,
            self.log
        )
        
        self.update_progress("writing", 1.0)
        
        if not script_json:
            self.log(f"❌ 脚本生成失败")
            return PipelineResult(
                success=False,
                error_message="脚本生成失败",
                stats=stats
            )
        
        # 使用生成的标题，如果没有则使用默认标题
        podcast_title = generated_title or f"Podcast {len(urls)} 篇文章"
        
        stats["script_lines"] = len(script_json)
        
        # 生成可读脚本文本
        script_text = f"=== {podcast_title} ===\n\n"
        for idx, url, _ in analyses:
            script_text += f"Source {idx+1}: {url}\n"
        script_text += "\n" + "="*40 + "\n\n"
        
        for line in script_json:
            script_text += f"{line['speaker']}: {line['text']}\n\n"
        
        self.log(f"")
        self.log(f"📊 Stage 3 完成: 标题「{podcast_title}」, {len(script_json)} 行对话")
        
        # ==========================================
        # Stage 4 & 5: 音频生成和合并
        # ==========================================
        audio_bytes = None
        
        if self.config.enable_audio_generation:
            # Stage 4: TTS 并行生成
            self.log(f"")
            self.log(f"{'='*60}")
            self.log(f"🚀 STAGE 4: TTS 生成 [并行 x{self.config.max_workers_tts}]")
            self.log(f"{'='*60}")
            
            self.update_progress("tts", 0.0)
            
            audio_segments, audio_errors = generate_audio_parallel(
                self.config,
                script_json,
                self.log
            )
            
            self.update_progress("tts", 1.0)
            
            stats["audio_segments"] = len(audio_segments)
            
            if not audio_segments:
                self.log(f"❌ 所有音频生成失败")
            else:
                # Stage 5: 音频合并 (串行)
                self.log(f"")
                self.log(f"{'='*60}")
                self.log(f"🚀 STAGE 5: 音频合并 [串行 - 按顺序拼接]")
                self.log(f"{'='*60}")
                
                self.update_progress("merging", 0.0)
                
                final_audio = merge_audio_segments(audio_segments, self.log)
                
                self.update_progress("merging", 1.0)
                
                if len(final_audio) > 0:
                    buffer = io.BytesIO()
                    final_audio.export(buffer, format="mp3")
                    audio_bytes = buffer.getvalue()
                    
                    self.log(f"")
                    self.log(f"🎉 音频导出完成!")
                    self.log(f"   文件大小: {len(audio_bytes)/1024:.1f} KB")
                else:
                    self.log(f"⚠️ 音频合并后为空")
        else:
            self.log(f"")
            self.log(f"⚪ 音频生成已跳过（未启用）")
        
        # ==========================================
        # 最终汇总
        # ==========================================
        self.log(f"")
        self.log(f"{'='*60}")
        self.log(f"📊 最终统计")
        self.log(f"{'='*60}")
        self.log(f"   链接总数: {stats['total_urls']}")
        self.log(f"   抓取成功: {stats['fetched']}")
        self.log(f"   分析成功: {stats['analyzed']}")
        self.log(f"   脚本行数: {stats['script_lines']}")
        self.log(f"   音频片段: {stats['audio_segments']}")
        self.log(f"{'='*60}")
        self.log(f"✅ 处理完成!")
            
        self.update_progress("complete", 1.0)
        
        return PipelineResult(
            success=True,
            title=podcast_title,
            script_text=script_text,
            audio_data=audio_bytes,
            stats=stats
        )
    
    def _fetch_task(self, index: int, url: str) -> Tuple[int, str, Optional[str]]:
        """抓取任务（供并行调用）"""
        self.log(f"   🌍 [{index+1}] 开始抓取: {url[:50]}...")
        content = fetch_content_with_jina(url, log_func=self.log)
        return index, url, content
