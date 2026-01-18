"""
存储模块：Supabase Storage 集成
"""
from typing import Optional, Tuple
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
    
    def _generate_filename(self, prefix: str, ext: str) -> str:
        """生成唯一文件名"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # 添加短 hash 避免冲突
        hash_suffix = hashlib.md5(f"{timestamp}{prefix}".encode()).hexdigest()[:6]
        return f"{prefix}_{timestamp}_{hash_suffix}.{ext}"
    
    def upload_audio(
        self,
        audio_bytes: bytes,
        filename: Optional[str] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        上传音频文件
        
        Args:
            audio_bytes: 音频二进制数据
            filename: 可选的文件名，不提供则自动生成
            
        Returns:
            (success, message, public_url)
        """
        if not audio_bytes:
            return False, "音频数据为空", None
        
        if not filename:
            filename = self._generate_filename("podcast", "mp3")
        
        # 确保文件名在 audio 文件夹下
        filepath = f"audio/{filename}"
        
        try:
            # 上传文件
            result = self.client.storage.from_(self.bucket).upload(
                path=filepath,
                file=audio_bytes,
                file_options={"content-type": "audio/mpeg"}
            )
            
            # 获取公开 URL
            public_url = self.client.storage.from_(self.bucket).get_public_url(filepath)
            
            return True, f"上传成功: {filepath}", public_url
            
        except Exception as e:
            return False, f"上传失败: {type(e).__name__}: {e}", None
    
    def upload_script(
        self,
        script_text: str,
        filename: Optional[str] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        上传脚本文件
        
        Args:
            script_text: 脚本文本内容
            filename: 可选的文件名，不提供则自动生成
            
        Returns:
            (success, message, public_url)
        """
        if not script_text:
            return False, "脚本内容为空", None
        
        if not filename:
            filename = self._generate_filename("script", "txt")
        
        # 确保文件名在 scripts 文件夹下
        filepath = f"scripts/{filename}"
        
        try:
            # 转换为 bytes
            script_bytes = script_text.encode('utf-8')
            
            # 上传文件
            result = self.client.storage.from_(self.bucket).upload(
                path=filepath,
                file=script_bytes,
                file_options={"content-type": "text/plain; charset=utf-8"}
            )
            
            # 获取公开 URL
            public_url = self.client.storage.from_(self.bucket).get_public_url(filepath)
            
            return True, f"上传成功: {filepath}", public_url
            
        except Exception as e:
            return False, f"上传失败: {type(e).__name__}: {e}", None
    
    def upload_results(
        self,
        audio_bytes: Optional[bytes],
        script_text: Optional[str]
    ) -> dict:
        """
        上传所有结果文件
        
        Returns:
            {
                "audio": {"success": bool, "message": str, "url": str},
                "script": {"success": bool, "message": str, "url": str}
            }
        """
        results = {}
        
        # 生成统一的时间戳前缀
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        hash_suffix = hashlib.md5(timestamp.encode()).hexdigest()[:6]
        base_name = f"podcast_{timestamp}_{hash_suffix}"
        
        # 上传音频
        if audio_bytes:
            success, msg, url = self.upload_audio(
                audio_bytes, 
                f"{base_name}.mp3"
            )
            results["audio"] = {"success": success, "message": msg, "url": url}
        else:
            results["audio"] = {"success": False, "message": "无音频数据", "url": None}
        
        # 上传脚本
        if script_text:
            success, msg, url = self.upload_script(
                script_text,
                f"{base_name}.txt"
            )
            results["script"] = {"success": success, "message": msg, "url": url}
        else:
            results["script"] = {"success": False, "message": "无脚本内容", "url": None}
        
        return results
