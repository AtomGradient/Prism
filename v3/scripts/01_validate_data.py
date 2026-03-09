#!/usr/bin/env python3
"""
Prism v3 — Step 1: 合成用户数据验证
扩展 v2 验证器，支持 14 个用户（10 原始 + 4 拼音 ID）、
v3_extensions schema 验证、crisis_window 一致性检查。

14个用户 × 90天 × 4个 App（Dailyn/Mealens/Ururu/Narrus）
"""

import json
import sys
from pathlib import Path

BASE_DIR = Path("v3/data/users")
NUM_DAYS = 90
APPS = ["dailyn", "mealens", "ururu", "narrus"]
V2_USERS = [f"user_{i:02d}" for i in range(1, 11)]
V3_NEW_USERS = ["lixiang", "wangguilan", "zhangxiuying", "chenmo"]
ALL_USERS = V2_USERS + V3_NEW_USERS

VALID_DRIFT_CLASSES = {"normal", "unexpected", "severe"}

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


# ── v3_extensions 验证 ──────────────────────────────────────────


def validate_v3_extensions(meta, user_id):
    """验证 meta.json 中的 v3_extensions 字段"""
    errors = []
    warnings = []

    if "v3_extensions" not in meta:
        errors.append("meta.json 缺少 v3_extensions")
        return errors, warnings

    ext = meta["v3_extensions"]

    # drift_class
    dc = ext.get("drift_class")
    if dc is None:
        errors.append("v3_extensions 缺少 drift_class")
    elif dc not in VALID_DRIFT_CLASSES:
        errors.append(f"drift_class '{dc}' 无效，应为 {VALID_DRIFT_CLASSES}")

    # crisis_windows
    cw = ext.get("crisis_windows")
    if cw is None:
        errors.append("v3_extensions 缺少 crisis_windows")
    elif not isinstance(cw, list):
        errors.append("crisis_windows 应为数组")
    else:
        for idx, window in enumerate(cw):
            # day_range 检查
            dr = window.get("day_range")
            if dr is None:
                errors.append(f"crisis_windows[{idx}] 缺少 day_range")
            elif not isinstance(dr, list) or len(dr) != 2:
                errors.append(f"crisis_windows[{idx}] day_range 应为长度2的数组")
            else:
                if not all(isinstance(d, int) for d in dr):
                    errors.append(f"crisis_windows[{idx}] day_range 元素应为整数")
                elif not (1 <= dr[0] <= 90 and 1 <= dr[1] <= 90):
                    errors.append(f"crisis_windows[{idx}] day_range {dr} 超出 [1,90]")
                elif dr[0] > dr[1]:
                    errors.append(f"crisis_windows[{idx}] day_range 起始 > 结束")

            # trigger
            trigger = window.get("trigger")
            if trigger is None or not isinstance(trigger, str):
                errors.append(f"crisis_windows[{idx}] 缺少 trigger 或非字符串")

            # expected_severity
            es = window.get("expected_severity")
            if es is None or not isinstance(es, str):
                errors.append(f"crisis_windows[{idx}] 缺少 expected_severity 或非字符串")

        # crisis window 一致性检查：不超出 data_range
        data_range = meta.get("data_range", {})
        if data_range.get("start") and data_range.get("end"):
            from datetime import datetime
            try:
                start_date = datetime.strptime(data_range["start"], "%Y-%m-%d")
                end_date = datetime.strptime(data_range["end"], "%Y-%m-%d")
                total_days = (end_date - start_date).days + 1
                for idx, window in enumerate(cw):
                    dr = window.get("day_range", [])
                    if isinstance(dr, list) and len(dr) == 2:
                        if dr[1] > total_days:
                            warnings.append(
                                f"crisis_windows[{idx}] day_range 结束日 {dr[1]} "
                                f"超出 data_range 总天数 {total_days}"
                            )
            except (ValueError, TypeError):
                warnings.append("data_range 日期格式解析失败，跳过一致性检查")

    # social_context
    sc = ext.get("social_context")
    if sc is None:
        errors.append("v3_extensions 缺少 social_context")
    elif not isinstance(sc, dict):
        errors.append("social_context 应为对象")
    else:
        for field in ["living_situation", "support_network", "key_relationships"]:
            if field not in sc:
                errors.append(f"social_context 缺少 {field}")

    # ethical_notes
    en = ext.get("ethical_notes")
    if en is None:
        errors.append("v3_extensions 缺少 ethical_notes")
    elif not isinstance(en, str) or len(en.strip()) == 0:
        errors.append("ethical_notes 应为非空字符串")

    return errors, warnings


