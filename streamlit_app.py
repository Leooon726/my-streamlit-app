"""
AI Podcast Generator - Streamlit 前端界面
Version: 2.1.0 - 移动端优化
"""
import streamlit as st
from core import PodcastConfig, PodcastPipeline

# 页面配置
st.set_page_config(
    page_title="AI Podcast Generator",
    page_icon="🎙️",
    layout="centered"  # 改为 centered，更适合移动端
)

# 标题（更紧凑）
st.title("🎙️ AI Podcast Generator")

# 初始化 session state
if "logs" not in st.session_state:
    st.session_state.logs = []
if "result" not in st.session_state:
    st.session_state.result = None
if "is_running" not in st.session_state:
    st.session_state.is_running = False

# ==========================================
# 侧边栏 - 配置项（保持不变）
# ==========================================
with st.sidebar:
    st.header("⚙️ 配置")
    
    api_key = st.text_input(
        "API Key",
        value="sk-vlmhbxgjgllzolnsqunigerenwtwdfsutvaecdpgpvxqyncc",
    )
    
    podcast_mode = st.selectbox(
        "模式",
        options=["Deep Dive (解读模式)", "News Brief (播报模式)"],
    )
    
    enable_audio = st.checkbox("生成音频", value=True)
    
    with st.expander("高级设置"):
        llm_model = st.text_input("LLM", value="deepseek-ai/DeepSeek-V3.2")
        tts_model = st.text_input("TTS", value="FunAudioLLM/CosyVoice2-0.5B")
        
        col1, col2 = st.columns(2)
        with col1:
            voice_a = st.text_input("Host A", value="alex")
        with col2:
            voice_b = st.text_input("Host B", value="claire")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            workers_jina = st.number_input("Jina", min_value=1, max_value=10, value=2)
        with col2:
            workers_llm = st.number_input("LLM", min_value=1, max_value=10, value=5)
        with col3:
            workers_tts = st.number_input("TTS", min_value=1, max_value=10, value=5)

# ==========================================
# 主界面 - 输入和执行
# ==========================================
url_input = st.text_area(
    "输入文章链接（每行一个）",
    height=120,
    placeholder="https://example.com/article1\nhttps://example.com/article2",
)

url_list = [line.strip() for line in url_input.split('\n') if line.strip()]

# 执行按钮
run_button = st.button(
    f"🚀 生成播客 ({len(url_list)} 篇)",
    use_container_width=True,
    disabled=st.session_state.is_running or len(url_list) == 0
)

# ==========================================
# 显示结果（放在最上面）
# ==========================================
if st.session_state.result:
    result = st.session_state.result
    
    if result.success:
        st.success("✅ 生成完成")
        
        # 音频放最上面
        if result.audio_data:
            st.audio(result.audio_data, format="audio/mp3")
            st.download_button(
                "📥 下载音频",
                data=result.audio_data,
                file_name="podcast.mp3",
                mime="audio/mp3",
                use_container_width=True
            )
        
        # 脚本（默认折叠）
        if result.script_text:
            with st.expander("📜 查看脚本"):
                st.text(result.script_text)
            st.download_button(
                "📥 下载脚本",
                data=result.script_text,
                file_name="script.txt",
                mime="text/plain",
                use_container_width=True
            )
        
        # 统计信息（折叠）
        stats = result.stats or {}
        with st.expander("📊 统计"):
            cols = st.columns(5)
            cols[0].metric("链接", stats.get("total_urls", 0))
            cols[1].metric("抓取", stats.get("fetched", 0))
            cols[2].metric("分析", stats.get("analyzed", 0))
            cols[3].metric("脚本", stats.get("script_lines", 0))
            cols[4].metric("音频", stats.get("audio_segments", 0))
    else:
        st.error(f"❌ {result.error_message}")

# 日志（折叠，放最下面）
if st.session_state.logs:
    with st.expander("📋 运行日志"):
        full_log_text = "\n".join(st.session_state.logs)
        st.code(full_log_text, language=None)
        st.download_button(
            "📥 下载日志",
            data=full_log_text,
            file_name="log.txt",
            mime="text/plain",
            use_container_width=True
        )

# ==========================================
# 执行流程
# ==========================================
if run_button:
    if not api_key:
        st.error("请输入 API Key")
        st.stop()
    
    st.session_state.is_running = True
    st.session_state.logs = []
    st.session_state.result = None
    
    # 创建配置
    config = PodcastConfig(
        api_key=api_key,
        enable_audio_generation=enable_audio,
        podcast_mode="news_brief" if "News Brief" in podcast_mode else "deep_dive",
        max_workers_jina=int(workers_jina),
        max_workers_llm=int(workers_llm),
        max_workers_tts=int(workers_tts),
        llm_model_name=llm_model,
        tts_model_name=tts_model,
        voice_name_host_a=voice_a,
        voice_name_host_b=voice_b,
        urls=url_list
    )
    
    # 进度显示
    progress_bar = st.progress(0, text="准备中...")
    
    # 日志收集（线程安全）
    import threading
    logs = []
    logs_lock = threading.Lock()
    
    def log_callback(message):
        with logs_lock:
            logs.append(message)
    
    stage_names = {
        "fetching": "抓取中",
        "analyzing": "分析中",
        "writing": "撰写中",
        "tts": "合成中",
        "merging": "合并中",
        "complete": "完成"
    }
    
    def progress_callback(stage, progress):
        stage_name = stage_names.get(stage, stage)
        progress_bar.progress(progress, text=f"{stage_name} {progress*100:.0f}%")
    
    # 运行流水线
    pipeline = PodcastPipeline(config)
    pipeline.set_log_callback(log_callback)
    pipeline.set_progress_callback(progress_callback)
    
    with st.spinner("生成中..."):
        result = pipeline.run()
    
    # 保存结果
    with logs_lock:
        st.session_state.logs = list(logs)
    st.session_state.result = result
    st.session_state.is_running = False
    
    # 清除进度条并刷新
    progress_bar.empty()
    st.rerun()
