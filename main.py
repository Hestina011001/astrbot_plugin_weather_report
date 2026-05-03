import asyncio
import aiohttp
import json
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from astrbot.api import logger
from astrbot.api.message_components import Plain


@register(
    "astrbot_plugin_weather_report",
    "希斯蒂娜Hestina",
    "定时推送高德天气预报（优化播报完整性）",
    "1.1.0",
    "https://github.com/yourname/astrbot_plugin_weather_report"
)
class WeatherReportPlugin(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.config = config or {}
        self.api_key = self.config.get("api_key", "")
        self.city_code = self.config.get("city_code", "")
        self.target_session = self.config.get("target_session", "")
        self.persona_mode = self.config.get("persona_mode", "global")
        self.selected_persona_id = self.config.get("selected_persona_id", "")
        self.llm_api_key = self.config.get("deepseek_api_key", "")
        self.api_base_url = self.config.get("api_base_url", "https://api.deepseek.com/v1")
        self.model_name = self.config.get("model_name", "deepseek-chat")
        if self.api_base_url.endswith('/'):
            self.api_base_url = self.api_base_url[:-1]
        push_time_str = self.config.get("push_time", "07:30")
        self.push_hour, self.push_minute = self._parse_time(push_time_str)

        self._task = None
        self._running = False
        self.effective_persona_prompt = ""

    def _parse_time(self, time_str: str):
        try:
            if ":" in time_str:
                parts = time_str.split(":")
                hour = int(parts[0])
                minute = int(parts[1])
                if 0 <= hour <= 23 and 0 <= minute <= 59:
                    return hour, minute
        except:
            pass
        return 7, 30

    def _load_persona_by_id(self, persona_id: str) -> str:
        """根据 persona_id 从数据库加载 system_prompt"""
        db_path = "/AstrBot/data/data_v4.db"
        if not os.path.exists(db_path):
            logger.warning(f"数据库不存在: {db_path}")
            return ""
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT system_prompt FROM personas WHERE persona_id = ?", (persona_id,))
            row = cursor.fetchone()
            conn.close()
            if row and row[0]:
                logger.info(f"成功加载人格 '{persona_id}'，长度 {len(row[0])}")
                return row[0]
            else:
                logger.warning(f"未找到 persona_id 为 '{persona_id}' 的人格")
                return ""
        except Exception as e:
            logger.error(f"加载人格失败: {e}", exc_info=True)
            return ""

    def _load_global_default_persona(self) -> str:
        """加载 AstrBot 全局默认人格，若 default_personality 无效则自动选择第一个人格"""
        db_path = "/AstrBot/data/data_v4.db"
        if not os.path.exists(db_path):
            logger.warning(f"数据库不存在: {db_path}")
            return ""

        # 1. 获取配置中的 default_personality
        default_id = None
        try:
            with open("/AstrBot/data/cmd_config.json", "r", encoding="utf-8-sig") as f:
                cfg = json.load(f)
            default_id = cfg.get("provider_settings", {}).get("default_personality", "").strip()
            if not default_id:
                logger.warning("cmd_config.json 中未设置 default_personality")
        except Exception as e:
            logger.warning(f"读取 cmd_config.json 失败: {e}")

        # 2. 尝试精确匹配
        if default_id:
            prompt = self._load_persona_by_id(default_id)
            if prompt:
                return prompt
            else:
                logger.warning(f"未找到 default_personality 指定的 ID '{default_id}'，将自动选择第一个人格")

        # 3. 精确匹配失败，则自动取数据库中第一条人格记录
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT persona_id, system_prompt FROM personas ORDER BY persona_id LIMIT 1")
            row = cursor.fetchone()
            conn.close()
            if row:
                pid, prompt = row
                logger.info(f"自动选择数据库中的第一个人格 '{pid}'，长度 {len(prompt)}")
                return prompt
            else:
                logger.warning("personas 表为空")
                return ""
        except Exception as e:
            logger.error(f"读取数据库失败: {e}", exc_info=True)
            return ""

    async def _list_personas(self) -> list:
        """返回数据库中所有人格的 (persona_id, system_prompt 前50字符) 列表"""
        db_path = "/AstrBot/data/data_v4.db"
        if not os.path.exists(db_path):
            return []
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT persona_id, system_prompt FROM personas")
            rows = cursor.fetchall()
            conn.close()
            return [(pid, prompt[:50] + "..." if len(prompt) > 50 else prompt) for pid, prompt in rows]
        except Exception as e:
            logger.error(f"列出人格失败: {e}")
            return []

    async def _call_llm_api(self, prompt: str, max_tokens: int = 500) -> str:
        if not self.llm_api_key:
            return ""
        url = f"{self.api_base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.llm_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": max_tokens
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, timeout=30) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data["choices"][0]["message"]["content"].strip()
                    else:
                        error_text = await resp.text()
                        logger.error(f"LLM API 调用失败 [{resp.status}] 响应内容: {error_text}")
                        return ""
        except Exception as e:
            logger.error(f"LLM API 调用异常: {e}", exc_info=True)
            return ""

    async def _rewrite_weather_with_persona(self, raw_weather: str, umo: str) -> tuple[str, str]:
        persona = self.effective_persona_prompt
        if not persona:
            return raw_weather, "无人格提示词"

        user_prompt = (
            f"{persona}\n\n"
            f"请以你的角色口吻，完整、准确地播报以下天气预报。\n"
            f"必须包含：日期、白天天气、白天温度、夜间天气、夜间温度、风力。\n"
            f"你可以加入符合角色的语气词和表达方式，但不要遗漏任何数据，也不要额外编造生活情节。\n\n"
            f"天气预报原文：\n{raw_weather}"
        )

        if self.llm_api_key:
            result = await self._call_llm_api(user_prompt, max_tokens=500)
            if result:
                return result, f"通过 LLM API 调用成功 (base: {self.api_base_url}, model: {self.model_name})"
            else:
                return raw_weather, "LLM API 调用失败（请查看日志中的详细错误）"

        return raw_weather, "未配置 LLM API Key"

    async def _get_weather(self) -> Optional[str]:
        if not self.api_key or not self.city_code:
            return None

        url = f"https://restapi.amap.com/v3/weather/weatherInfo?key={self.api_key}&city={self.city_code}&extensions=all"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    data = await resp.json()
                    if data.get("status") != "1":
                        logger.error(f"高德 API 错误: {data}")
                        return None
                    forecasts = data.get("forecasts", [])
                    if not forecasts:
                        return None
                    fc = forecasts[0]
                    city = fc.get("city", "未知城市")
                    casts = fc.get("casts", [])
                    if not casts:
                        return None
                    today = casts[0]
                    date = today.get("date", "未知日期")
                    day_weather = today.get("dayweather", "未知")
                    night_weather = today.get("nightweather", "未知")
                    day_temp = today.get("daytemp", "N/A")
                    night_temp = today.get("nighttemp", "N/A")
                    day_wind = today.get("daywind", "未知")
                    night_wind = today.get("nightwind", "未知")

                    return (
                        f"【{city}天气预报】\n"
                        f"日期：{date}\n"
                        f"白天：{day_weather}，{day_temp}℃\n"
                        f"夜间：{night_weather}，{night_temp}℃\n"
                        f"风力：白天 {day_wind} / 夜间 {night_wind}"
                    )
        except Exception as e:
            logger.error(f"获取天气失败: {e}")
            return None

    async def _send_weather_report(self):
        logger.info("=== _send_weather_report 被调用 ===")
        if not self.target_session:
            logger.warning("未设置目标会话 UMO")
            return
        logger.info(f"目标会话: {self.target_session}")
        raw = await self._get_weather()
        if raw:
            logger.info("获取原始天气成功，开始人格改写")
            final, _ = await self._rewrite_weather_with_persona(raw, self.target_session)
            logger.info(f"人格改写完成，消息长度: {len(final)}")
            try:
                class _FakeMessageChain:
                    def __init__(self, comps):
                        self.chain = comps
                message_chain = _FakeMessageChain([Plain(final)])
                await self.context.send_message(self.target_session, message_chain)
                logger.info(f"✅ 已推送天气至 {self.target_session}")
            except Exception as e:
                logger.error(f"❌ 发送消息失败: {type(e).__name__}: {e}", exc_info=True)
        else:
            logger.error("获取天气失败，推送取消")

    async def _scheduled_weather_push(self):
        while self._running:
            now = datetime.now()
            target = now.replace(hour=self.push_hour, minute=self.push_minute, second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
            wait = (target - now).total_seconds()
            logger.info(f"距离下次推送还有 {wait/3600:.1f} 小时")
            await asyncio.sleep(wait)
            if not self._running:
                break
            await self._send_weather_report()

    async def initialize(self):
        if not self.api_key or not self.city_code:
            logger.warning("请填写高德 API Key 和城市代码")
            return
        if not self.target_session:
            logger.warning("请填写目标会话 UMO")
            return

        # 根据人格模式加载有效人格
        if self.persona_mode == "global":
            self.effective_persona_prompt = self._load_global_default_persona()
            if self.effective_persona_prompt:
                logger.info(f"使用全局默认人格，长度 {len(self.effective_persona_prompt)}")
            else:
                logger.error("全局默认人格加载失败，请确保数据库中存在至少一个人格记录。")
        elif self.persona_mode == "selected":
            if not self.selected_persona_id:
                logger.warning("selected 模式但未填写 selected_persona_id")
            else:
                self.effective_persona_prompt = self._load_persona_by_id(self.selected_persona_id)
                if self.effective_persona_prompt:
                    logger.info(f"使用指定人格 '{self.selected_persona_id}'，长度 {len(self.effective_persona_prompt)}")
                else:
                    logger.warning(f"未找到人格 ID '{self.selected_persona_id}'")
        else:
            logger.warning(f"未知的人格模式: {self.persona_mode}，将使用 global 模式")
            self.effective_persona_prompt = self._load_global_default_persona()

        if self._task is None or self._task.done():
            self._running = True
            self._task = asyncio.create_task(self._scheduled_weather_push())
            logger.info(f"定时推送已启动，时间 {self.push_hour:02d}:{self.push_minute:02d}，人格模式: {self.persona_mode}")

    async def terminate(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            logger.info("定时任务已停止")

    async def run(self):
        await self.initialize()

    @filter.command("weather_test")
    async def weather_test(self, event: AstrMessageEvent):
        raw = await self._get_weather()
        if raw:
            final, _ = await self._rewrite_weather_with_persona(raw, event.unified_msg_origin)
            yield event.plain_result(final)
        else:
            yield event.plain_result("❌ 获取天气失败，请检查配置")

    @filter.command("weather_test_verbose")
    async def weather_test_verbose(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin
        report = []
        report.append(f"API Key: {'已配置' if self.api_key else '❌ 未配置'}")
        report.append(f"城市代码: {self.city_code if self.city_code else '❌ 未配置'}")
        report.append(f"目标UMO: {self.target_session if self.target_session else '❌ 未配置'}")
        report.append(f"人格模式: {self.persona_mode}")

        if self.persona_mode == "global":
            if self.effective_persona_prompt:
                report.append(f"✅ 全局默认人格已加载 (长度: {len(self.effective_persona_prompt)})")
            else:
                report.append("❌ 全局人格加载失败或为空")
        elif self.persona_mode == "selected":
            if self.selected_persona_id:
                report.append(f"指定人格 ID: {self.selected_persona_id}")
                if self.effective_persona_prompt:
                    report.append(f"✅ 已加载指定人格 (长度: {len(self.effective_persona_prompt)})")
                else:
                    report.append("❌ 加载指定人格失败，请检查 ID 是否正确")
            else:
                report.append("❌ 未填写指定人格 ID")
        else:
            report.append(f"人格模式未知: {self.persona_mode}")

        if self.llm_api_key:
            report.append(f"✅ LLM API Key 已配置，API Base URL: {self.api_base_url}, 模型: {self.model_name}")
        else:
            report.append("⚠️ LLM API Key 未配置，无法进行人格改写")
            report.append("提示：请在插件配置中填写 LLM API Key 和模型名称")

        raw = await self._get_weather()
        if not raw:
            report.append("❌ 获取原始天气失败")
            yield event.plain_result("\n".join(report))
            return

        report.append(f"✅ 原始天气:\n{raw}")
        final, debug = await self._rewrite_weather_with_persona(raw, umo)
        report.append(f"调试信息: {debug}")
        report.append("--- 最终结果 ---")
        report.append(final)
        yield event.plain_result("\n".join(report))

    @filter.command("get_umo")
    async def get_umo(self, event: AstrMessageEvent):
        umo = event.unified_msg_origin
        yield event.plain_result(f"当前会话 UMO：\n`{umo}`\n请复制此值填入插件配置的「目标会话UMO」。")

    @filter.command("list_personas")
    async def list_personas(self, event: AstrMessageEvent):
        """列出所有可用人格 ID 及其提示词预览"""
        personas = await self._list_personas()
        if not personas:
            yield event.plain_result("❌ 无法获取人格列表，请确保数据库存在或联系管理员。")
            return
        msg = "📋 可用人格列表：\n"
        for pid, preview in personas:
            msg += f"- **{pid}**: {preview}\n"
        msg += "\n你可以将上述 **ID** 复制到插件配置的「指定人格 ID」字段，并将人格模式设为 `selected`。"
        yield event.plain_result(msg)