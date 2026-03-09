#!/usr/bin/env python3
"""
Prism v3 — 消融实验 & 模型规模实验
统一 llama.cpp /v1/chat/completions API。
只负责收集模型原始输出，不评分（评分由后续步骤完成）。

V3 扩展:
  - 14个用户（10 原始 user_XX + 4 拼音 ID）
  - Config H prompt 增加危机检测指令
  - 输出到 v3/results/ablation/raw/

两种实验模式:
  --experiment ablation  → 8种数据配置 × N用户 (实验A: 跨域消融)
  --experiment scale     → 全景H配置 × N用户 (实验B: 模型规模曲线)
"""

import argparse
import json
import time
import requests
from datetime import datetime
from pathlib import Path

# ── 14个用户 ────────────────────────────────────────────────────

ALL_USERS = [f"user_{i:02d}" for i in range(1, 11)] + [
    "lixiang", "wangguilan", "zhangxiuying", "chenmo",
]

# ── 8种消融配置 ──────────────────────────────────────────────────

CONFIGS = {
    "A": {"apps": ["dailyn"], "label": "仅财务"},
    "B": {"apps": ["mealens"], "label": "仅饮食"},
    "C": {"apps": ["ururu"], "label": "仅情绪"},
    "D": {"apps": ["narrus"], "label": "仅阅读"},
    "E": {"apps": ["dailyn", "mealens"], "label": "财务×饮食"},
    "F": {"apps": ["dailyn", "ururu"], "label": "财务×情绪"},
    "G": {"apps": ["mealens", "ururu"], "label": "饮食×情绪"},
    "H": {"apps": ["dailyn", "mealens", "ururu", "narrus"], "label": "全景整合"},
}

APP_NAMES = {
    "dailyn": "Dailyn（个人财务）",
    "mealens": "Mealens（饮食记录）",
    "ururu": "Ururu（情绪日记）",
    "narrus": "Narrus（阅读记录）",
}

# ── 数据加载 ─────────────────────────────────────────────────────


def load_user_data(data_dir, user_id):
    """加载用户所有app数据（v2 schema）"""
    user_dir = Path(data_dir) / user_id
    data = {}
    for app in ["dailyn", "mealens", "ururu", "narrus"]:
        filepath = user_dir / f"{app}.json"
        if filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                data[app] = json.load(f)
    meta_path = user_dir / "meta.json"
    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            data["meta"] = json.load(f)
    return data


# ── v2 Schema 数据摘要 ──────────────────────────────────────────


def summarize_app_data(app_name, records, last_n_days=30):
    """将 v2 schema 的 app 数据压缩为 LLM 可读摘要"""
    if not records:
        return "无数据"

    # 取最近N天
    dates = sorted(set(r.get("date", "") for r in records))
    if len(dates) > last_n_days:
        cutoff = dates[-last_n_days]
        records = [r for r in records if r.get("date", "") >= cutoff]

    if app_name == "dailyn":
        return _summarize_dailyn(records)
    elif app_name == "mealens":
        return _summarize_mealens(records)
    elif app_name == "ururu":
        return _summarize_ururu(records)
    elif app_name == "narrus":
        return _summarize_narrus(records)
    return "未知app类型"


