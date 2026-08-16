import asyncio
import base64
import hashlib
import io
import inspect
import json
import mimetypes
import os
import random
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from typing import List, Optional

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from quart import jsonify, request, send_file

try:
    from astrbot.core.utils.astrbot_path import get_astrbot_data_path
except Exception:
    get_astrbot_data_path = None

try:
    from astrbot.core.message.components import Image as AstrImage
except Exception:
    AstrImage = None

PLUGIN_NAME = "astrbot_plugin_nailong"
DEFAULT_MEME_REPO_URL = "https://github.com/GGGeeeooorrrgggeee/nailong-memes"
DEFAULT_GITHUB_ACCELERATOR_URL = ""
DEFAULT_GITHUB_ACCELERATORS = [
    {"label": "加速地址：https://edgeone.gh-proxy.com", "url": "https://edgeone.gh-proxy.com"},
    {"label": "加速地址：https://hk.gh-proxy.com/", "url": "https://hk.gh-proxy.com/"},
    {"label": "加速地址：https://gh-proxy.com/", "url": "https://gh-proxy.com/"},
    {"label": "加速地址：https://gh.llkk.cc", "url": "https://gh.llkk.cc"},
]

_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".ico"}
_GIF_DIR_NAME = "gif"
_STATIC_DIR_NAME = "images"
_HASH_INDEX_FILE = "_hash_index.json"
_DEFAULT_COMMAND_PREFIXES = {"/", "／", "!", "！", "#", "＃"}
_PLUGIN_COMMANDS = {"来只奶龙", "奶龙", "查询奶龙数量", "添加奶龙", "删除奶龙"}


