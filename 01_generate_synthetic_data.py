#!/usr/bin/env python3
"""
Prism v2 — Step 1: 合成用户数据验证
数据由 Claude Code (Opus 4.6) 直接生成 JSON 文件。
本脚本仅负责验证数据完整性、Schema 一致性，输出统计报告。

10个用户 × 90天 × 4个 App（Dailyn/Mealens/Ururu/Narrus）
"""

import json
import sys
from pathlib import Path

BASE_DIR = Path("data/users")
NUM_DAYS = 90
APPS = ["dailyn", "mealens", "ururu", "narrus"]
USERS = [f"user_{i:02d}" for i in range(1, 11)]

# ── v2 Schema 定义 ──────────────────────────────────────────────

DAILYN_REQUIRED = {"date", "records", "daily_total"}
DAILYN_RECORD_REQUIRED = {"category", "amount", "description", "time"}

MEALENS_REQUIRED = {"date", "meals", "daily_calories", "water_ml"}
MEALENS_MEAL_REQUIRED = {"meal_type", "time", "foods", "estimated_calories", "tags"}

URURU_REQUIRED = {
    "date", "mood_score", "primary_emotion", "stress_level",
    "sleep_hours", "sleep_time", "wake_time", "journal_keywords", "journal_snippet",
}

NARRUS_REQUIRED = {"date", "sessions", "daily_reading_min", "topics"}
NARRUS_SESSION_REQUIRED = {"title", "category", "duration_min", "highlights", "time_range"}


def validate_dailyn(records, user_id):
    errors = []
    for i, r in enumerate(records):
        missing = DAILYN_REQUIRED - set(r.keys())
        if missing:
            errors.append(f"  day {i}: missing {missing}")
        if "records" in r and isinstance(r["records"], list):
            for j, rec in enumerate(r["records"]):
                rec_missing = DAILYN_RECORD_REQUIRED - set(rec.keys())
                if rec_missing:
                    errors.append(f"  day {i} record {j}: missing {rec_missing}")
    return errors


def validate_mealens(records, user_id):
    errors = []
    for i, r in enumerate(records):
        missing = MEALENS_REQUIRED - set(r.keys())
        if missing:
            errors.append(f"  day {i}: missing {missing}")
        if "meals" in r and isinstance(r["meals"], list):
            for j, meal in enumerate(r["meals"]):
                meal_missing = MEALENS_MEAL_REQUIRED - set(meal.keys())
                if meal_missing:
                    errors.append(f"  day {i} meal {j}: missing {meal_missing}")
    return errors


def validate_ururu(records, user_id):
    errors = []
    for i, r in enumerate(records):
        missing = URURU_REQUIRED - set(r.keys())
        if missing:
            errors.append(f"  day {i}: missing {missing}")
        if "mood_score" in r:
            if not (0 <= r["mood_score"] <= 1):
                errors.append(f"  day {i}: mood_score {r['mood_score']} out of [0,1]")
        if "stress_level" in r:
            if not (1 <= r["stress_level"] <= 10):
                errors.append(f"  day {i}: stress_level {r['stress_level']} out of [1,10]")
    return errors


def validate_narrus(records, user_id):
    errors = []
    for i, r in enumerate(records):
        missing = NARRUS_REQUIRED - set(r.keys())
        if missing:
            errors.append(f"  day {i}: missing {missing}")
        if "sessions" in r and isinstance(r["sessions"], list):
            for j, sess in enumerate(r["sessions"]):
                sess_missing = NARRUS_SESSION_REQUIRED - set(sess.keys())
                if sess_missing:
                    errors.append(f"  day {i} session {j}: missing {sess_missing}")
    return errors


VALIDATORS = {
    "dailyn": validate_dailyn,
    "mealens": validate_mealens,
    "ururu": validate_ururu,
    "narrus": validate_narrus,
}


def validate_user(user_id):
    user_dir = BASE_DIR / user_id
    result = {"user_id": user_id, "ok": True, "apps": {}, "errors": []}

    if not user_dir.exists():
        result["ok"] = False
        result["errors"].append(f"目录不存在: {user_dir}")
        return result

    for app in APPS:
        filepath = user_dir / f"{app}.json"
        app_result = {"exists": False, "record_count": 0, "date_count": 0, "schema_errors": []}

        if not filepath.exists():
            result["ok"] = False
            result["errors"].append(f"{app}.json 不存在")
            result["apps"][app] = app_result
            continue

        app_result["exists"] = True

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                records = json.load(f)
        except json.JSONDecodeError as e:
            result["ok"] = False
            result["errors"].append(f"{app}.json JSON解析失败: {e}")
            result["apps"][app] = app_result
            continue

        if not isinstance(records, list):
            result["ok"] = False
            result["errors"].append(f"{app}.json 根元素应为数组")
            result["apps"][app] = app_result
            continue

        app_result["record_count"] = len(records)

        # 检查天数
        dates = sorted(set(r.get("date", "") for r in records))
        app_result["date_count"] = len(dates)

        if len(records) != NUM_DAYS:
            result["errors"].append(f"{app}.json: 期望{NUM_DAYS}条记录, 实际{len(records)}")
            # 不设 ok=False, 因为可能有合理偏差

        if len(dates) != NUM_DAYS:
            result["errors"].append(f"{app}.json: 期望{NUM_DAYS}个不同日期, 实际{len(dates)}")

        # Schema 验证
        validator = VALIDATORS[app]
        schema_errors = validator(records, user_id)
        if schema_errors:
            app_result["schema_errors"] = schema_errors[:5]  # 最多显示5条
            result["errors"].extend([f"{app}: {e}" for e in schema_errors[:3]])

        result["apps"][app] = app_result

    return result


def main():
    print("=" * 65)
    print("Prism v2 — 合成用户数据验证")
    print("=" * 65)

    if not BASE_DIR.exists():
        print(f"\n数据目录不存在: {BASE_DIR.resolve()}")
        print("请先用 Claude Code 生成数据到 data/users/user_XX/")
        sys.exit(1)

    all_ok = True
    total_records = 0

    print(f"\n{'用户':<10} {'Dailyn':>8} {'Mealens':>8} {'Ururu':>8} {'Narrus':>8} {'状态':>6}")
    print("-" * 55)

    for user_id in USERS:
        result = validate_user(user_id)
        if not result["ok"]:
            all_ok = False

        counts = []
        for app in APPS:
            app_info = result["apps"].get(app, {})
            count = app_info.get("record_count", 0)
            total_records += count
            counts.append(f"{count:>8}")

        status = "OK" if result["ok"] else "ERR"
        if result["errors"] and result["ok"]:
            status = "WARN"
        print(f"{user_id:<10} {''.join(counts)} {status:>6}")

        if result["errors"]:
            for err in result["errors"][:3]:
                print(f"  -> {err}")

    print("-" * 55)
    print(f"{'总计':<10} {total_records:>35} 条记录")

    if all_ok:
        print("\n验证通过 — 所有用户数据完整且Schema一致")
    else:
        print("\n验证失败 — 请检查上述错误")
        sys.exit(1)


if __name__ == "__main__":
    main()