def _summarize_dailyn(records):
    """v2 schema: 每天一条记录，含 records 数组"""
    total_expense = 0
    monthly_income = 0
    cat_totals = {}
    daily_expenses = {}

    for day_rec in records:
        date = day_rec.get("date", "")
        if day_rec.get("monthly_income"):
            monthly_income = day_rec["monthly_income"]
        day_total = 0
        for r in day_rec.get("records", []):
            cat = r.get("category", "其他")
            amount = r.get("amount", 0)
            cat_totals[cat] = cat_totals.get(cat, 0) + amount
            day_total += amount
        total_expense += day_total
        daily_expenses[date] = day_total

    avg_daily = total_expense / max(1, len(daily_expenses))
    savings_rate = ((monthly_income - total_expense / max(1, len(records)) * 30) / max(1, monthly_income) * 100) if monthly_income > 0 else 0
    cat_str = ", ".join(f"{k}:{v:.0f}元" for k, v in sorted(cat_totals.items(), key=lambda x: -x[1]))

    # 异常消费日
    anomaly_days = [(d, v) for d, v in daily_expenses.items() if v > avg_daily * 2.5]
    anomaly_str = "; ".join(f"{d}消费{v:.0f}元" for d, v in sorted(anomaly_days)[:3])

    # 前后半段对比
    mid = len(records) // 2
    first_half = sum(daily_expenses.get(r["date"], 0) for r in records[:mid])
    second_half = sum(daily_expenses.get(r["date"], 0) for r in records[mid:])

    return (
        f"月收入: {monthly_income:.0f}元 | 期间总支出: {total_expense:.0f}元 | 预估储蓄率: {savings_rate:.1f}%\n"
        f"支出分布: {cat_str}\n"
        f"日均支出: {avg_daily:.0f}元 | 记录天数: {len(daily_expenses)}\n"
        f"异常消费日: {anomaly_str if anomaly_str else '无明显异常'}\n"
        f"前半段支出: {first_half:.0f}元 → 后半段: {second_half:.0f}元"
    )


def _summarize_mealens(records):
    """v2 schema: 每天一条记录，含 meals 数组"""
    total_meals = 0
    total_calories = 0
    healthy_count = 0
    skip_breakfast = 0
    total_breakfast = 0
    late_meals = 0
    food_count = {}
    water_total = 0

    for day_rec in records:
        cal = day_rec.get("daily_calories", 0)
        total_calories += cal
        water_total += day_rec.get("water_ml", 0)
        has_breakfast = False
        for meal in day_rec.get("meals", []):
            total_meals += 1
            mt = meal.get("meal_type", "")
            if mt == "breakfast":
                has_breakfast = True
                total_breakfast += 1
            tags = meal.get("tags", [])
            if "健康" in tags or "自制" in tags:
                healthy_count += 1
            if meal.get("time", "") >= "22:00":
                late_meals += 1
            for food in meal.get("foods", []):
                food_count[food] = food_count.get(food, 0) + 1
        if not has_breakfast:
            skip_breakfast += 1

    avg_cal = total_calories / max(1, len(records))
    skip_rate = (skip_breakfast / max(1, len(records))) * 100
    top_foods = sorted(food_count.items(), key=lambda x: -x[1])[:5]

    # 前后半段热量对比
    mid = len(records) // 2
    cal_first = sum(r.get("daily_calories", 0) for r in records[:mid])
    cal_second = sum(r.get("daily_calories", 0) for r in records[mid:])

    return (
        f"总餐次: {total_meals} | 日均热量: {avg_cal:.0f}kcal | 日均饮水: {water_total // max(1, len(records))}ml\n"
        f"健康饮食比例: {healthy_count}/{total_meals} ({healthy_count / max(1, total_meals) * 100:.0f}%)\n"
        f"跳过早餐率: {skip_rate:.0f}% | 深夜进食: {late_meals}次\n"
        f"高频食物: {', '.join(f'{f}({c}次)' for f, c in top_foods)}\n"
        f"前半段日均热量: {cal_first / max(1, mid):.0f} → 后半段: {cal_second / max(1, len(records) - mid):.0f}"
    )


