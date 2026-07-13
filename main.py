import os
import shutil
import random
import hashlib
from pathlib import Path
from typing import List, Optional

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star, register

# ---------------------------------------------------------------------------
# 路径常量
# ---------------------------------------------------------------------------

_PLUGIN_DIR = Path(__file__).resolve().parent
_INIT_IMG_DIR = _PLUGIN_DIR / "init_img"
_DATA_DIR = _PLUGIN_DIR.parent.parent / "plugin_data" / "astrbot_plugin_nailong"

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".ico"}


# ---------------------------------------------------------------------------
# 插件注册
# ---------------------------------------------------------------------------

@register(
    "astrbot_plugin_nailong",
    "George",
    "奶龙表情包管理 - 随机发送奶龙表情包，支持上传、配图删除表情包、后台管理",
    "v1.2.0",
    "",
)
class NailongPlugin(Star):
    """奶龙表情包管理插件主类。"""

    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config or {}
        self.plugin_dir = _PLUGIN_DIR
        self.init_img_dir = _INIT_IMG_DIR
        self.data_dir = _DATA_DIR

        # 初始化持久图库
        self._init_image_store()

    # ------------------------------------------------------------------ #
    #  初始化：持久图库
    # ------------------------------------------------------------------ #

    def _init_image_store(self) -> None:
        """
        初始化持久图库目录。
        - 持久图库不存在或为空 → 从 init_img 复制初始素材
        - 持久图库已有文件     → 跳过复制
        """
        self.data_dir.mkdir(parents=True, exist_ok=True)

        if not self._has_images(self.data_dir):
            if self.init_img_dir.exists():
                copied = 0
                for item in self.init_img_dir.iterdir():
                    if item.is_file():
                        dest = self.data_dir / item.name
                        if not dest.exists():
                            shutil.copy2(item, dest)
                            copied += 1
                logger.info(
                    f"[奶龙插件] 已从 init_img 复制 {copied} 个文件到持久图库。"
                )
            else:
                logger.warning("[奶龙插件] init_img 目录不存在。")
        else:
            count = self._count_images(self.data_dir)
            logger.info(f"[奶龙插件] 持久图库已有 {count} 个文件，跳过复制。")

    @staticmethod
    def _has_images(directory: Path) -> bool:
        if not directory.exists():
            return False
        for f in directory.iterdir():
            if f.is_file() and f.suffix.lower() in _IMAGE_EXTENSIONS:
                return True
        return False

    @staticmethod
    def _count_images(directory: Path) -> int:
        if not directory.exists():
            return 0
        return sum(
            1 for f in directory.iterdir()
            if f.is_file() and f.suffix.lower() in _IMAGE_EXTENSIONS
        )

    @staticmethod
    def _list_images(directory: Path) -> List[Path]:
        if not directory.exists():
            return []
        return [
            f for f in directory.iterdir()
            if f.is_file() and f.suffix.lower() in _IMAGE_EXTENSIONS
        ]

    # ------------------------------------------------------------------ #
    # 消息事件处理
    # ------------------------------------------------------------------ #

    @filter.command("来只奶龙")
    async def send_nailong(self, event: AstrMessageEvent):
        """随机发送一张奶龙表情包"""
        async for r in self._send_random_image(event):
            yield r

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("添加奶龙")
    async def add_nailong(self, event: AstrMessageEvent):
        """配表情包/回复表情包发送「添加奶龙」，把表情包添加到本地图库中，管理员专用"""
        async for r in self._handle_image_upload(event):
            yield r

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("删除奶龙")
    async def del_nailong(self, event: AstrMessageEvent):
        """
        配表情包/回复表情包发送「删除奶龙」，自动计算表情包哈希并删除图库内对应表情包，管理员专用
        """
        message_chain = event.get_messages()
        image_components = self._extract_image_components(message_chain)

        # 无图则检查回复消息
        if not image_components:
            for comp in message_chain:
                type_name = type(comp).__name__
                comp_type = getattr(comp, "type", "")
                if "Reply" in type_name or comp_type == "reply":
                    chain = getattr(comp, "chain", None)
                    if chain:
                        image_components = self._extract_image_components(chain)
                    break

        if not image_components:
            yield event.plain_result("请附带表情包发送「删除奶龙」，或回复一张表情包再发送该指令！")
            return

        count_before = self._count_images(self.data_dir)
        del_count = 0

        for img_comp in image_components:
            try:
                image_url = self._get_image_url(img_comp)
                if not image_url:
                    continue

                # 下载临时图片用于计算哈希
                temp_path = self.data_dir / f"_tmp_del_{os.getpid()}_{id(img_comp)}"
                await self._download_image(image_url, temp_path)
                # 计算原图MD5哈希
                target_hash = self._compute_file_hash(temp_path)
                temp_path.unlink(missing_ok=True)

                # 遍历图库匹配对应哈希的图片
                target_file: Optional[Path] = None
                all_imgs = self._list_images(self.data_dir)
                for img_path in all_imgs:
                    stem = img_path.stem
                    if stem.startswith("nailong_"):
                        file_hash = stem.replace("nailong_", "", 1)
                        if file_hash == target_hash:
                            target_file = img_path
                            break

                if target_file is None:
                    continue

                # 删除文件
                target_file.unlink(missing_ok=False)
                del_count += 1
                logger.info(f"[奶龙插件] 删除图片 {target_file.name}，哈希 {target_hash}")

            except Exception as e:
                logger.error(f"[奶龙插件] 删除流程异常: {e}")
                continue

        count_after = self._count_images(self.data_dir)
        if del_count == 0:
            yield event.plain_result("该奶龙表情包不存在！")
        else:
            msg = f"成功删除 {del_count} 张奶龙表情包！当前还剩 {count_after} 张。"
            yield event.plain_result(msg)

    async def _send_random_image(self, event: AstrMessageEvent):
        """从持久图库随机选取一张图片发送。"""
        image_files = self._list_images(self.data_dir)

        if not image_files:
            yield event.plain_result("暂无奶龙表情包！请管理员「添加奶龙」新增奶龙表情包。")
            return

        chosen = random.choice(image_files)
        try:
            from astrbot.core.message.components import Image as _Img
            try:
                yield event.chain_result([_Img.fromFileSystem(str(chosen))])
            except AttributeError:
                with open(str(chosen), "rb") as _f:
                    yield event.chain_result([_Img.fromBytes(_f.read())])
        except Exception as e:
            logger.error(f"[奶龙插件] 发送图片失败 {chosen.name}: {e}")
            yield event.plain_result("发送图片失败，请稍后再试")

    # ------------------------------------------------------------------ #
    #  上传表情包
    # ------------------------------------------------------------------ #

    async def _handle_image_upload(self, event: AstrMessageEvent):
        """
        下载图片并保存到持久图库。
        支持直接发图+key词，也支持回复某张图片并发key词。
        """
        message_chain = event.get_messages()
        image_components = self._extract_image_components(message_chain)

        if not image_components:
            for comp in message_chain:
                type_name = type(comp).__name__
                comp_type = getattr(comp, "type", "")
                if "Reply" in type_name or comp_type == "reply":
                    chain = getattr(comp, "chain", None)
                    if chain:
                        image_components = self._extract_image_components(chain)
                    break

        if not image_components:
            yield event.plain_result("请同时发送图片和文字「添加奶龙」，或回复某张图片发送添加奶龙")
            return

        success_count = 0
        fail_count = 0
        exists_count = 0
        count_before = self._count_images(self.data_dir)

        for img_comp in image_components:
            try:
                image_url = self._get_image_url(img_comp)
                if not image_url:
                    fail_count += 1
                    continue

                ext = self._guess_extension(image_url)
                temp_path = self.data_dir / f"_tmp_{os.getpid()}_{id(img_comp)}"
                await self._download_image(image_url, temp_path)

                if not ext:
                    raw_data = temp_path.read_bytes()
                    ext = self._detect_ext_from_content(raw_data)
                    new_temp = temp_path.with_suffix(ext)
                    temp_path.rename(new_temp)
                    temp_path = new_temp

                content_hash = self._compute_file_hash(temp_path)
                save_path = self.data_dir / f"nailong_{content_hash}{ext}"

                if save_path.exists():
                    exists_count += 1
                    temp_path.unlink(missing_ok=True)
                    continue

                temp_path.rename(save_path)
                success_count += 1

            except Exception as e:
                logger.error(f"[奶龙插件] 下载图片失败: {e}")
                fail_count += 1

        count_after = self._count_images(self.data_dir)
        new_count = count_after - count_before

        if success_count > 0:
            msg = f"成功添加 {new_count} 张奶龙表情包！当前共 {count_after} 张。"
            if exists_count > 0:
                msg += f"（{exists_count} 张重复，已跳过）"
            if fail_count > 0:
                msg += f"（{fail_count} 张下载失败）"
            yield event.plain_result(msg)
        elif exists_count > 0:
            yield event.plain_result("此奶龙表情包已存在，不能重复添加！")
        else:
            yield event.plain_result("添加失败，请确认发送的是有效图片。")

    # ------------------------------------------------------------------ #
    #  图片工具方法
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_image_components(message_chain) -> List:
        """从消息链中提取 Image 组件。"""
        images = []
        for comp in message_chain:
            type_name = type(comp).__name__
            comp_type = getattr(comp, "type", "")
            if "Image" in type_name or comp_type == "image":
                images.append(comp)
        return images

    @staticmethod
    def _get_image_url(comp) -> Optional[str]:
        """从 Image 组件中提取可下载的 URL。"""
        url = getattr(comp, "url", None) or getattr(comp, "image_url", None) or ""
        if url:
            return url
        file_attr = getattr(comp, "file", "")
        if file_attr and file_attr.startswith("file://"):
            return file_attr
        return None

    @staticmethod
    async def _download_image(url: str, save_path: Path) -> None:
        """异步下载图片（使用标准库 urllib）。"""
        import asyncio
        import urllib.request
        def _sync():
            with urllib.request.urlopen(url, timeout=30) as resp:
                return resp.read()
        loop = asyncio.get_event_loop()
        data = await loop.run_in_executor(None, _sync)
        save_path.write_bytes(data)

    @staticmethod
    def _compute_file_hash(file_path: Path) -> str:
        """
        基于图片文件内容本身计算 MD5 哈希。
        同一张图片哈希完全一致。
        """
        hash_md5 = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()[:16]

    @staticmethod
    def _guess_extension(url: str) -> str:
        path = url.split("?")[0].split("/")[-1]
        if "." in path:
            ext = "." + path.rsplit(".", 1)[-1].lower()
            if ext in _IMAGE_EXTENSIONS:
                return ext
        if "." in url:
            ext = "." + url.rsplit(".", 1)[-1].split("?")[0].lower()
            if ext in _IMAGE_EXTENSIONS:
                return ext
        return ""

    @staticmethod
    def _detect_ext_from_content(data: bytes) -> str:
        if data[:6] == b"GIF87a" or data[:6] == b"GIF89a":
            return ".gif"
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return ".png"
        if data[:2] == b"\xff\xd8":
            return ".jpg"
        if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            return ".webp"
        if data[:2] == b"BM":
            return ".bmp"
        if data[:4] in (b"II*\x00", b"MM\x00*"):
            return ".tiff"
        return ".png"

    # ------------------------------------------------------------------ #
    #  插件生命周期
    # ------------------------------------------------------------------ #

    @staticmethod
    def _is_admin(event) -> bool:
        role = getattr(event, "role", "member")
        if role in ("admin", "owner"):
            return True
        if getattr(event, "is_admin", False):
            return True
        return False

    @filter.on_astrbot_loaded()
    async def on_loaded(self):
        count = self._count_images(self.data_dir)
        logger.info(
            f"[奶龙插件] 已启动！持久图库路径：{self.data_dir}，共 {count} 张表情包。"
        )

    async def terminate(self):
        logger.info("[奶龙插件] 已卸载。持久图库文件已保留。")