# 声桥 VoiceBridge

轻量的实时语音翻译客户端：Windows/macOS 使用 Python + Tkinter，Android 使用原生 Java + AudioRecord/AudioTrack。语音直接连接配置的模型接口，不经额外的业务服务器。

## 公开版与私有版

公开源码、默认构建都不包含 API key。用户在设置中填写 API key、WSS 接口地址、模型名称、协议版本和声音复刻接口。协议支持 `qwen38` 与 `qwen35`（千问实时翻译的两种事件格式）；允许填写兼容模型名称，不表示任何聊天模型或任意服务商均可直接使用。

私有构建需显式添加 `--private` 并设置 `VOICEBRIDGE_EMBED_KEY`。该密钥会进入二进制，不能视为无法提取的秘密。不要把私有 APK/DMG、签名密钥、构建缓存或用户声音库上传到公开 GitHub/Release。构建脚本不会默认读取你的个人密钥。

用户配置的密钥优先于内置密钥：Windows 使用 DPAPI，macOS 使用钥匙串，Android 使用 Android Keystore AES-GCM。密钥不会写入普通设置 JSON 或导出记录。

## 多语言

输入语言自动识别，选择目标语言即可在支持的输入语言间切换互译。首批提供英语、中文、日语、韩语、法语、德语、西班牙语、葡萄牙语、俄语、阿拉伯语的语音与文字输出；另提供意大利语、印地语、印度尼西亚语、越南语、泰语、土耳其语、荷兰语、波兰语、瑞典语、乌克兰语的文字模式。后者是客户端当前保守选项，不代表模型永远不支持这些语言的语音。更换模型后的可用语言取决于服务商支持范围。

## 功能与边界

- 实时音量、双语文字、流式译音、暂停输入、多人命名声音库、录音创建音色、术语表、本地历史与导出。
- Android 使用麦克风前台服务与常驻通知，用户可随时停止；录音权限必须先由用户同意。普通历史存储不保存原始音频。
- 默认约 5 分钟在停顿处续接会话，另监测保守 token 用量阈值；连续讲话最多额外等待约 30 秒。重连时待发送音频最多缓存 60 秒。
- 网络断开时，已经发出但尚未返回结果的末尾不保证无损；不重放整个历史以避免大段重复。实时复刻在新会话需要重新提取音色，长时间使用建议预先保存声音。
- 固定音色与模型相关；更换模型可能需要重新创建。语音克隆只使用自己的或已获授权的声音。
- 桌面支持 TXT/JSON/SRT；Android 支持系统文件选择器导出 TXT。移动端路由由 Android 管理，实际蓝牙设备表现需要实机验证。

## 桌面运行/构建

Python 3.13+，带 Tk。安装 `pip install .`，运行 `voicebridge`。打包时安装 PyInstaller，然后运行 `python scripts/build_desktop.py`。macOS 必须在 Mac 上构建，会生成拖入 Applications 安装的 DMG；生成的临时签名不是 Apple Developer ID 签名或公证。

GitHub Actions 工作流同时构建 Apple Silicon 和 Intel 版。默认公开构建不读取密钥。只有私有仓库中手动选择 `private_build` 才会读取同名 `VOICEBRIDGE_EMBED_KEY` 仓库 Secret。私有构建完成后应删除临时 Secret，并保管含密钥产物。

## Android 构建

需要 JDK 17、Android SDK platform 35、build-tools 36.0.0，以及 `ANDROID_HOME`。不需要 Gradle，脚本使用官方 AAPT2、javac、D8、zipalign 和 apksigner。

    python scripts/build_android.py

默认产生不含 API key 的 APK，签名文件放在忽略的 build 目录。正式连续发布请指定 `--keystore` 并使用环境变量 `VOICEBRIDGE_STORE_PASSWORD`，保留同一签名密钥才能覆盖升级。最低 Android 8.0 (API 26)。

Java-WebSocket 1.6.0（MIT）、SLF4J 2.0.16（MIT）从 Maven Central 下载。应用本身使用 MIT 许可；依赖保留各自许可证。发布前执行 `python scripts/check_source.py`，并只上传本目录的源码，不要上传外层工作区。

## 验证状态

见项目交付时的验证报告。编译成功不能代替真实手机音频和 Mac 麦克风的实机验证。