def _summarize_ururu(records):
    """v2 schema: 每天一条记录"""
    moods = [r.get("mood_score", 0.5) for r in records]
    avg_mood = sum(moods) / max(1, len(moods))

    # 情绪分布
    emotion_count = {}
    for r in records:
        e = r.get("primary_emotion", "")
        emotion_count[e] = emotion_count.get(e, 0) + 1
    emotion_str = ", ".join(f"{k}({v}次)" for k, v in sorted(emotion_count.items(), key=lambda x: -x[1])[:5])

    # 睡眠
    sleeps = [r.get("sleep_hours", 7) for r in records]
    avg_sleep = sum(sleeps) / max(1, len(sleeps))

    # 压力
    stress = [r.get("stress_level", 5) for r in records]
    avg_stress = sum(stress) / max(1, len(stress))

    # 日记
    snippets = [r.get("journal_snippet", "") for r in records if r.get("journal_snippet")]
    sample = snippets[0][:100] if snippets else "无"

    # 前后半段对比
    mid = len(records) // 2
    mood_first = sum(r.get("mood_score", 0.5) for r in records[:mid]) / max(1, mid)
    mood_second = sum(r.get("mood_score", 0.5) for r in records[mid:]) / max(1, len(records) - mid)

    # 关键词统计
    all_keywords = []
    for r in records:
        all_keywords.extend(r.get("journal_keywords", []))
    kw_count = {}
    for kw in all_keywords:
        kw_count[kw] = kw_count.get(kw, 0) + 1
    top_kw = sorted(kw_count.items(), key=lambda x: -x[1])[:5]

    return (
        f"情绪均值: {avg_mood:.2f}/1.0 | 记录天数: {len(records)}\n"
        f"主要情绪: {emotion_str}\n"
        f"睡眠: 均{avg_sleep:.1f}h | 压力: {avg_stress:.1f}/10\n"
        f"前半段情绪: {mood_first:.2f} → 后半段: {mood_second:.2f}\n"
        f"高频关键词: {', '.join(f'{k}({v})' for k, v in top_kw)}\n"
        f"日记样本: {sample}..."
    )


def _summarize_narrus(records):
    """v2 schema: 每天一条记录，含 sessions 数组"""
    total_reads = 0
    total_minutes = 0
    total_highlights = 0
    topic_count = {}
    reading_days = 0

    for day_rec in records:
        sessions = day_rec.get("sessions", [])
        if sessions:
            reading_days += 1
        total_reads += len(sessions)
        total_minutes += day_rec.get("daily_reading_min", 0)
        for t in day_rec.get("topics", []):
            topic_count[t] = topic_count.get(t, 0) + 1
        for sess in sessions:
            total_highlights += sess.get("highlights", 0)

    topic_str = ", ".join(f"{k}({v})" for k, v in sorted(topic_count.items(), key=lambda x: -x[1])[:5])

    return (
        f"阅读天数: {reading_days}/{len(records)} | 总阅读次数: {total_reads} | 总时长: {total_minutes}分钟\n"
        f"日均阅读: {total_minutes / max(1, reading_days):.0f}分钟\n"
        f"主题分布: {topic_str}\n"
        f"高亮标注: {total_highlights}处\n"
        f"阅读覆盖率: {reading_days}/{len(records)}天"
    )


# ── Prompt 构建 ──────────────────────────────────────────────────


