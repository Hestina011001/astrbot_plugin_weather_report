# 🌤️ AstrBot 天气预报插件

> 本插件全程代码由 DeepSeek 编写，作者希斯蒂娜 Hestina 负责策划、调试与发布。

> 定时推送高德天气预报，支持从 AstrBot 数据库自动加载人格设定。

[![version](https://img.shields.io/badge/version-1.1.0-blue)]()

## ✨ 特性

- ⏰ 定时推送指定城市的天气预报
- 🎭 **全局人格模式**：自动使用 AstrBot 中的默认人格（或数据库第一个人格）
- 🎯 **指定人格模式**：通过 `/list_personas` 查看所有人格 ID，手动选择你要的 ID
- 🖥️ 纯 WebUI 配置，无需修改代码
- 🔍 提供 `/weather_test_verbose` 诊断命令，`/list_personas` 列出人格

## 📦 安装

1. 将 `astrbot_plugin_weather_report` 文件夹打包为 `.zip`
2. AstrBot WebUI → 插件管理 → 从文件安装 → 上传 `.zip`
3. 启用插件

## 🔑 如何获取高德地图 API Key

本插件需要使用高德地图 API 来获取天气数据，因此你需要在[高德开放平台](https://lbs.amap.com/)注册账号并申请一个 **Web 服务** 类型的 API Key。

1.  **注册与登录**
    访问[高德开放平台](https://lbs.amap.com/)，点击右上角“注册”完成账号注册，之后登录[reference:0][reference:1]。

2.  **创建应用并添加 Key**
    *   登录后，进入 **控制台**，在左侧导航栏选择 **应用管理** -> **我的应用**[reference:2]。
    *   点击右上角的 **创建新应用**，填写应用名称并选择应用类型（如“其它”）[reference:3]。
    *   创建成功后，点击应用下的 **添加 Key**，在弹出的对话框中，**服务平台** 一项务必选择 **Web 服务 (Web API)**[reference:4][reference:5]。

3.  **获取并使用 Key**
    添加成功后，你就能看到生成的 API Key（通常是一串复杂的字符）。把它复制下来，填入本插件的 **`高德地图 API Key`** 配置项中即可[reference:6]。

## ⚙️ 配置

| 配置项 | 必填 | 说明 |
|--------|------|------|
| 高德地图 API Key | ✅ | 高德开放平台 Web 服务 Key |
| 城市代码 | ✅ | 例如北京 `110000` |
| 定时推送时间 | ✅ | 格式 `HH:MM`，如 `07:30` |
| 目标会话 UMO | ✅ | 在目标会话发送 `/get_umo` 获得 |
| 人格模式 | ✅ | `global`（自动）或 `selected`（手动指定 ID） |
| 指定人格 ID | 当模式为 `selected` 时必填 | 通过 `/list_personas` 获取的 ID，例如 `猫娘` |
| LLM API Key | ✅ | 你的 API Key（DeepSeek、火山引擎等） |
| LLM API Base URL | ✅ | API 地址，程序会自动拼接 `/chat/completions` |
| LLM 模型名称 | ✅ | 模型名，如 `deepseek-chat` |

## 💬 指令

| 指令 | 作用 |
|------|------|
| `/weather_test` | 手动查询天气 |
| `/weather_test_verbose` | 详细诊断信息 |
| `/get_umo` | 获取当前会话 UMO |
| `/list_personas` | 列出数据库中所有可用人格 ID 及预览 |

## 🧠 人格自动加载说明

- **global 模式**：插件会读取 AstrBot 主配置文件中的 `default_personality` 的值，并尝试加载对应的人格。如果该值无效或不存在，则自动选择数据库 `personas` 表中的第一个人格（按 `persona_id` 排序）。
- **selected 模式**：你通过 `/list_personas` 查看所有人格的 ID，然后在插件配置中填入你想用的那个 ID，插件就会精确加载那个人格。

## 🙏 致谢

- **DeepSeek（深度求索）**
- **AstrBot** 
- **高德地图**