# ── 用户验证 ────────────────────────────────────────────────────


def validate_user(user_id):
    """验证单个用户的全部数据"""
    user_dir = BASE_DIR / user_id
    is_v3_new = user_id in V3_NEW_USERS
    result = {
        "user_id": user_id,
        "ok": True,
        "apps": {},
        "errors": [],
        "warnings": [],
        "is_v3_new": is_v3_new,
        "drift_class": None,
    }

    if not user_dir.exists():
        result["ok"] = False
        result["errors"].append(f"目录不存在: {user_dir}")
        return result

    # ── meta.json 验证 ──
    meta_path = user_dir / "meta.json"
    if not meta_path.exists():
        result["ok"] = False
        result["errors"].append("meta.json 不存在")
        return result

    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
    except json.JSONDecodeError as e:
        result["ok"] = False
        result["errors"].append(f"meta.json JSON解析失败: {e}")
        return result

    # v3_extensions 验证
    ext_errors, ext_warnings = validate_v3_extensions(meta, user_id)
    if ext_errors:
        result["ok"] = False
        result["errors"].extend(ext_errors)
    result["warnings"].extend(ext_warnings)

    # 记录 drift_class
    ext = meta.get("v3_extensions", {})
    result["drift_class"] = ext.get("drift_class")

    # ── App 数据验证 ──
    for app in APPS:
        filepath = user_dir / f"{app}.json"
        app_result = {"exists": False, "record_count": 0, "date_count": 0, "schema_errors": []}

        if not filepath.exists():
            if is_v3_new:
                # V3 新用户可能缺少 app 数据，仅警告
                result["warnings"].append(f"{app}.json 不存在（V3新用户，可接受）")
            else:
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
            result["warnings"].append(f"{app}.json: 期望{NUM_DAYS}条记录, 实际{len(records)}")

        if len(dates) != NUM_DAYS:
            result["warnings"].append(f"{app}.json: 期望{NUM_DAYS}个不同日期, 实际{len(dates)}")

        # Schema 验证
        validator = VALIDATORS[app]
        schema_errors = validator(records, user_id)
        if schema_errors:
            app_result["schema_errors"] = schema_errors[:5]
            result["errors"].extend([f"{app}: {e}" for e in schema_errors[:3]])

        result["apps"][app] = app_result

    return result


def main():
    print("=" * 70)
    print("Prism v3 — 合成用户数据验证")
    print(f"  V2用户: {len(V2_USERS)}  |  V3新用户: {len(V3_NEW_USERS)}  |  共: {len(ALL_USERS)}")
    print("=" * 70)

    if not BASE_DIR.exists():
        print(f"\n数据目录不存在: {BASE_DIR.resolve()}")
        print("请先生成数据到 v3/data/users/")
        sys.exit(1)

    all_ok = True
    total_records = 0
    drift_counts = {"normal": 0, "unexpected": 0, "severe": 0}

    print(f"\n{'用户':<14} {'Dailyn':>8} {'Mealens':>8} {'Ururu':>8} {'Narrus':>8} {'漂移':>10} {'状态':>6}")
    print("-" * 70)

    for user_id in ALL_USERS:
        result = validate_user(user_id)
        if not result["ok"]:
            all_ok = False

        counts = []
        for app in APPS:
            app_info = result["apps"].get(app, {})
            count = app_info.get("record_count", 0)
            total_records += count
            counts.append(f"{count:>8}")

        dc = result["drift_class"] or "?"
        if dc in drift_counts:
            drift_counts[dc] += 1

        status = "OK" if result["ok"] else "ERR"
        if not result["ok"]:
            status = "ERR"
        elif result["warnings"]:
            status = "WARN"
        print(f"{user_id:<14} {''.join(counts)} {dc:>10} {status:>6}")

        if result["errors"]:
            for err in result["errors"][:3]:
                print(f"  [E] {err}")
        if result["warnings"]:
            for warn in result["warnings"][:3]:
                print(f"  [W] {warn}")

    print("-" * 70)
    print(f"{'总计':<14} {total_records:>35} 条记录")

    # ── 漂移分布摘要 ──
    print(f"\n漂移分布:")
    print(f"  normal:     {drift_counts['normal']}")
    print(f"  unexpected: {drift_counts['unexpected']}")
    print(f"  severe:     {drift_counts['severe']}")

    if all_ok:
        print("\n验证通过 — 所有用户数据完整且Schema一致")
    else:
        print("\n验证失败 — 请检查上述错误")
        sys.exit(1)


if __name__ == "__main__":
    main()
