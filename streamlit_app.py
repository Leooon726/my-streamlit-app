import streamlit as st
from datetime import datetime
import pytz
import time

st.set_page_config(page_title="世界时钟", page_icon="🌍", layout="centered")

st.title("🌍 世界时钟")
st.markdown("---")

# 定义时区
timezones = {
    "🇨🇳 上海": "Asia/Shanghai",
    "🇺🇸 纽约": "America/New_York"
}

# 创建占位符用于实时更新
placeholder = st.empty()

# 自动刷新
while True:
    with placeholder.container():
        cols = st.columns(len(timezones))
        
        for idx, (city, tz_name) in enumerate(timezones.items()):
            tz = pytz.timezone(tz_name)
            current_time = datetime.now(tz)
            
            with cols[idx]:
                st.subheader(city)
                st.markdown(f"### 🕐 {current_time.strftime('%H:%M:%S')}")
                st.markdown(f"📅 {current_time.strftime('%Y年%m月%d日')}")
                st.markdown(f"📆 {current_time.strftime('%A')}")
    
    time.sleep(1)
