"""
Podify - AI Podcast Generator
Version: 3.1.0 - UI 美化
"""
import streamlit as st
from core import PodcastConfig, PodcastPipeline, SupabaseStorage

# 页面配置
st.set_page_config(
    page_title="Podify",
    page_icon="🎙️",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# 自定义 CSS 美化
st.markdown("""
<style>
    /* 顶部空白 */
    .block-container {
        padding-top: 3rem !important;
        padding-bottom: 1rem !important;
    }
    
    /* 隐藏底部的 "Made with Streamlit" */
    footer {
        display: none !important;
    }
    
    /* 标题样式 */
    .main-title {
        font-size: 1.2rem;
        font-weight: 600;
        color: #1a1a2e;
        margin-bottom: 0.3rem;
        display: flex;
        align-items: center;
        gap: 0.3rem;
    }
    
    /* 输入框美化 */
    .stTextArea textarea {
        border-radius: 10px;
        border: 1px solid #e0e0e0;
    }
    
    .stTextArea textarea:focus {
        border-color: #667eea;
        box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.2);
    }
    
    /* 按钮美化 */
    .stButton > button {
        border-radius: 8px;
        font-weight: 500;
        font-size: 0.85rem;
        padding: 0.3rem 0.8rem;
        transition: all 0.2s;
    }
    
    .stButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
    }
    
    /* 成功/错误提示美化 */
    .stSuccess, .stError, .stInfo {
        border-radius: 10px;
    }
    
    /* 音频播放器美化 */
    .stAudio {
        border-radius: 10px;
        overflow: hidden;
    }
    
    /* Expander 美化 */
    .streamlit-expanderHeader {
        font-weight: 600;
        border-radius: 8px;
    }
    
    /* 分隔线美化 */
    hr {
        margin: 1rem 0;
        border: none;
        border-top: 1px solid #eee;
    }
    
    /* 播放列表标题 */
    .playlist-title {
        font-size: 1.1rem;
        font-weight: 600;
        color: #333;
        margin: 0.5rem 0;
    }
    
    /* 侧边栏美化 */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #f8f9fa 0%, #ffffff 100%);
    }
</style>
""", unsafe_allow_html=True)

# 标题
st.markdown('<div class="main-title">🎙️ Podify</div>', unsafe_allow_html=True)

# 初始化 session state
if "logs" not in st.session_state:
    st.session_state.logs = []
if "result" not in st.session_state:
    st.session_state.result = None
if "is_running" not in st.session_state:
    st.session_state.is_running = False
if "cloud_urls" not in st.session_state:
    st.session_state.cloud_urls = None
if "selected_podcast" not in st.session_state:
    st.session_state.selected_podcast = None

# ==========================================
# 侧边栏 - 配置
# ==========================================
with st.sidebar:
    st.header("⚙️ 配置")
    
    api_key = st.text_input(
        "API Key",
        value="sk-vlmhbxgjgllzolnsqunigerenwtwdfsutvaecdpgpvxqyncc",
    )
    
    podcast_mode = st.selectbox(
        "模式",
        options=["Deep Dive (解读)", "News Brief (播报)"],
    )
    
    enable_audio = st.checkbox("生成音频", value=True)
    enable_cloud = st.checkbox("保存到云端", value=True)
    
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
    
    with st.expander("云存储"):
        supabase_url = st.text_input(
            "URL",
            value="https://osxroigfhvnhwijelbrj.supabase.co"
        )
        supabase_key = st.text_input(
            "Key",
            value="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im9zeHJvaWdmaHZuaHdpamVsYnJqIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2ODcxMjMwOSwiZXhwIjoyMDg0Mjg4MzA5fQ.STIO32GaWK0ehPn-izsiWk2CpjjqdLue7ycdWUDNNsc",
            type="password"
        )
        supabase_bucket = st.text_input("Bucket", value="podcast-material")

# ==========================================
# 主界面 - 生成区域
# ==========================================
url_input = st.text_area(
    "输入文章链接（每行一个）",
    height=150,
    placeholder="https://example.com/article1\nhttps://example.com/article2",
)

url_list = [line.strip() for line in url_input.split('\n') if line.strip()]

run_button = st.button(
    f"🚀 生成播客 ({len(url_list)} 篇)",
    use_container_width=True,
    disabled=st.session_state.is_running or len(url_list) == 0
)

# ==========================================
# 显示生成结果
# ==========================================
if st.session_state.result:
    result = st.session_state.result
    
    if result.success:
        st.success("✅ 生成完成")
        
        # 云端链接
        if st.session_state.cloud_urls and st.session_state.cloud_urls.get("success"):
            urls = st.session_state.cloud_urls
            st.info(f"☁️ 已保存到云端")
        
        # 音频播放
        if result.audio_data:
            st.audio(result.audio_data, format="audio/mp3")
            st.download_button(
                "📥 下载音频",
                data=result.audio_data,
                file_name="podcast.mp3",
                mime="audio/mp3",
                use_container_width=True
            )
        
        # 脚本
        if result.script_text:
            with st.expander("📜 脚本"):
                st.text(result.script_text)
            st.download_button(
                "📥 下载脚本",
                data=result.script_text,
                file_name="script.txt",
                mime="text/plain",
                use_container_width=True
            )
        
        # 统计
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

# 日志
if st.session_state.logs:
    with st.expander("📋 日志"):
        st.code("\n".join(st.session_state.logs), language=None)

# ==========================================
# 播放列表（历史记录）
# ==========================================
st.markdown("---")
st.markdown('<div class="playlist-title">📚 播放列表</div>', unsafe_allow_html=True)

# 获取历史记录
try:
    storage = SupabaseStorage(
        url=supabase_url,
        key=supabase_key,
        bucket=supabase_bucket
    )
    podcasts = storage.list_podcasts(limit=10)
except Exception as e:
    podcasts = []
    st.caption(f"无法加载播放列表: {e}")

if podcasts:
    # 初始化脚本显示状态
    if "visible_scripts" not in st.session_state:
        st.session_state.visible_scripts = {}
    
    for podcast in podcasts:
        podcast_id = podcast.get("id", "")
        title = podcast.get("title", "未命名")
        created_at = podcast.get("created_at", "")[:10]  # 只显示日期
        audio_url = podcast.get("audio_url")
        
        # 显示每个播客条目
        with st.expander(f"🎧 {title} ({created_at})"):
            # 音频播放
            if audio_url:
                st.audio(audio_url, format="audio/mp3")
            
            # 加载脚本
            script_url = podcast.get("script_url")
            if script_url:
                is_visible = st.session_state.visible_scripts.get(podcast_id, False)
                
                if is_visible:
                    # 显示隐藏按钮
                    if st.button("📜 隐藏脚本", key=f"hide_{podcast_id}"):
                        st.session_state.visible_scripts[podcast_id] = False
                        st.rerun()
                    
                    # 显示脚本内容
                    script_content = storage.get_script_content(script_url)
                    if script_content:
                        st.text(script_content)
                    else:
                        st.warning("无法加载脚本")
                else:
                    # 显示查看按钮
                    if st.button("📜 查看脚本", key=f"show_{podcast_id}"):
                        st.session_state.visible_scripts[podcast_id] = True
                        st.rerun()
            
            # 来源链接
            source_urls = podcast.get("source_urls", [])
            if source_urls:
                st.caption("来源: " + ", ".join([f"[链接]({url})" for url in source_urls[:3]]))
else:
    st.caption("暂无历史记录")

# ==========================================
# 执行生成流程
# ==========================================
if run_button:
    if not api_key:
        st.error("请输入 API Key")
        st.stop()
    
    st.session_state.is_running = True
    st.session_state.logs = []
    st.session_state.result = None
    st.session_state.cloud_urls = None
    
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
    
    progress_bar = st.progress(0, text="准备中...")
    
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
    
    pipeline = PodcastPipeline(config)
    pipeline.set_log_callback(log_callback)
    pipeline.set_progress_callback(progress_callback)
    
    with st.spinner("生成中..."):
        result = pipeline.run()
    
    # 保存到云端
    cloud_result = None
    if result.success and enable_cloud and supabase_url and supabase_key:
        progress_bar.progress(0.95, text="保存到云端...")
        log_callback("")
        log_callback("☁️ 保存到云端...")
        
        try:
            # 使用 AI 生成的标题
            final_title = result.title or f"Podcast {len(podcasts) + 1}"
            
            cloud_result = storage.save_podcast(
                title=final_title,
                audio_bytes=result.audio_data,
                script_text=result.script_text,
                source_urls=url_list
            )
            
            if cloud_result.get("success"):
                log_callback(f"✅ 保存成功: {final_title}")
            else:
                log_callback(f"⚠️ {cloud_result.get('message', '保存失败')}")
                
        except Exception as e:
            log_callback(f"❌ 云存储错误: {e}")
    
    with logs_lock:
        st.session_state.logs = list(logs)
    st.session_state.result = result
    st.session_state.cloud_urls = cloud_result
    st.session_state.is_running = False
    
    progress_bar.empty()
    st.rerun()
