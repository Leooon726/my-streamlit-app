"""
存储模块：Supabase Storage 集成
"""
from typing import Optional, Tuple, List, Dict, Any
from datetime import datetime
import hashlib

from supabase import create_client, Client


class SupabaseStorage:
    """Supabase Storage 客户端"""
    
    def __init__(
        self,
        url: str,
        key: str,
        bucket: str = "podcast-material"
    ):
        self.url = url
        self.key = key
        self.bucket = bucket
        self.client: Client = create_client(url, key)
    
    def _generate_id(self) -> str:
        """生成唯一 ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        hash_suffix = hashlib.md5(f"{timestamp}".encode()).hexdigest()[:6]
        return f"{timestamp}_{hash_suffix}"
    
    def upload_audio(
        self,
        audio_bytes: bytes,
        podcast_id: str
    ) -> Tuple[bool, Optional[str]]:
        """上传音频文件"""
        if not audio_bytes:
            return False, None
        
        filepath = f"audio/{podcast_id}.mp3"
        
        try:
            self.client.storage.from_(self.bucket).upload(
                path=filepath,
                file=audio_bytes,
                file_options={"content-type": "audio/mpeg"}
            )
            public_url = self.client.storage.from_(self.bucket).get_public_url(filepath)
            return True, public_url
        except Exception as e:
            print(f"Audio upload error: {e}")
            return False, None
    
    def upload_script(
        self,
        script_text: str,
        podcast_id: str
    ) -> Tuple[bool, Optional[str]]:
        """上传脚本文件"""
        if not script_text:
            return False, None
        
        filepath = f"scripts/{podcast_id}.txt"
        
        try:
            script_bytes = script_text.encode('utf-8')
            self.client.storage.from_(self.bucket).upload(
                path=filepath,
                file=script_bytes,
                file_options={"content-type": "text/plain; charset=utf-8"}
            )
            public_url = self.client.storage.from_(self.bucket).get_public_url(filepath)
            return True, public_url
        except Exception as e:
            print(f"Script upload error: {e}")
            return False, None
    
    def save_podcast(
        self,
        title: str,
        audio_bytes: Optional[bytes],
        script_text: Optional[str],
        source_urls: List[str] = None
    ) -> Dict[str, Any]:
        """
        保存播客（上传文件 + 保存元数据到数据库）
        
        Returns:
            {
                "success": bool,
                "id": str,
                "audio_url": str,
                "script_url": str,
                "message": str
            }
        """
        podcast_id = self._generate_id()
        result = {
            "success": False,
            "id": podcast_id,
            "audio_url": None,
            "script_url": None,
            "message": ""
        }
        
        # 上传音频
        if audio_bytes:
            success, url = self.upload_audio(audio_bytes, podcast_id)
            if success:
                result["audio_url"] = url
        
        # 上传脚本
        if script_text:
            success, url = self.upload_script(script_text, podcast_id)
            if success:
                result["script_url"] = url
        
        # 保存元数据到数据库
        try:
            metadata = {
                "id": podcast_id,
                "title": title,
                "audio_url": result["audio_url"],
                "script_url": result["script_url"],
                "source_urls": source_urls or [],
                "created_at": datetime.now().isoformat()
            }
            
            self.client.table("podcasts").insert(metadata).execute()
            result["success"] = True
            result["message"] = "保存成功"
            
        except Exception as e:
            # 如果数据库保存失败，文件仍然上传成功
            result["success"] = result["audio_url"] is not None or result["script_url"] is not None
            result["message"] = f"文件已上传，但元数据保存失败: {e}"
        
        return result
    
    def list_podcasts(self, limit: int = 20) -> List[Dict[str, Any]]:
        """
        获取播客列表
        
        Returns:
            [{"id", "title", "audio_url", "script_url", "created_at", "source_urls"}, ...]
        """
        try:
            response = self.client.table("podcasts") \
                .select("*") \
                .order("created_at", desc=True) \
                .limit(limit) \
                .execute()
            
            return response.data or []
            
        except Exception as e:
            print(f"List podcasts error: {e}")
            return []
    
    def get_podcast(self, podcast_id: str) -> Optional[Dict[str, Any]]:
        """获取单个播客详情"""
        try:
            response = self.client.table("podcasts") \
                .select("*") \
                .eq("id", podcast_id) \
                .single() \
                .execute()
            
            return response.data
            
        except Exception as e:
            print(f"Get podcast error: {e}")
            return None
    
    def get_script_content(self, script_url: str) -> Optional[str]:
        """从 URL 获取脚本内容"""
        try:
            import requests
            response = requests.get(script_url, timeout=10)
            if response.status_code == 200:
                return response.text
            return None
        except Exception as e:
            print(f"Get script error: {e}")
            return None
    
    def delete_podcast(self, podcast_id: str) -> bool:
        """删除播客"""
        try:
            # 删除文件
            self.client.storage.from_(self.bucket).remove([
                f"audio/{podcast_id}.mp3",
                f"scripts/{podcast_id}.txt"
            ])
            
            # 删除数据库记录
            self.client.table("podcasts").delete().eq("id", podcast_id).execute()
            
            return True
        except Exception as e:
            print(f"Delete podcast error: {e}")
            return False