def build_prompt(config_key, apps, summaries, user_meta):
    """构建发送给 LLM 的 prompt（V3 增强版）"""
    user_desc = f"{user_meta.get('name', '用户')}, {user_meta.get('age', '?')}岁, {user_meta.get('profile', '')}"
    config_label = CONFIGS[config_key]["label"]

    data_section = ""
    for app in apps:
        app_label = APP_NAMES.get(app, app)
        summary = summaries.get(app, "无数据")
        data_section += f"\n【{app_label}】\n{summary}\n"

    if len(apps) == 1:
        task = (
            "请基于以上单维度数据，分析该用户的行为模式，给出你能发现的洞察和建议。\n"
            "注意：你只有单个数据维度，请诚实指出你能看到什么、不能看到什么。"
        )
    elif len(apps) < 4:
        task = (
            "请基于以上多维度数据，进行跨域关联分析。\n"
            "重点发现不同数据维度之间的联动模式。\n"
            "指出哪些洞察是单个维度无法发现、必须通过跨域才能看到的。"
        )
    else:
        # Config H: 全景整合 — V3 增强版，增加危机检测指令
        task = (
            "请基于以上全部四个维度的数据，进行全景跨域分析。\n"
            "核心要求：\n"
            "1. 发现至少3个跨域关联模式（如情绪-饮食-消费的联动）\n"
            "2. 识别隐含的健康/财务/心理风险\n"
            "3. 找到事件前后的行为变化模式（temporal drift）\n"
            "4. 给出至少5条具体的、有操作性的改善建议\n"
            "5. 明确指出哪些发现是单个数据维度永远无法产生的\n"
            "6. 识别可能的危机信号（情绪崩塌、饮食断裂、社交归零、经济断裂等跨域收敛模式）\n"
            "7. 对检测到的危机信号给出严重程度评估（关注/预警/危机三级）\n"
            "请确保你的分析展现了跨域数据整合的独特价值。"
        )

    prompt = (
        f"你是一个个人生活分析助手。以下是用户 {user_desc} 过去30天的数据。\n"
        f"数据配置: {config_label}\n"
        f"{data_section}\n"
        f"{task}"
    )
    return prompt


# ── LLM 调用（统一 llama.cpp /v1/chat/completions）────────────


def call_llm(endpoint, model_name, prompt, max_tokens=4096, temperature=0.7, timeout=600):
    """调用 llama.cpp /v1/chat/completions"""
    url = f"{endpoint}/v1/chat/completions"
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }

    start_time = time.time()
    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    result = response.json()
    elapsed = time.time() - start_time

    content = result["choices"][0]["message"]["content"]
    usage = result.get("usage", {})

    return {
        "content": content,
        "usage": usage,
        "latency_s": round(elapsed, 2),
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
    }


# ── 消融实验 (Experiment A) ─────────────────────────────────────


def run_ablation_for_user(user_id, data_dir, endpoint, model_name, output_dir):
    """对单个用户运行 8 种配置的消融实验，只保存原始输出"""
    print(f"\n{'=' * 60}")
    print(f"  消融实验: {user_id}")
    print(f"  模型: {model_name}")
    print(f"  端点: {endpoint}")
    print(f"{'=' * 60}")

    user_data = load_user_data(data_dir, user_id)
    if not user_data:
        print(f"  无法加载 {user_id} 的数据")
        return None

    user_meta = user_data.get("meta", {"name": user_id})
    results = {}

    for config_key, config in CONFIGS.items():
        apps = config["apps"]
        label = config["label"]
        print(f"\n  [{config_key}] {label}: {', '.join(apps)}")

        summaries = {}
        for app in apps:
            if app in user_data:
                summaries[app] = summarize_app_data(app, user_data[app])
            else:
                summaries[app] = "数据缺失"

        prompt = build_prompt(config_key, apps, summaries, user_meta)

        try:
            llm_result = call_llm(endpoint, model_name, prompt)
            results[config_key] = {
                "label": label,
                "apps": apps,
                "insight": llm_result["content"],
                "usage": llm_result["usage"],
                "latency_s": llm_result["latency_s"],
                "prompt_tokens": llm_result["prompt_tokens"],
                "completion_tokens": llm_result["completion_tokens"],
            }
            print(f"    {llm_result['completion_tokens']} tokens, {llm_result['latency_s']:.1f}s")
        except Exception as e:
            print(f"    错误: {e}")
            results[config_key] = {
                "label": label,
                "apps": apps,
                "insight": "",
                "error": str(e),
            }

    # 保存原始输出
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    safe_model = model_name.replace("/", "_")
    filename = f"{user_id}_{safe_model}_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    filepath = output_path / filename

    output = {
        "experiment": "ablation",
        "user_id": user_id,
        "model_name": model_name,
        "endpoint": endpoint,
        "user_meta": user_meta,
        "configs": results,
        "timestamp": datetime.now().isoformat(),
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"  结果已保存: {filepath}")
    return output


