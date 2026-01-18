"""
AI Podcast Generator - Streamlit 前端界面
"""
import streamlit as st
from core import PodcastConfig, PodcastPipeline

# 页面配置
st.set_page_config(
    page_title="AI Podcast Generator",
    page_icon="🎙️",
    layout="wide"
)

# 标题
st.title("🎙️ AI Podcast Generator")
st.markdown("将文章链接转换为双人播客脚本和音频")
st.markdown("---")

# 初始化 session state
if "logs" not in st.session_state:
    st.session_state.logs = []
if "result" not in st.session_state:
    st.session_state.result = None
if "is_running" not in st.session_state:
    st.session_state.is_running = False

# ==========================================
# 侧边栏 - 配置项
# ==========================================
with st.sidebar:
    st.header("⚙️ 系统配置")
    
    # API 凭证
    st.subheader("🔑 API 凭证")
    api_key = st.text_input(
        "SiliconFlow API Key",
        help="请输入您的 SiliconFlow API Key"
    )
    
    st.markdown("---")
    
    # 模式选择
    st.subheader("🎯 模式选择")
    podcast_mode = st.selectbox(
        "播客模式",
        options=["Deep Dive (解读模式)", "News Brief (播报模式)"],
        help="解读模式：师生对谈风格\n播报模式：新闻播报风格"
    )
    
    enable_audio = st.checkbox(
        "启用音频生成",
        value=True,
        help="是否生成 TTS 音频文件"
    )
    
    st.markdown("---")
    
    # 模型配置
    st.subheader("🤖 模型配置")
    llm_model = st.text_input(
        "LLM 模型",
        value="deepseek-ai/DeepSeek-V3.2",
        help="用于分析和生成脚本的大语言模型"
    )
    
    tts_model = st.text_input(
        "TTS 模型",
        value="FunAudioLLM/CosyVoice2-0.5B",
        help="用于语音合成的模型"
    )
    
    st.markdown("---")
    
    # 音色配置
    st.subheader("🎤 音色配置")
    col1, col2 = st.columns(2)
    with col1:
        voice_a = st.text_input(
            "Host A 音色",
            value="alex",
            help="主持人 A 的音色 ID"
        )
    with col2:
        voice_b = st.text_input(
            "Host B 音色",
            value="claire",
            help="主持人 B 的音色 ID"
        )
    
    st.markdown("---")
    
    # 并发设置
    st.subheader("🚦 并发设置")
    col1, col2, col3 = st.columns(3)
    with col1:
        workers_jina = st.number_input(
            "Jina",
            min_value=1,
            max_value=10,
            value=2,
            help="Jina 抓取并发数"
        )
    with col2:
        workers_llm = st.number_input(
            "LLM",
            min_value=1,
            max_value=10,
            value=5,
            help="LLM 处理并发数"
        )
    with col3:
        workers_tts = st.number_input(
            "TTS",
            min_value=1,
            max_value=10,
            value=5,
            help="TTS 生成并发数"
        )

# ==========================================
# 主界面 - 链接输入和执行
# ==========================================
st.header("📝 输入文章链接")

url_input = st.text_area(
    "请粘贴文章链接（每行一个）",
    height=200,
    placeholder="""https://example.com/article1
https://example.com/article2
https://example.com/article3""",
    help="支持任意网页链接，系统会自动使用 Jina 抓取内容"
)

# 解析 URL 列表
url_list = [line.strip() for line in url_input.split('\n') if line.strip()]

# 显示链接统计
if url_list:
    st.info(f"📊 已输入 {len(url_list)} 个链接")

st.markdown("---")

# 执行按钮
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    run_button = st.button(
        "🚀 开始生成",
        use_container_width=True,
        disabled=st.session_state.is_running
    )

# ==========================================
# 执行流程
# ==========================================
if run_button:
    # 验证输入
    if not api_key:
        st.error("❌ 请输入 API Key")
        st.stop()
    
    if not url_list:
        st.error("❌ 请输入至少一个链接")
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
    
    # 创建进度显示
    progress_bar = st.progress(0, text="准备中...")
    status_text = st.empty()
    
    # 创建单个日志展示区域
    log_expander = st.expander("📋 运行日志", expanded=True)
    log_placeholder = log_expander.empty()
    
    # 日志回调
    logs = []
    def log_callback(message):
        logs.append(message)
        # 实时更新同一个 placeholder
        log_placeholder.code("\n".join(logs[-100:]), language=None)
    
    # 进度回调
    stage_names = {
        "fetching": "🌍 抓取内容",
        "processing": "🧠 LLM 处理",
        "audio": "🎙️ 生成音频",
        "complete": "✅ 完成"
    }
    
    def progress_callback(stage, progress):
        stage_name = stage_names.get(stage, stage)
        progress_bar.progress(progress, text=f"{stage_name} ({progress*100:.0f}%)")
    
    # 创建并运行流水线
    pipeline = PodcastPipeline(config)
    pipeline.set_log_callback(log_callback)
    pipeline.set_progress_callback(progress_callback)
    
    with st.spinner("正在生成播客..."):
        result = pipeline.run()
    
    st.session_state.result = result
    st.session_state.logs = logs
    st.session_state.is_running = False
    
    # 清除进度条
    progress_bar.empty()
    status_text.empty()

# ==========================================
# 显示结果
# ==========================================
if st.session_state.result:
    result = st.session_state.result
    
    st.markdown("---")
    st.header("📊 生成结果")
    
    if result.success:
        # 统计信息
        stats = result.stats or {}
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("总链接数", stats.get("total_urls", 0))
        with col2:
            st.metric("成功抓取", stats.get("fetched", 0))
        with col3:
            st.metric("成功处理", stats.get("processed", 0))
        with col4:
            st.metric("音频生成", stats.get("audio_generated", 0))
        
        st.success("✅ 生成完成！")
        
        # 脚本文本
        if result.script_text:
            st.subheader("📜 播客脚本")
            with st.expander("查看完整脚本", expanded=True):
                st.text(result.script_text)
            
            # 下载脚本按钮
            st.download_button(
                label="📥 下载脚本 (TXT)",
                data=result.script_text,
                file_name="podcast_script.txt",
                mime="text/plain"
            )
        
        # 音频
        if result.audio_data:
            st.subheader("🎧 播客音频")
            st.audio(result.audio_data, format="audio/mp3")
            
            # 下载音频按钮
            st.download_button(
                label="📥 下载音频 (MP3)",
                data=result.audio_data,
                file_name="podcast_final.mp3",
                mime="audio/mp3"
            )
    else:
        st.error(f"❌ 生成失败: {result.error_message}")

# ==========================================
# 显示日志
# ==========================================
if st.session_state.logs:
    with st.expander("📋 完整运行日志", expanded=False):
        st.text("\n".join(st.session_state.logs))

# ==========================================
# 页脚
# ==========================================
st.markdown("---")
st.markdown(
    """
    <div style="text-align: center; color: #888;">
        <small>
            Powered by SiliconFlow API | 
            Built with Streamlit
        </small>
    </div>
    """,
    unsafe_allow_html=True
)
