"""
主流程模块：协调各模块完成播客生成
"""
import io
from typing import Optional, Callable, List, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from pydub import AudioSegment

from .config import PodcastConfig
from .fetcher import fetch_with_index
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
        self.log(f"{'='*50}")
        self.log(f"📋 配置信息:")
        self.log(f"   - 模式: {self.config.podcast_mode}")
        self.log(f"   - LLM 模型: {self.config.llm_model_name}")
        self.log(f"   - TTS 模型: {self.config.tts_model_name}")
        self.log(f"   - 音色 A: {self.config.voice_a_full}")
        self.log(f"   - 音色 B: {self.config.voice_b_full}")
        self.log(f"   - 音频生成: {'启用' if self.config.enable_audio_generation else '禁用'}")
        self.log(f"   - 并发: Jina={self.config.max_workers_jina}, LLM={self.config.max_workers_llm}, TTS={self.config.max_workers_tts}")
        self.log(f"{'='*50}")
            
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
        self.log(f"\n{'='*50}")
        self.log(f"🚀 STAGE 1: Jina Fetching")
        self.log(f"   Workers: {self.config.max_workers_jina}")
        self.log(f"   URLs: {len(urls)}")
        self.log(f"{'='*50}")
        
        for i, url in enumerate(urls):
            self.log(f"   [{i+1}] {url}")
        
        self.update_progress("fetching", 0.0)
        
        tasks = [(i, u) for i, u in enumerate(urls)]
        with ThreadPoolExecutor(max_workers=self.config.max_workers_jina) as executor:
            futures = {executor.submit(fetch_with_index, t): t[0] for t in tasks}
            completed = 0
            
            for future in as_completed(futures):
                completed += 1
                self.update_progress("fetching", completed / len(tasks))
                
                res = future.result()  # (index, url, text)
                if res[2]:  # 如果 text 存在
                    fetched_data.append(res)
                    stats["fetched"] += 1
                    self.log(f"✅ [{res[0]+1}] 抓取成功: {len(res[2])} 字符")
                else:
                    self.log(f"❌ [{res[0]+1}] 抓取失败: {res[1][:50]}...")
        
        self.log(f"\n📊 Stage 1 结果: {stats['fetched']}/{len(urls)} 成功")
                    
        if not fetched_data:
            return PipelineResult(
                success=False,
                error_message="所有链接抓取失败",
                stats=stats
            )
            
        # ==========================================
        # Stage 2: LLM Processing
        # ==========================================
        self.log(f"\n{'='*50}")
        self.log(f"🚀 STAGE 2: LLM Processing")
        self.log(f"   Workers: {self.config.max_workers_llm}")
        self.log(f"   待处理: {len(fetched_data)} 篇文章")
        self.log(f"{'='*50}")
        
        self.update_progress("processing", 0.0)
        
        with ThreadPoolExecutor(max_workers=self.config.max_workers_llm) as executor:
            futures = {}
            for d in fetched_data:
                future = executor.submit(
                    process_article,
                    self.config,
                    d[0],  # index
                    d[1],  # url
                    d[2]   # raw_text
                )
                futures[future] = d[0]
                
            completed = 0
            for future in as_completed(futures):
                completed += 1
                self.update_progress("processing", completed / len(fetched_data))
                
                idx, url, r_text, s_json = future.result()
                if s_json:
                    processed_scripts[idx] = (r_text, s_json)
                    full_text_log += r_text
                    stats["processed"] += 1
                    self.log(f"✅ [{idx+1}] LLM 处理成功: {len(s_json)} 行对话")
                else:
                    self.log(f"❌ [{idx+1}] LLM 处理失败")
        
        self.log(f"\n📊 Stage 2 结果: {stats['processed']}/{len(fetched_data)} 成功")
        self.log(f"\n📄 文本脚本生成完成")
        
        # ==========================================
        # Stage 3: Audio Generation (Optional)
        # ==========================================
        audio_bytes = None
        
        if self.config.enable_audio_generation:
            self.log(f"\n{'='*50}")
            self.log(f"🚀 STAGE 3: Audio Generation")
            self.log(f"   Workers: {self.config.max_workers_tts}")
            self.log(f"   待合成: {sum(1 for s in processed_scripts if s)} 篇文章")
            self.log(f"{'='*50}")
            
            self.update_progress("audio", 0.0)
            
            total_lines = sum(
                len(s[1]) for s in processed_scripts if s is not None
            )
            processed_lines = 0
            
            self.log(f"   总对话行数: {total_lines}")
            
            for i, script_data in enumerate(processed_scripts):
                if script_data:
                    r_text, s_json = script_data
                    self.log(f"\n🎙️ Article {i+1}: 合成 {len(s_json)} 行对话...")
                    
                    def audio_progress(current, total):
                        nonlocal processed_lines
                        self.update_progress(
                            "audio",
                            (processed_lines + current) / total_lines if total_lines > 0 else 0
                        )
                    
                    article_audio = generate_audio_for_script(
                        self.config,
                        s_json,
                        progress_callback=audio_progress
                    )
                    
                    processed_lines += len(s_json)
                    
                    if len(article_audio) > 0:
                        final_mix += article_audio
                        final_mix += transition
                        stats["audio_generated"] += 1
                        self.log(f"   ✅ Article {i+1} 音频完成，时长: {len(article_audio)/1000:.1f}s")
                    else:
                        self.log(f"   ❌ Article {i+1} 音频为空")
                        
            # 导出音频
            if len(final_mix) > 0:
                buffer = io.BytesIO()
                final_mix.export(buffer, format="mp3")
                audio_bytes = buffer.getvalue()
                self.log(f"\n🎉 音频生成完成!")
                self.log(f"   总时长: {len(final_mix)/1000:.1f} 秒")
                self.log(f"   文件大小: {len(audio_bytes)/1024:.1f} KB")
            else:
                self.log("\n⚠️ 未生成任何音频")
        else:
            self.log("\n⚪ 音频生成已跳过（未启用）")
        
        self.log(f"\n{'='*50}")
        self.log(f"📊 最终统计:")
        self.log(f"   - 链接总数: {stats['total_urls']}")
        self.log(f"   - 抓取成功: {stats['fetched']}")
        self.log(f"   - LLM 处理成功: {stats['processed']}")
        self.log(f"   - 音频生成成功: {stats['audio_generated']}")
        self.log(f"{'='*50}")
            
        self.update_progress("complete", 1.0)
        
        return PipelineResult(
            success=True,
            script_text=full_text_log,
            audio_data=audio_bytes,
            stats=stats
        )