# ── 模型规模实验 (Experiment B) ──────────────────────────────────


def run_scale_for_user(user_id, data_dir, endpoint, model_name, output_dir):
    """对单个用户运行全景配置 (H)，只保存原始输出"""
    print(f"\n{'=' * 60}")
    print(f"  规模实验: {user_id}")
    print(f"  模型: {model_name}")
    print(f"  端点: {endpoint}")
    print(f"{'=' * 60}")

    user_data = load_user_data(data_dir, user_id)
    if not user_data:
        print(f"  无法加载 {user_id} 的数据")
        return None

    user_meta = user_data.get("meta", {"name": user_id})
    config = CONFIGS["H"]
    apps = config["apps"]

    summaries = {}
    for app in apps:
        if app in user_data:
            summaries[app] = summarize_app_data(app, user_data[app])
        else:
            summaries[app] = "数据缺失"

    prompt = build_prompt("H", apps, summaries, user_meta)

    try:
        llm_result = call_llm(endpoint, model_name, prompt)
        result = {
            "label": config["label"],
            "apps": apps,
            "insight": llm_result["content"],
            "usage": llm_result["usage"],
            "latency_s": llm_result["latency_s"],
            "prompt_tokens": llm_result["prompt_tokens"],
            "completion_tokens": llm_result["completion_tokens"],
        }
        print(f"  {llm_result['completion_tokens']} tokens, {llm_result['latency_s']:.1f}s")
    except Exception as e:
        print(f"  错误: {e}")
        result = {
            "label": config["label"],
            "apps": apps,
            "insight": "",
            "error": str(e),
        }

    # 保存原始输出
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    safe_model = model_name.replace("/", "_")
    filename = f"{user_id}_{safe_model}_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    filepath = output_path / filename

    output = {
        "experiment": "scale",
        "user_id": user_id,
        "model_name": model_name,
        "endpoint": endpoint,
        "user_meta": user_meta,
        "result": result,
        "timestamp": datetime.now().isoformat(),
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"  结果已保存: {filepath}")
    return output


# ── 主入口 ───────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Prism v3 消融/规模实验")
    parser.add_argument("--experiment", required=True, choices=["ablation", "scale"],
                        help="实验类型: ablation(跨域消融) 或 scale(模型规模)")
    parser.add_argument("--user", help="指定用户ID (如 user_01 或 lixiang)")
    parser.add_argument("--all_users", action="store_true", help="运行全部14个用户")
    parser.add_argument("--data_dir", default="v3/data/users", help="数据目录")
    parser.add_argument("--endpoint", required=True, help="llama.cpp API端点 (如 http://localhost:9200)")
    parser.add_argument("--model_name", required=True, help="模型名称 (用于记录)")
    parser.add_argument("--output_dir", help="输出目录 (默认 v3/results/{experiment}/raw)")
    args = parser.parse_args()

    if not args.output_dir:
        args.output_dir = f"v3/results/{args.experiment}/raw"

    users = []
    if args.all_users:
        users = ALL_USERS
    elif args.user:
        users = [args.user]
    else:
        print("请指定 --user 或 --all_users")
        return

    # 验证端点
    try:
        r = requests.get(f"{args.endpoint}/v1/models", timeout=10)
        r.raise_for_status()
        print(f"模型端点就绪: {args.endpoint}")
    except Exception as e:
        print(f"警告: 模型端点可能未就绪 ({e})")

    if args.experiment == "ablation":
        for uid in users:
            run_ablation_for_user(uid, args.data_dir, args.endpoint, args.model_name, args.output_dir)
    elif args.experiment == "scale":
        for uid in users:
            run_scale_for_user(uid, args.data_dir, args.endpoint, args.model_name, args.output_dir)

    print(f"\n实验完成，结果在 {args.output_dir}/")


if __name__ == "__main__":
    main()