@register(
    PLUGIN_NAME,
    "George",
    "奶龙表情包管理 - 随机发送奶龙表情包，支持添加、删除、插件页面管理和 GitHub 下载。",
    "1.1.0",
    "https://github.com/GGGeeeooorrrgggeee/astrbot_plugin_nailong",
)
class NailongPlugin(Star):
    """奶龙表情包管理插件。"""

    def __init__(self, context: Context, config: AstrBotConfig = None):
        super().__init__(context)
        self.config = config or {}
        self.data_dir = self._get_data_dir()
        self.command_prefixes = self._load_command_prefixes()
        self._init_image_store()
        self._register_web_api()

    def _get_data_dir(self) -> Path:
        if get_astrbot_data_path:
            try:
                data_path = Path(get_astrbot_data_path())
                if data_path.exists() or data_path.name == "data":
                    return data_path / "plugin_data" / PLUGIN_NAME
            except Exception as e:
                logger.warning(f"[奶龙插件] 获取 AstrBot 数据目录失败，将尝试常见数据目录: {e}")

        for data_path in (Path("/AstrBot/data"), Path("/app/data"), Path.cwd() / "data"):
            if data_path.exists():
                return data_path / "plugin_data" / PLUGIN_NAME

        return Path(tempfile.gettempdir()) / PLUGIN_NAME / "plugin_data"

    def _astrbot_data_root(self) -> Path:
        for path in (self.data_dir, *self.data_dir.parents):
            if path.name == "plugin_data":
                return path.parent
        return self.data_dir.parent

    def _load_command_prefixes(self) -> set:
        prefixes = set(_DEFAULT_COMMAND_PREFIXES)
        data_root = self._astrbot_data_root()
        for config_path in (data_root / "cmd_config.json", data_root / "config" / "cmd_config.json"):
            if not config_path.exists():
                continue
            try:
                data = json.loads(config_path.read_text(encoding="utf-8-sig"))
            except Exception as e:
                logger.warning(f"[奶龙插件] 读取命令前缀配置失败，将使用默认指令过滤前缀: {e}")
                continue
            for key in ("wake_prefix", "wake_prefixes", "command_prefix", "command_prefixes"):
                self._add_command_prefixes(prefixes, data.get(key))
        return {prefix for prefix in prefixes if prefix}

    @classmethod
    def _add_command_prefixes(cls, prefixes: set, value) -> None:
        if isinstance(value, str):
            if value:
                prefixes.add(value)
            return
        if isinstance(value, (list, tuple, set)):
            for item in value:
                cls._add_command_prefixes(prefixes, item)

    def _init_image_store(self) -> None:
        self._category_dir("gif")
        self._category_dir("static")

    @staticmethod
    def _list_images(directory: Path) -> List[Path]:
        if not directory.exists():
            return []
        return sorted(
            [
                f for f in directory.rglob("*")
                if f.is_file()
                and f.suffix.lower() in _IMAGE_EXTENSIONS
            ],
            key=lambda p: p.relative_to(directory).as_posix().lower(),
        )

    @staticmethod
    def _unique_path(path: Path) -> Path:
        if not path.exists():
            return path
        index = 1
        while True:
            candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
            if not candidate.exists():
                return candidate
            index += 1

    @staticmethod
    def _safe_image_name(filename: str, fallback_ext: str = ".png") -> str:
        name = Path(filename or "").name.strip()
        suffix = Path(name).suffix.lower()
        if suffix not in _IMAGE_EXTENSIONS:
            suffix = fallback_ext if fallback_ext in _IMAGE_EXTENSIONS else ".png"

        stem = Path(name).stem.strip().strip(".")
        if not stem:
            stem = f"nailong_{random.randint(100000, 999999)}"
        stem = "".join("_" if ch in '<>:"/\\|?*' or ord(ch) < 32 else ch for ch in stem).strip(" .")
        if not stem:
            stem = f"nailong_{random.randint(100000, 999999)}"
        return f"{stem}{suffix}"

    def _category_dir(self, category: str) -> Path:
        target = self.data_dir / (_GIF_DIR_NAME if category == "gif" else _STATIC_DIR_NAME)
        target.mkdir(parents=True, exist_ok=True)
        return target

    def _relative_image_name(self, path: Path) -> str:
        try:
            return path.relative_to(self.data_dir).as_posix()
        except ValueError:
            return path.name

    @property
    def _hash_index_path(self) -> Path:
        return self.data_dir / _HASH_INDEX_FILE

    def _load_hash_index(self) -> dict:
        path = self._hash_index_path
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception as e:
            logger.warning(f"[奶龙插件] 读取表情包哈希索引失败，将使用空索引: {e}")
            return {}

    def _save_hash_index(self, index: dict) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._hash_index_path.write_text(
            json.dumps(index, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def _find_image_by_hash(self, target_hash: str) -> Optional[Path]:
        for relative_name, digest in self._load_hash_index().items():
            if digest != target_hash:
                continue
            path = self._resolve_image_path(relative_name)
            if path:
                return path
        return None

    def _record_hash(self, path: Path, digest: str) -> None:
        index = self._load_hash_index()
        index[self._relative_image_name(path)] = digest
        self._save_hash_index(index)

    def _remove_hash_record(self, path: Path) -> None:
        index = self._load_hash_index()
        relative_name = self._relative_image_name(path)
        if relative_name in index:
            del index[relative_name]
            self._save_hash_index(index)

    def _rename_hash_record(self, old_path: Path, new_path: Path) -> None:
        index = self._load_hash_index()
        old_name = self._relative_image_name(old_path)
        new_name = self._relative_image_name(new_path)
        digest = index.pop(old_name, None)
        if digest:
            index[new_name] = digest
        self._save_hash_index(index)

    def _clear_image_store(self) -> int:
        image_files = self._list_images(self.data_dir)
        for path in image_files:
            path.unlink(missing_ok=True)
        self._save_hash_index({})
        return len(image_files)

    @staticmethod
    def _detect_image_extension(data: bytes) -> str:
        if data.startswith((b"GIF87a", b"GIF89a")):
            return ".gif"
        if data.startswith(b"\x89PNG\r\n\x1a\n"):
            return ".png"
        if data.startswith(b"\xff\xd8\xff"):
            return ".jpg"
        if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
            return ".webp"
        if data.startswith(b"BM"):
            return ".bmp"
        if data.startswith((b"II*\x00", b"MM\x00*")):
            return ".tiff"
        if data.startswith(b"\x00\x00\x01\x00"):
            return ".ico"
        return ""

    @staticmethod
    def _filename_with_extension(filename: str, extension: str) -> str:
        name = Path(filename or "").name.strip()
        stem = Path(name).stem.strip().strip(".") if name else ""
        if not stem:
            stem = f"nailong_{random.randint(100000, 999999)}"
        return f"{stem}{extension}"

    def _save_image_bytes_to_store(self, data: bytes, filename: str, fallback_ext: str = ".png") -> tuple:
        detected_ext = self._detect_image_extension(data)
        if detected_ext:
            filename = self._filename_with_extension(filename, detected_ext)
            fallback_ext = detected_ext
        digest = self._hash_bytes(data)
        duplicate = self._find_image_by_hash(digest)
        if duplicate:
            return None, duplicate

        safe_name = self._safe_image_name(filename, fallback_ext)
        category = "gif" if safe_name.lower().endswith(".gif") else "static"
        save_path = self._unique_path(self._category_dir(category) / safe_name)
        save_path.write_bytes(data)
        self._record_hash(save_path, digest)
        return save_path, None

    @staticmethod
    def _image_category(path: Path) -> str:
        parts = [part.lower() for part in path.parts]
        if _GIF_DIR_NAME in parts:
            return "gif"
        if _STATIC_DIR_NAME in parts:
            return "static"
        return "gif" if path.suffix.lower() == ".gif" else "static"

    def _resolve_image_path(self, filename: str) -> Optional[Path]:
        normalized = str(filename).replace("\\", "/")
        pure = PurePosixPath(normalized)
        simple_name = pure.name
        candidates = [
            self.data_dir / Path(*pure.parts),
            self.data_dir / simple_name,
            self.data_dir / _GIF_DIR_NAME / simple_name,
            self.data_dir / _STATIC_DIR_NAME / simple_name,
        ]
        data_root = self.data_dir.resolve()
        for path in candidates:
            try:
                resolved = path.resolve()
            except Exception:
                continue
            if not str(resolved).startswith(str(data_root)):
                continue
            if resolved.exists() and resolved.is_file() and resolved.suffix.lower() in _IMAGE_EXTENSIONS:
                return resolved
        return None

    @filter.command("来只奶龙")
    async def send_nailong(self, event: AstrMessageEvent, filename: str = ""):
        """随机发送或按文件名发送一张奶龙表情包。"""
        async for result in self._send_random_image(event, filename):
            yield result

    @filter.command("奶龙")
    async def send_nailong_alias(self, event: AstrMessageEvent, filename: str = ""):
        """随机发送或按文件名发送一张奶龙表情包。"""
        async for result in self._send_random_image(event, filename):
            yield result

    @filter.command("查询奶龙数量")
    async def count_nailong(self, event: AstrMessageEvent):
        """查询当前奶龙图库数量。"""
        yield event.plain_result(self._count_message())

    @filter.event_message_type(filter.EventMessageType.ALL)
    async def auto_send_nailong(self, event: AstrMessageEvent):
        """检测到普通聊天时，按配置概率自动发送一张奶龙表情包。"""
        if not self._should_auto_send(event):
            return

        async for result in self._send_random_image(event):
            yield result

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("添加奶龙")
    async def add_nailong(self, event: AstrMessageEvent):
        """配表情包或回复表情包发送“添加奶龙”，把表情包添加到本地图库。"""
        async for result in self._handle_image_upload(event):
            yield result

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("删除奶龙")
    async def del_nailong(self, event: AstrMessageEvent):
        """回复一张图库里的表情包后发送“删除奶龙”。"""
        processed, deleted = await self._delete_replied_images(event)
        failed = processed - deleted
        total = len(self._list_images(self.data_dir))

        if processed > 1:
            prefix = "✅" if deleted else "❌"
            yield event.plain_result(f"{prefix}本次预删除 {processed} 张表情包，其中成功 {deleted} 张，失败 {failed} 张。当前共 {total} 张。")
        elif deleted:
            yield event.plain_result(f"✅已删除 {deleted} 张奶龙表情包，当前还有 {total} 张。")
        else:
            yield event.plain_result("❌没有找到对应的奶龙表情包。")

    async def _send_random_image(self, event: AstrMessageEvent, filename: str = ""):
        filename = (filename or "").strip()
        image_files = self._list_images(self.data_dir)
        if not image_files:
            yield event.plain_result("❌暂无奶龙表情包！")
            return

        if filename:
            chosen = self._resolve_image_path(filename)
            if not chosen:
                yield event.plain_result(f"❌没有找到名为“{filename}”的奶龙表情包。")
                return
        elif self._get_bool_config("only_send_gif", False):
            image_files = [path for path in image_files if path.suffix.lower() == ".gif"]
            if not image_files:
                yield event.plain_result("❌当前没有 GIF 动态奶龙表情包，请先添加 GIF 表情包或关闭“只发送 GIF 动态表情包”。")
                return
            chosen = random.choice(image_files)
        else:
            chosen = random.choice(image_files)

        send_path = chosen
        temp_path = None
        try:
            if self._get_bool_config("send_as_gif", False) and chosen.suffix.lower() != ".gif":
                temp_path = await self._make_gif_copy(chosen)
                send_path = temp_path

            if AstrImage:
                try:
                    yield event.chain_result([AstrImage.fromFileSystem(str(send_path))])
                except AttributeError:
                    yield event.chain_result([AstrImage.fromBytes(send_path.read_bytes())])
            else:
                yield event.image_result(str(send_path))
        except Exception as e:
            logger.error(f"[奶龙插件] 发送表情包失败 {chosen.name}: {e}")
            yield event.plain_result("❌发送表情包失败，请稍后再试。")
        finally:
            if temp_path:
                temp_path.unlink(missing_ok=True)

    def _count_message(self) -> str:
        image_files = self._list_images(self.data_dir)
        gif_count = sum(1 for path in image_files if path.suffix.lower() == ".gif")
        static_count = len(image_files) - gif_count
        return f"奶龙表情包共 {len(image_files)} 张，其中GIF {gif_count} 张、静态 {static_count} 张！"

    def _should_auto_send(self, event: AstrMessageEvent) -> bool:
        if not self._get_bool_config("auto_send_enabled", True):
            return False
        if self._is_command_message(event):
            return False
        probability = self._get_float_config("auto_send_probability", 1.0)
        probability = max(0.0, min(100.0, probability))
        return random.random() < probability / 100.0

    def _is_command_message(self, event: AstrMessageEvent) -> bool:
        if self._event_extra_bool(event, "astrbot_known_wake_prefix_command"):
            return True

        for message_str in self._event_text_candidates(event):
            if self._is_command_text(message_str):
                return True
        return False

    def _event_text_candidates(self, event: AstrMessageEvent) -> List[str]:
        texts = []
        original = self._event_extra(event, "astrbot_original_message_str")
        current = getattr(event, "message_str", "") or ""
        for value in (original, current):
            if isinstance(value, str) and value.strip() and value not in texts:
                texts.append(value)
        return texts

    def _is_command_text(self, message_str: str) -> bool:
        text = (message_str or "").strip()
        if not text:
            return False
        first_word = text.split(None, 1)[0]
        normalized = first_word
        for prefix in sorted(self.command_prefixes, key=len, reverse=True):
            if prefix and normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
                break
        if normalized in _PLUGIN_COMMANDS:
            return True
        return any(text.startswith(prefix) for prefix in self.command_prefixes if prefix)

    @staticmethod
    def _event_extra(event: AstrMessageEvent, key: str):
        getter = getattr(event, "get_extra", None)
        if callable(getter):
            try:
                return getter(key)
            except TypeError:
                try:
                    return getter(key, None)
                except Exception:
                    return None
            except Exception:
                return None

        extras = getattr(event, "extras", None) or getattr(event, "extra", None)
        if isinstance(extras, dict):
            return extras.get(key)
        return None

    @classmethod
    def _event_extra_bool(cls, event: AstrMessageEvent, key: str) -> bool:
        value = cls._event_extra(event, key)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    async def _handle_image_upload(self, event: AstrMessageEvent):
        image_components = self._extract_image_components_with_reply(event.get_messages())
        if not image_components:
            yield event.plain_result("❌请同时发送表情包和“添加奶龙”，或回复一张表情包后发送添加奶龙。")
            return

        saved_names = []
        duplicate = 0
        failed = 0
        for image_component in image_components:
            try:
                image_url = self._get_image_url(image_component)
                if not image_url:
                    failed += 1
                    continue

                filename = self._get_image_filename(image_component) or self._guess_filename(image_url)
                ext = self._guess_extension(image_url) or Path(filename).suffix.lower()
                if ext not in _IMAGE_EXTENSIONS:
                    ext = ".png"

                data = await self._download_bytes(image_url)
                save_path, duplicate_path = self._save_image_bytes_to_store(data, filename, ext)
                if duplicate_path:
                    duplicate += 1
                    continue
                saved_names.append(self._relative_image_name(save_path))
            except Exception as e:
                logger.error(f"[奶龙插件] 添加表情包失败: {e}")
                failed += 1

        processed = len(saved_names) + duplicate + failed
        total = len(self._list_images(self.data_dir))
        if not saved_names:
            if duplicate == 1 and processed == 1:
                yield event.plain_result("❌该奶龙表情包已存在，请勿重复添加！")
                return
            if duplicate or failed:
                yield event.plain_result(f"❌本次预添加 {processed} 张表情包，其中新增 0 张，本地已存在 {duplicate} 张，添加失败 {failed} 张。当前共 {total} 张。")
                return
            yield event.plain_result("❌添加失败，请确认发送的是有效表情包。")
            return

        if processed > 1:
            message = f"✅本次预添加 {processed} 张表情包，其中新增 {len(saved_names)} 张，本地已存在 {duplicate} 张，添加失败 {failed} 张。当前共 {total} 张。"
        else:
            message = f"✅成功添加 {len(saved_names)} 张奶龙表情包，当前共 {total} 张。"
        yield event.plain_result(message)

    def _delete_images(self, filenames: List[str]) -> int:
        deleted = 0
        for filename in filenames:
            path = self._resolve_image_path(filename)
            if path:
                path.unlink()
                self._remove_hash_record(path)
                deleted += 1
        return deleted

    def _rename_image(self, old_name: str, new_name: str) -> Optional[Path]:
        source = self._resolve_image_path(old_name)
        if not source:
            return None

        suffix = Path(new_name).suffix.lower() or source.suffix.lower()
        if suffix not in _IMAGE_EXTENSIONS:
            suffix = source.suffix.lower()
        safe_name = self._safe_image_name(new_name, suffix)
        target = source.with_name(safe_name)
        if target == source:
            return source
        target = self._unique_path(target)
        source.rename(target)
        self._rename_hash_record(source, target)
        return target

    async def _delete_replied_images(self, event: AstrMessageEvent) -> tuple:
        image_components = self._extract_image_components_with_reply(event.get_messages())
        if not image_components:
            return 0, 0

        deleted = 0
        processed = 0
        for image_component in image_components:
            processed += 1
            try:
                image_url = self._get_image_url(image_component)
                if not image_url:
                    continue
                data = await self._download_bytes(image_url)
                target_path = self._find_image_by_hash(self._hash_bytes(data))
                if target_path:
                    target_path.unlink()
                    self._remove_hash_record(target_path)
                    deleted += 1
            except Exception as e:
                logger.error(f"[奶龙插件] 回复表情包删除失败: {e}")
        return processed, deleted

    async def _download_github_pack(self, repo_url: str, accelerator: str = "", mode: str = "overwrite") -> dict:
        archive_url = self._github_archive_url((repo_url or "").strip() or DEFAULT_MEME_REPO_URL)
        download_url = self._apply_accelerator(archive_url, accelerator)
        mode = "append" if mode == "append" else "overwrite"

        with tempfile.TemporaryDirectory(prefix="nailong_") as temp_dir:
            archive_path = Path(temp_dir) / "repo.zip"
            await self._download_file(download_url, archive_path)

            imported = 0
            skipped = 0
            appended = 0
            overwritten = 0
            duplicate = 0
            overwrite_hash_index = {}
            if mode == "overwrite":
                overwritten = self._clear_image_store()

            with zipfile.ZipFile(archive_path, "r") as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    archive_item = PurePosixPath(info.filename)
                    suffix = Path(archive_item.name).suffix.lower()
                    if suffix not in _IMAGE_EXTENSIONS:
                        skipped += 1
                        continue

                    category = self._github_item_category(archive_item, suffix)
                    save_name = self._safe_image_name(archive_item.name, suffix)
                    target_path = self._category_dir(category) / save_name
                    with zf.open(info) as src:
                        data = src.read()
                    digest = self._hash_bytes(data)
                    existing_by_hash = self._find_image_by_hash(digest)

                    if mode == "append":
                        if existing_by_hash:
                            duplicate += 1
                            continue
                        save_path = self._unique_path(target_path)
                        if target_path.exists():
                            appended += 1
                        else:
                            imported += 1
                    else:
                        save_path = target_path
                        imported += 1

                    save_path.write_bytes(data)
                    if mode == "overwrite":
                        overwrite_hash_index[self._relative_image_name(save_path)] = digest
                    else:
                        self._record_hash(save_path, digest)

            if mode == "overwrite":
                self._save_hash_index(overwrite_hash_index)

        return {
            "imported": imported,
            "skipped": skipped,
            "appended": appended,
            "overwritten": overwritten,
            "duplicate": duplicate,
            "total": len(self._list_images(self.data_dir)),
            "mode": mode,
        }

    @staticmethod
    def _github_item_category(path: PurePosixPath, suffix: str) -> str:
        parts = [part.lower() for part in path.parts]
        if _GIF_DIR_NAME in parts:
            return "gif"
        if _STATIC_DIR_NAME in parts:
            return "static"
        return "gif" if suffix == ".gif" else "static"

    @staticmethod
    def _github_archive_url(repo_url: str) -> str:
        parsed = urllib.parse.urlparse(repo_url)
        path_parts = [p for p in parsed.path.strip("/").split("/") if p]
        if parsed.netloc.lower() != "github.com" or len(path_parts) < 2:
            raise ValueError("请填写 GitHub 项目地址，例如 https://github.com/用户/仓库。")

        owner, repo = path_parts[0], path_parts[1]
        branch = "main"
        if len(path_parts) >= 4 and path_parts[2] == "tree":
            branch = path_parts[3]
        return f"https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip"

    @staticmethod
    def _apply_accelerator(url: str, accelerator: str = "") -> str:
        accelerator = (accelerator or "").strip()
        if not accelerator:
            return url
        if "{url}" in accelerator:
            return accelerator.replace("{url}", url)
        return accelerator.rstrip("/") + "/" + url

    def _register_web_api(self) -> None:
        register_api = getattr(self.context, "register_web_api", None)
        if not callable(register_api):
            logger.info("[奶龙插件] 当前 AstrBot 版本未提供 register_web_api，插件页面接口跳过注册。")
            return

        register_api(f"/{PLUGIN_NAME}/list", self.page_list_images, ["GET"], "列出奶龙表情包")
        register_api(f"/{PLUGIN_NAME}/upload", self.page_upload_images, ["POST"], "上传奶龙表情包")
        register_api(f"/{PLUGIN_NAME}/delete", self.page_delete_images, ["POST"], "删除奶龙表情包")
        register_api(f"/{PLUGIN_NAME}/download", self.page_download_pack, ["POST"], "从 GitHub 下载奶龙表情包")
        register_api(f"/{PLUGIN_NAME}/test-accelerator", self.page_test_accelerator, ["POST"], "测试 GitHub 加速地址")
        register_api(f"/{PLUGIN_NAME}/export", self.page_export_images, ["POST"], "导出奶龙表情包")
        register_api(f"/{PLUGIN_NAME}/export-file", self.page_export_file, ["GET"], "下载奶龙表情包压缩包")
        register_api(f"/{PLUGIN_NAME}/image-data", self.page_image_data, ["GET"], "读取奶龙表情包原图")
        register_api(f"/{PLUGIN_NAME}/logo-data", self.page_logo_data, ["GET"], "读取奶龙插件图标")
        register_api(f"/{PLUGIN_NAME}/rename", self.page_rename_image, ["POST"], "重命名奶龙表情包")

    async def page_list_images(self):
        images = self._web_image_list()
        return jsonify(
            {
                "images": images,
                "count": len(images),
                "gif_count": sum(1 for image in images if image["category"] == "gif"),
                "static_count": sum(1 for image in images if image["category"] == "static"),
                "official_repo_url": DEFAULT_MEME_REPO_URL,
                "github_accelerator": DEFAULT_GITHUB_ACCELERATOR_URL,
                "github_accelerators": DEFAULT_GITHUB_ACCELERATORS,
            }
        ), 200

    async def page_upload_images(self):
        saved = []
        duplicate = 0
        try:
            files = await request.files
            upload = files.get("file") if files else None
            if upload and getattr(upload, "filename", ""):
                save_path, duplicate_path = await self._save_upload_to_store(upload)
                if duplicate_path:
                    duplicate += 1
                else:
                    saved.append(self._relative_image_name(save_path))
                return jsonify({"message": "表情包添加完成", "saved": saved, "duplicate": duplicate, "count": len(self._list_images(self.data_dir))}), 201
        except Exception as e:
            logger.warning(f"[奶龙插件] 表单上传读取失败，尝试 JSON 兼容模式: {e}")

        payload = await self._page_payload()
        files = self._read_payload_files(payload)
        if not files:
            return jsonify({"message": "请选择要上传的表情包。"}), 400

        for filename, data in files:
            save_path, duplicate_path = self._save_image_bytes_to_store(data, filename, Path(filename).suffix.lower() or ".png")
            if duplicate_path:
                duplicate += 1
                continue
            saved.append(self._relative_image_name(save_path))
        return jsonify({"message": "表情包添加完成", "saved": saved, "duplicate": duplicate, "count": len(self._list_images(self.data_dir))}), 201

    async def page_image_data(self):
        name = str(request.args.get("name") or request.args.get("filename") or "")
        size = str(request.args.get("size") or "preview")
        path = self._resolve_image_path(name)
        if not path:
            return jsonify({"status": "error", "message": "表情包不存在。"}), 404
        max_bytes = 32 * 1024 * 1024 if size == "original" else 8 * 1024 * 1024
        file_size = path.stat().st_size
        if file_size > max_bytes:
            return jsonify({"status": "error", "message": "表情包太大，无法在插件页面预览。", "size": file_size, "max_size": max_bytes}), 413
        media_type = mimetypes.guess_type(str(path))[0] or "image/png"
        data_url = self._build_preview_data_url(path) if size == "preview" else self._inline_data_url(path, media_type)
        return jsonify(
            {
                "name": self._relative_image_name(path),
                "filename": path.name,
                "mime_type": media_type,
                "size": file_size,
                "data_url": data_url,
            }
        ), 200

    async def page_logo_data(self):
        logo_path = Path(__file__).resolve().parent / "logo.png"
        if not logo_path.exists():
            return jsonify({"message": "logo.png 不存在。"}), 404
        media_type = mimetypes.guess_type(str(logo_path))[0] or "image/png"
        return jsonify({"data_url": self._inline_data_url(logo_path, media_type)}), 200

    async def page_delete_images(self):
        payload = await self._page_payload()
        names = []
        if isinstance(payload, dict):
            names = payload.get("names") or payload.get("filenames") or []
        if isinstance(names, str):
            names = [names]
        deleted = self._delete_images([str(name) for name in names])
        return jsonify({"message": "表情包删除完成", "deleted": deleted, "count": len(self._list_images(self.data_dir))}), 200

    async def page_rename_image(self):
        payload = await self._page_payload()
        data = payload if isinstance(payload, dict) else {}
        old_name = str(data.get("name") or "")
        new_name = str(data.get("new_name") or "")
        renamed = self._rename_image(old_name, new_name)
        if not renamed:
            return jsonify({"message": "重命名失败，请确认表情包存在且新文件名有效。"}), 400
        return jsonify({"message": "已重命名", "name": self._relative_image_name(renamed), "filename": renamed.name}), 200

    async def page_download_pack(self):
        payload = await self._page_payload()
        data = payload if isinstance(payload, dict) else {}
        try:
            accelerator = str(data["accelerator"]) if "accelerator" in data else DEFAULT_GITHUB_ACCELERATOR_URL
            result = await self._download_github_pack(
                str(data.get("repo_url") or data.get("url") or DEFAULT_MEME_REPO_URL),
                accelerator,
                str(data.get("mode") or data.get("download_mode") or "overwrite"),
            )
        except Exception as e:
            logger.error(f"[奶龙插件] GitHub 表情包下载失败: {e}")
            return jsonify({"message": str(e)}), 400
        return jsonify(result), 200

    async def page_test_accelerator(self):
        payload = await self._page_payload()
        data = payload if isinstance(payload, dict) else {}
        try:
            repo_url = str(data.get("repo_url") or data.get("url") or DEFAULT_MEME_REPO_URL)
            archive_url = self._github_archive_url(repo_url)
            accelerators = data.get("accelerators")
            if isinstance(accelerators, list):
                results = []
                for item in accelerators:
                    if not isinstance(item, dict):
                        continue
                    url = str(item.get("url") or "")
                    if not url:
                        continue
                    started = time.perf_counter()
                    try:
                        await self._probe_url(self._apply_accelerator(archive_url, url))
                        latency_ms = int((time.perf_counter() - started) * 1000)
                        results.append({"url": url, "ok": True, "latency_ms": latency_ms})
                    except Exception as e:
                        results.append({"url": url, "ok": False, "message": str(e)})
                return jsonify({"results": results}), 200

            accelerator = str(data.get("accelerator") or "")
            started = time.perf_counter()
            await self._probe_url(self._apply_accelerator(archive_url, accelerator))
            latency_ms = int((time.perf_counter() - started) * 1000)
        except Exception as e:
            return jsonify({"message": str(e)}), 400
        return jsonify({"message": "加速地址连通性正常。", "latency_ms": latency_ms}), 200

    async def page_export_images(self):
        payload = await self._page_payload()
        names = []
        if isinstance(payload, dict):
            names = payload.get("names") or []
        if isinstance(names, str):
            names = [names]

        files = [path for name in names if (path := self._resolve_image_path(str(name)))]
        if not files:
            return jsonify({"message": "请选择要下载的表情包。"}), 400

        if len(files) == 1:
            path = files[0]
            media_type, _ = mimetypes.guess_type(str(path))
            return jsonify(
                {
                    "filename": path.name,
                    "mime": media_type or "application/octet-stream",
                    "data": base64.b64encode(path.read_bytes()).decode("ascii"),
                }
            ), 200

        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in files:
                zf.write(path, self._relative_image_name(path))
        return jsonify(
            {
                "filename": "nailong-memes.zip",
                "mime": "application/zip",
                "data": base64.b64encode(buffer.getvalue()).decode("ascii"),
            }
        ), 200

    async def page_export_file(self):
        names_text = request.args.get("names", "")
        names = []
        if names_text:
            try:
                parsed = json.loads(str(names_text))
                if isinstance(parsed, list):
                    names = [str(name) for name in parsed]
            except Exception:
                for name in str(names_text).split("\n"):
                    name = name.strip()
                    if name:
                        names.append(name)

        files = [path for name in names if (path := self._resolve_image_path(str(name)))]
        if not files:
            return jsonify({"message": "请选择要下载的表情包。"}), 400

        export_dir = Path(tempfile.gettempdir()) / PLUGIN_NAME / "exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        export_path = export_dir / f"nailong-memes-{os.urandom(4).hex()}.zip"
        with zipfile.ZipFile(export_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in files:
                zf.write(path, self._relative_image_name(path))

        try:
            return await send_file(str(export_path), as_attachment=True, download_name="nailong-memes.zip", mimetype="application/zip")
        except TypeError:
            return await send_file(str(export_path), as_attachment=True, attachment_filename="nailong-memes.zip", mimetype="application/zip")

    @staticmethod
    async def _page_payload(payload=None) -> dict:
        if isinstance(payload, dict):
            return payload
        try:
            data = await request.get_json(silent=True)
            if isinstance(data, dict):
                return data
        except Exception:
            return {}
        return {}

    @staticmethod
    def _read_payload_files(payload: dict = None) -> List[tuple]:
        if not isinstance(payload, dict):
            return []

        files = []
        for item in payload.get("files") or []:
            if not isinstance(item, dict):
                continue
            filename = str(item.get("name") or "")
            data_url = str(item.get("data") or "")
            if not filename or "," not in data_url:
                continue
            try:
                _, encoded = data_url.split(",", 1)
                files.append((filename, base64.b64decode(encoded)))
            except Exception:
                continue
        return files

    def _web_image_list(self) -> List[dict]:
        images = []
        for path in self._list_images(self.data_dir):
            relative_name = self._relative_image_name(path)
            stat = path.stat()
            images.append(
                {
                    "name": relative_name,
                    "filename": path.name,
                    "category": self._image_category(path),
                    "size": stat.st_size,
                    "mtime": int(stat.st_mtime),
                    "mtime_ns": stat.st_mtime_ns,
                }
            )
        return sorted(images, key=lambda image: (-image["mtime_ns"], image["filename"].lower()))

    async def _save_upload_to_store(self, upload) -> tuple:
        upload_name = str(getattr(upload, "filename", "") or getattr(upload, "name", "") or "")
        suffix = Path(upload_name).suffix.lower()
        result = upload.read()
        if inspect.isawaitable(result):
            data = await result
        else:
            data = result
        return self._save_image_bytes_to_store(data, upload_name, suffix or ".png")

    @staticmethod
    def _extract_image_components(message_chain) -> List:
        images = []
        for comp in message_chain:
            type_name = type(comp).__name__
            comp_type = getattr(comp, "type", "")
            if "Image" in type_name or comp_type == "image":
                images.append(comp)
        return images

    def _extract_image_components_with_reply(self, message_chain) -> List:
        images = self._extract_image_components(message_chain)
        if images:
            return images

        for comp in message_chain:
            type_name = type(comp).__name__
            comp_type = getattr(comp, "type", "")
            if "Reply" in type_name or comp_type == "reply":
                chain = getattr(comp, "chain", None)
                if chain:
                    return self._extract_image_components(chain)
        return []

    @staticmethod
    def _get_image_url(comp) -> Optional[str]:
        url = getattr(comp, "url", None) or getattr(comp, "image_url", None) or ""
        if url:
            return url
        file_attr = getattr(comp, "file", "")
        if file_attr and (file_attr.startswith("file://") or file_attr.startswith("http")):
            return file_attr
        return None

    @staticmethod
    def _get_image_filename(comp) -> str:
        for attr in ("filename", "name", "file_name"):
            value = getattr(comp, attr, "")
            if value:
                return Path(str(value)).name
        file_attr = getattr(comp, "file", "")
        if file_attr and not str(file_attr).startswith("base64://"):
            return Path(str(file_attr).split("?", 1)[0]).name
        url = getattr(comp, "url", None) or getattr(comp, "image_url", None) or ""
        return NailongPlugin._guess_filename(url) if url else ""

    @staticmethod
    def _guess_filename(url: str) -> str:
        name = urllib.parse.unquote(Path(urllib.parse.urlparse(url).path).name)
        if name and "." in name:
            return name
        return f"nailong_{random.randint(100000, 999999)}.png"

    @staticmethod
    def _guess_extension(url: str) -> str:
        ext = Path(urllib.parse.unquote(urllib.parse.urlparse(url).path)).suffix.lower()
        return ext if ext in _IMAGE_EXTENSIONS else ""

    @staticmethod
    async def _download_file(url: str, save_path: Path) -> None:
        data = await NailongPlugin._download_bytes(url)
        save_path.write_bytes(data)

    @staticmethod
    async def _download_bytes(url: str) -> bytes:
        if url.startswith("file://"):
            return Path(urllib.parse.unquote(url[7:])).read_bytes()

        def _sync_download():
            req = urllib.request.Request(url, headers={"User-Agent": f"{PLUGIN_NAME}/1.1"})
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    return resp.read()
            except urllib.error.HTTPError as e:
                if e.code in {502, 503, 504}:
                    raise RuntimeError(f"下载失败：当前 GitHub 加速地址返回 HTTP {e.code}，请换一个加速地址或选择直连。")
                raise RuntimeError(f"下载失败：HTTP {e.code}。")
            except urllib.error.URLError as e:
                raise RuntimeError(f"下载失败：无法连接到下载地址，原因：{e.reason}")

        return await asyncio.get_event_loop().run_in_executor(None, _sync_download)

    @staticmethod
    async def _probe_url(url: str) -> None:
        def _sync_probe():
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": f"{PLUGIN_NAME}/1.1",
                    "Range": "bytes=0-0",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=12) as resp:
                    resp.read(1)
            except urllib.error.HTTPError as e:
                if e.code in {502, 503, 504}:
                    raise RuntimeError(f"测试失败：当前 GitHub 加速地址返回 HTTP {e.code}。")
                raise RuntimeError(f"测试失败：HTTP {e.code}。")
            except urllib.error.URLError as e:
                raise RuntimeError(f"测试失败：无法连接到加速地址，原因：{e.reason}")

        await asyncio.get_event_loop().run_in_executor(None, _sync_probe)

    @staticmethod
    def _hash_bytes(data: bytes) -> str:
        return hashlib.md5(data).hexdigest()

    @staticmethod
    def _inline_data_url(path: Path, media_type: str = None) -> str:
        media_type = media_type or mimetypes.guess_type(str(path))[0] or "image/png"
        return f"data:{media_type};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"

    def _build_preview_data_url(self, path: Path) -> str:
        media_type = mimetypes.guess_type(str(path))[0] or "image/png"
        try:
            from PIL import Image

            with Image.open(path) as img:
                if getattr(img, "is_animated", False):
                    img.seek(0)
                image = img.convert("RGBA")
                image.thumbnail((512, 512))
                buffer = io.BytesIO()
                image.save(buffer, format="WEBP", quality=80, method=6)
            return f"data:image/webp;base64,{base64.b64encode(buffer.getvalue()).decode('ascii')}"
        except Exception as e:
            logger.warning(f"[奶龙插件] 生成页面预览失败，将返回原图: {path.name}: {e}")
            return self._inline_data_url(path, media_type)

    @staticmethod
    async def _make_gif_copy(path: Path) -> Path:
        temp_path = Path(tempfile.gettempdir()) / f"nailong_send_{os.getpid()}_{random.randint(100000, 999999)}.gif"
        try:
            from PIL import Image

            def _convert():
                with Image.open(path) as img:
                    img.save(temp_path, format="GIF")

            await asyncio.get_event_loop().run_in_executor(None, _convert)
        except Exception:
            shutil.copy2(path, temp_path)
        return temp_path

    def _get_bool_config(self, key: str, default: bool) -> bool:
        value = self.config.get(key, default)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on", "开启", "启用"}
        return bool(value)

    def _get_float_config(self, key: str, default: float) -> float:
        value = self.config.get(key, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @filter.on_astrbot_loaded()
    async def on_loaded(self):
        logger.info(f"[奶龙插件] 已启动，图库路径：{self.data_dir}，共 {len(self._list_images(self.data_dir))} 张表情包。")

    async def terminate(self):
        logger.info("[奶龙插件] 已卸载，持久图库文件已保留。")
