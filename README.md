# 🐲 nailong-memes

<p align="center">
  <img src="https://count.getloli.com/@nailong-memes?name=nailong-memes&theme=random&padding=7&offset=0&align=top&scale=1&pixelated=1&darkmode=auto" alt="Moe Counter">
</p>


<p align="center" style="margin-top: 8px; font-size: 18px;">
  ✅ <a href="https://github.com/GGGeeeooorrrgggeee/astrbot_plugin_nailong" target="_blank">astrbot_plugin_nailong</a> 默认抽象奶龙表情包图库 ✅
</p>


<p align="center">
  <img src="https://img.shields.io/badge/Gallery-Official-blue" alt="Official Gallery">
  <img src="https://img.shields.io/badge/Type-Memes-yellow" alt="Meme Gallery">
  <a href="https://github.com/GGGeeeooorrrgggeee/nailong-memes"><img src="https://img.shields.io/github/stars/GGGeeeooorrrgggeee/nailong-memes" alt="Stars"></a>
  <a href="https://github.com/GGGeeeooorrrgggeee/nailong-memes/commits/main"><img src="https://img.shields.io/github/last-commit/GGGeeeooorrrgggeee/nailong-memes" alt="Last Commit"></a>
</p>


<p align="center">
  <strong>Language / 语言</strong><br>
  <a href="README.md"><img src="https://img.shields.io/badge/中文-当前-blue" alt="中文"></a>
</p>


---

## 一、仓库定位

本仓库是奶龙表情包资源仓库，不包含 [AstrBot](https://github.com/AstrBotDevs/AstrBot) 插件代码。

它在 `astrbot_plugin_nailong` 中承担默认图库的作用：

- 为 `astrbot_plugin_nailong` 提供默认下载图库
- 统一维护奶龙 GIF 动态表情包和静态表情包
- 方便用户快速补全本地奶龙图库
- 方便插件页面进行图库下载、分类导入和本地管理

## 二、对应插件

- 作者：[George](https://github.com/GGGeeeooorrrgggeee)
- 对应插件：`astrbot_plugin_nailong`
- 插件仓库：<https://github.com/GGGeeeooorrrgggeee/astrbot_plugin_nailong>
- 默认图库：<https://github.com/GGGeeeooorrrgggeee/nailong-memes>

## 三、仓库目录结构

本仓库按表情包类型进行分类，目录结构如下：

```text
nailong-memes/
├── gif/       # GIF 动态奶龙表情包
├── images/    # PNG/JPG/WEBP 等静态奶龙表情包
└── README.md  # 本说明文档
```

说明：

- `gif/` 目录用于存放 `.gif` 动态表情包。
- `images/` 目录用于存放 `.png`、`.jpg`、`.jpeg`、`.webp` 等静态表情包。
- 插件下载图库时会自动读取仓库压缩包中的图片文件，并按照目录或文件后缀导入到本地图库。

## 四、支持格式

插件当前支持常见图片格式，包括：

```text
.jpg .jpeg .png .gif .bmp .webp .tiff .ico
```

本图库主要使用以下格式：

- 动态表情包：`.gif`
- 静态表情包：`.png`、`.jpg`、`.jpeg`、`.webp`

## 五、在插件中下载图库

在 `astrbot_plugin_nailong` 的插件页面中，用户可以通过「下载图库」功能获取本仓库中的奶龙表情包。

插件默认图库地址为：

```text
https://github.com/GGGeeeooorrrgggeee/nailong-memes
```

下载模式说明：

| 模式       | 说明                                         |
| :--------- | :------------------------------------------- |
| 覆盖已存在 | 以默认图库内容重新导入本地图库               |
| 追加已存在 | 保留本地已有表情包，并补充默认图库中的新内容 |

插件页面同时提供 GitHub 加速地址选项，用于改善部分网络环境下的下载速度。

## 六、手动使用方式

本仓库也可以通过 GitHub 页面手动下载使用：

1. 在 GitHub 页面点击 `Code`。
2. 选择 `Download ZIP` 下载本仓库。
3. 解压后，将 `gif/` 和 `images/` 中的表情包复制到 AstrBot 的插件数据目录。

插件本地图库目录通常为：

```text
plugin_data/astrbot_plugin_nailong/
```

常见结构如下：

```text
plugin_data/astrbot_plugin_nailong/
├── gif/
├── images/
└── _hash_index.json
```

其中 `_hash_index.json` 由插件自动维护，用于记录表情包哈希信息，帮助插件处理去重、删除和重命名等操作。

## 七、图库内容说明

本仓库中的表情包按照类型进行整理：

- `gif/` 目录收录 GIF 动态奶龙表情包。
- `images/` 目录收录 PNG、JPG、WEBP 等静态奶龙表情包。
- 图库内容以抽象奶龙表情包为主。
- 本仓库只收集抽象奶龙，不收集猎奇向奶龙和可爱向奶龙。
- 仓库中的图片会作为插件默认图库资源提供给用户下载。
- 插件导入图库时会根据目录和文件后缀自动区分动态表情包与静态表情包。

## 八、与插件功能的关系

本图库被下载到本地后，会成为 `astrbot_plugin_nailong` 的本地表情包来源。插件可以使用这些表情包完成以下功能：

- 使用 `来只奶龙` 或 `奶龙` 随机发送一张奶龙表情包
- 使用 `查询奶龙数量` 查看当前图库数量
- 在普通聊天中按配置概率自动发送奶龙表情包
- 在插件页面中查看、删除、重命名和批量导出表情包
- 开启「只发送 GIF 动态表情包」后，仅从 GIF 动态表情包中随机发送
- 开启「静态图以 GIF 格式发送」后，将静态图临时转换为 GIF 后发送

## 九、使用说明

- 本仓库是图库资源仓库，不是插件安装包。
- 本仓库的收录范围为抽象奶龙表情包，不包含猎奇向或可爱向奶龙表情包。
- 插件提示「暂无奶龙表情包」时，通常表示本地图库尚未下载或尚未添加表情包。
- 覆盖下载会以默认图库为准重新导入资源；追加下载会保留本地已有表情包并补充新内容。
- 同一张表情包同时存在静态图和 GIF 两个版本时，插件会将它们视为不同文件。
- 表情包资源仅用于交流、学习和插件图库分发。涉及侵权或不宜收录的内容，可联系仓库维护者处理。

## 十、相关链接

- AstrBot：<https://github.com/AstrBotDevs/AstrBot>
- astrbot_plugin_nailong 插件：<https://github.com/GGGeeeooorrrgggeee/astrbot_plugin_nailong>
- 奶龙默认图库：<https://github.com/GGGeeeooorrrgggeee/nailong-memes>
