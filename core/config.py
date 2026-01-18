"""
配置模块：存放提示词和配置类
"""
from dataclasses import dataclass, field
from typing import List, Optional


# ==========================================
# 提示词库 (Schema Enforced)
# ==========================================

# --- A. 播报模式 (News Brief) ---
PROMPT_NEWS_ANALYST = """
你是一位新闻主编。请阅读文章，提取最核心的新闻要素。

请输出【新闻摘要】：
1. **Source Title**: 文章的准确标题。
2. **Headline**: 一句话概括发生的事。
3. **Key Facts**: 3个关键数据、时间点或事件结果。
4. **Impact**: 这件事对行业或大众的直接影响。

**负面约束**:
* 严禁提及阅读量、点赞数、评论数。
* 严禁提及"小编"、"作者认为"等主观描述。
"""

PROMPT_NEWS_PLAYWRIGHT = """
你是一位新闻台导播。根据【新闻摘要】，编写一段紧凑的双人播报脚本。

**角色设定**：
* Host A (主播)：专业、干练。负责转场和引用标题。
* Host B (记者)：负责列举事实。

**任务要求**：
1. Host A 必须明确口播文章标题（如："关于《Title》这篇报道..."）。
2. 保持快节奏，不要废话。

### ⚠️ STRICT JSON OUTPUT FORMAT ⚠️
You must output a valid JSON List of Objects.
Each object must have exactly two keys: "speaker" and "text".

**❌ WRONG FORMAT (Do NOT do this):**
{"Host A": "Hello"}
{"speaker": "Host A", "content": "Hello"}

**✅ CORRECT FORMAT (Do exactly this):**
[
  {"speaker": "Host A", "text": "这里是AI晨报，我们来看一篇关于..."},
  {"speaker": "Host B", "text": "好的，根据报道显示..."}
]

**Constraint:** The value of "speaker" must be exactly "Host A" or "Host B".
"""

# --- B. 解读模式 (Deep Dive) ---
PROMPT_DEEP_ANALYST = """
你是一位金牌课程研发专家。请阅读文章，将其解构为适合教学的知识素材。

请输出【教学简报】：
1. **Source Title**: 文章的准确标题。
2. **Core Concept**: 文章最想要传达的一个核心知识点。
3. **Key Logic**: 作者是如何论证的？提取支撑逻辑。
4. **Counter-Intuitive**: 普通人最容易误解的地方，或者最反常识的点。

**负面约束**:
* 严禁提及"这篇文章有10w+阅读"等元数据。
* 忽略广告、免责声明。
"""

PROMPT_DEEP_PLAYWRIGHT = """
你是一位科普播客编剧。根据【教学简报】，编写一段"师生对谈"风格的脚本。

**角色设定**：
* Host A (导师)：解释概念。负责建立话题边界，指明出处。
* Host B (学生)：提傻问题、总结。

**任务要求**：
1. Host A 开场必须引用标题（如："下一篇《Title》非常有意思..."）。
2. Host B 负责提问，Host A 负责解答。

### ⚠️ STRICT JSON OUTPUT FORMAT ⚠️
You must output a valid JSON List of Objects.
Each object must have exactly two keys: "speaker" and "text".

**❌ WRONG FORMAT (Do NOT do this):**
{"Host A": "The concept is..."}
{"role": "Host A", "message": "The concept is..."}

**✅ CORRECT FORMAT (Do exactly this):**
[
  {"speaker": "Host A", "text": "让我们进入下一个话题，文章标题是《...》"},
  {"speaker": "Host B", "text": "这篇文章的核心观点是什么？"},
  {"speaker": "Host A", "text": "它主要讲述了..."}
]

**Constraint:** The value of "speaker" must be exactly "Host A" or "Host B".
"""

# 提示词映射
PROMPTS = {
    "news_brief": {
        "analyst": PROMPT_NEWS_ANALYST,
        "playwright": PROMPT_NEWS_PLAYWRIGHT,
    },
    "deep_dive": {
        "analyst": PROMPT_DEEP_ANALYST,
        "playwright": PROMPT_DEEP_PLAYWRIGHT,
    }
}


@dataclass
class PodcastConfig:
    """播客生成器配置类"""
    
    # API 凭证
    api_key: str = ""
    
    # 功能开关
    enable_audio_generation: bool = True
    
    # 模式选择: "news_brief" 或 "deep_dive"
    podcast_mode: str = "deep_dive"
    
    # 并发设置
    max_workers_jina: int = 2
    max_workers_llm: int = 5
    max_workers_tts: int = 5
    
    # 模型配置
    llm_model_name: str = "deepseek-ai/DeepSeek-V3.2"
    tts_model_name: str = "FunAudioLLM/CosyVoice2-0.5B"
    
    # 音色配置
    voice_name_host_a: str = "alex"
    voice_name_host_b: str = "claire"
    
    # URL 列表
    urls: List[str] = field(default_factory=list)
    
    def get_prompts(self):
        """获取当前模式对应的提示词"""
        mode_key = "news_brief" if "news" in self.podcast_mode.lower() else "deep_dive"
        return PROMPTS.get(mode_key, PROMPTS["deep_dive"])
    
    def get_full_voice_id(self, voice_name: str) -> str:
        """获取完整的音色ID"""
        if ":" in voice_name:
            return voice_name
        return f"{self.tts_model_name}:{voice_name}"
    
    @property
    def voice_a_full(self) -> str:
        return self.get_full_voice_id(self.voice_name_host_a)
    
    @property
    def voice_b_full(self) -> str:
        return self.get_full_voice_id(self.voice_name_host_b)
    
    def validate(self) -> tuple[bool, str]:
        """验证配置是否有效"""
        if not self.api_key or not self.api_key.strip():
            return False, "请输入 API Key"
        if not self.urls:
            return False, "请输入至少一个 URL"
        return True, ""
