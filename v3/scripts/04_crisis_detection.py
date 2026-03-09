#!/usr/bin/env python3
"""
Prism v3 — 跨域危机检测
基于规则从现有 app 数据字段中检测危机信号，并与 meta.json 中的
ground truth crisis_windows 进行对比评估。

危机信号类型:
  - 财务危机 (dailyn):  daily_total 骤降 >50%，或连续低于事前均值50%
  - 饮食危机 (mealens): 连续3天 <2餐/日，或日均热量 <800kcal 持续3天
  - 情绪危机 (ururu):   mood_score <0.25 连续3天，stress >=9 连续3天，
                        sleep <4h 连续3天
  - 社交/阅读危机 (narrus): 阅读归零5天（对之前有阅读的用户）
  - 数据缺失信号:       任意app连续缺失3天

危机等级:
  - Level 1 (关注): 单域异常
  - Level 2 (预警): 2+域在同一3天窗口内同时异常
  - Level 3 (危机): 3+域在同一5天窗口内同时异常且持续3+天

两种模式:
  --mode detect    → 对全部用户运行检测，输出信号
  --mode evaluate  → 与 ground truth 对比，输出 P/R/F1
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

# ── 常量 ─────────────────────────────────────────────────────────

ALL_USERS = [f"user_{i:02d}" for i in range(1, 11)] + [
    "lixiang", "wangguilan", "zhangxiuying", "chenmo",
]

APPS = ["dailyn", "mealens", "ururu", "narrus"]

CRISIS_LEVELS = {
    1: "关注",
    2: "预警",
    3: "危机",
}

# ── 数据加载 ─────────────────────────────────────────────────────


def load_user_data(data_dir, user_id):
    """加载用户所有 app 数据和 meta"""
    user_dir = Path(data_dir) / user_id
    data = {}
    for app in APPS:
        filepath = user_dir / f"{app}.json"
        if filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                data[app] = json.load(f)
    meta_path = user_dir / "meta.json"
    if meta_path.exists():
        with open(meta_path, "r", encoding="utf-8") as f:
            data["meta"] = json.load(f)
    return data


def get_sorted_dates(records):
    """提取排序后的日期列表"""
    return sorted(set(r.get("date", "") for r in records if r.get("date")))


def build_date_index(records):
    """构建 date -> record 索引"""
    idx = {}
    for r in records:
        d = r.get("date", "")
        if d:
            idx[d] = r
    return idx


# ── 域级别异常检测 ───────────────────────────────────────────────


def detect_dailyn_anomalies(records):
    """
    财务危机信号:
    - daily_total 相比 baseline（前14天均值）下降 >50%
    - 连续日 daily_total < baseline 的 50%
    """
    signals = []
    if not records or len(records) < 7:
        return signals

    date_idx = build_date_index(records)
    dates = get_sorted_dates(records)

    # 计算 baseline: 前14天均值
    baseline_days = min(14, len(dates))
    baseline_totals = []
    for d in dates[:baseline_days]:
        rec = date_idx.get(d, {})
        baseline_totals.append(rec.get("daily_total", 0))
    baseline = sum(baseline_totals) / max(1, len(baseline_totals))

    if baseline <= 0:
        return signals

    threshold = baseline * 0.5
    consecutive_low = 0

    for i, d in enumerate(dates):
        rec = date_idx.get(d, {})
        daily = rec.get("daily_total", 0)

        if daily < threshold:
            consecutive_low += 1
        else:
            consecutive_low = 0

        # 单日骤降
        if i >= baseline_days and daily < threshold:
            signals.append({
                "domain": "dailyn",
                "type": "spending_drop",
                "day_index": i + 1,
                "date": d,
                "detail": f"daily_total={daily:.0f} (baseline={baseline:.0f}, 下降{((baseline - daily) / baseline) * 100:.0f}%)",
                "consecutive": consecutive_low,
            })

    return signals


def detect_mealens_anomalies(records):
    """
    饮食危机信号:
    - 连续3天 <2餐/日
    - 连续3天日均热量 <800kcal
    """
    signals = []
    if not records:
        return signals

    date_idx = build_date_index(records)
    dates = get_sorted_dates(records)

    # 餐次不足检测
    low_meal_streak = 0
    for i, d in enumerate(dates):
        rec = date_idx.get(d, {})
        meal_count = len(rec.get("meals", []))
        if meal_count < 2:
            low_meal_streak += 1
        else:
            low_meal_streak = 0

        if low_meal_streak >= 3:
            signals.append({
                "domain": "mealens",
                "type": "missed_meals",
                "day_index": i + 1,
                "date": d,
                "detail": f"连续{low_meal_streak}天不足2餐 (当日{meal_count}餐)",
                "consecutive": low_meal_streak,
            })

    # 热量不足检测
    low_cal_streak = 0
    for i, d in enumerate(dates):
        rec = date_idx.get(d, {})
        cal = rec.get("daily_calories", 0)
        if cal < 800:
            low_cal_streak += 1
        else:
            low_cal_streak = 0

        if low_cal_streak >= 3:
            signals.append({
                "domain": "mealens",
                "type": "low_calories",
                "day_index": i + 1,
                "date": d,
                "detail": f"连续{low_cal_streak}天热量<800kcal (当日{cal:.0f}kcal)",
                "consecutive": low_cal_streak,
            })

    return signals


def detect_ururu_anomalies(records):
    """
    情绪危机信号:
    - mood_score <0.25 连续3天
    - stress_level >=9 连续3天
    - sleep_hours <4 连续3天
    """
    signals = []
    if not records:
        return signals

    date_idx = build_date_index(records)
    dates = get_sorted_dates(records)

    # 情绪低落
    low_mood_streak = 0
    for i, d in enumerate(dates):
        rec = date_idx.get(d, {})
        mood = rec.get("mood_score", 0.5)
        if mood < 0.25:
            low_mood_streak += 1
        else:
            low_mood_streak = 0

        if low_mood_streak >= 3:
            signals.append({
                "domain": "ururu",
                "type": "low_mood",
                "day_index": i + 1,
                "date": d,
                "detail": f"连续{low_mood_streak}天 mood_score<0.25 (当日{mood:.2f})",
                "consecutive": low_mood_streak,
            })

    # 高压力
    high_stress_streak = 0
    for i, d in enumerate(dates):
        rec = date_idx.get(d, {})
        stress = rec.get("stress_level", 5)
        if stress >= 9:
            high_stress_streak += 1
        else:
            high_stress_streak = 0

        if high_stress_streak >= 3:
            signals.append({
                "domain": "ururu",
                "type": "high_stress",
                "day_index": i + 1,
                "date": d,
                "detail": f"连续{high_stress_streak}天 stress>=9 (当日{stress})",
                "consecutive": high_stress_streak,
            })

    # 睡眠不足
    low_sleep_streak = 0
    for i, d in enumerate(dates):
        rec = date_idx.get(d, {})
        sleep = rec.get("sleep_hours", 7)
        if sleep < 4:
            low_sleep_streak += 1
        else:
            low_sleep_streak = 0

        if low_sleep_streak >= 3:
            signals.append({
                "domain": "ururu",
                "type": "sleep_deprivation",
                "day_index": i + 1,
                "date": d,
                "detail": f"连续{low_sleep_streak}天 sleep<4h (当日{sleep:.1f}h)",
                "consecutive": low_sleep_streak,
            })

    return signals


def detect_narrus_anomalies(records):
    """
    社交/阅读危机信号:
    - 之前有阅读习惯，但连续5天阅读归零
    """
    signals = []
    if not records:
        return signals

    date_idx = build_date_index(records)
    dates = get_sorted_dates(records)

    # 检查是否有阅读习惯（前14天有读过）
    baseline_days = min(14, len(dates))
    has_reading_habit = False
    for d in dates[:baseline_days]:
        rec = date_idx.get(d, {})
        if rec.get("daily_reading_min", 0) > 0 or rec.get("sessions", []):
            has_reading_habit = True
            break

    if not has_reading_habit:
        return signals

    # 检测阅读归零
    zero_reading_streak = 0
    for i, d in enumerate(dates):
        rec = date_idx.get(d, {})
        reading_min = rec.get("daily_reading_min", 0)
        sessions = rec.get("sessions", [])
        if reading_min == 0 and not sessions:
            zero_reading_streak += 1
        else:
            zero_reading_streak = 0

        if zero_reading_streak >= 5:
            signals.append({
                "domain": "narrus",
                "type": "reading_cessation",
                "day_index": i + 1,
                "date": d,
                "detail": f"连续{zero_reading_streak}天阅读归零",
                "consecutive": zero_reading_streak,
            })

    return signals


def detect_data_absence(user_data):
    """
    数据缺失信号: 任意 app 连续缺失3+天
    基于日期连续性检查。
    """
    signals = []

    # 收集所有已知日期（从所有 app 的并集）
    all_dates = set()
    for app in APPS:
        records = user_data.get(app, [])
        if isinstance(records, list):
            for r in records:
                d = r.get("date", "")
                if d:
                    all_dates.add(d)

    if not all_dates:
        return signals

    sorted_all = sorted(all_dates)

    for app in APPS:
        records = user_data.get(app, [])
        if not isinstance(records, list) or not records:
            continue

        app_dates = set(r.get("date", "") for r in records if r.get("date"))
        missing_streak = 0

        for i, d in enumerate(sorted_all):
            if d not in app_dates:
                missing_streak += 1
            else:
                missing_streak = 0

            if missing_streak >= 3:
                signals.append({
                    "domain": app,
                    "type": "data_absence",
                    "day_index": i + 1,
                    "date": d,
                    "detail": f"{app} 连续{missing_streak}天无数据",
                    "consecutive": missing_streak,
                })

    return signals


# ── 跨域危机等级判定 ─────────────────────────────────────────────


def assign_crisis_levels(all_signals):
    """
    根据跨域收敛模式判定危机等级:
    - Level 1 (关注): 单域异常
    - Level 2 (预警): 2+域在同一3天窗口内同时异常
    - Level 3 (危机): 3+域在同一5天窗口内同时异常且持续3+天
    """
    if not all_signals:
        return []

    # 按 day_index 组织信号
    by_day = defaultdict(list)
    for sig in all_signals:
        by_day[sig["day_index"]].append(sig)

    all_days = sorted(by_day.keys())
    if not all_days:
        return []

    crisis_events = []

    # 先检测 Level 3
    for d in all_days:
        # 5天窗口: [d-4, d]
        window_domains = set()
        window_signals = []
        persistent_domains = set()

        for wd in range(d - 4, d + 1):
            for sig in by_day.get(wd, []):
                window_domains.add(sig["domain"])
                window_signals.append(sig)
                if sig.get("consecutive", 0) >= 3:
                    persistent_domains.add(sig["domain"])

        if len(window_domains) >= 3 and len(persistent_domains) >= 3:
            crisis_events.append({
                "level": 3,
                "level_label": CRISIS_LEVELS[3],
                "day_index": d,
                "date": by_day[d][0]["date"] if by_day[d] else "",
                "domains": sorted(window_domains),
                "num_domains": len(window_domains),
                "signals": [s["type"] for s in window_signals],
                "window": f"day {max(1, d - 4)}-{d}",
            })
            continue

        # Level 2: 3天窗口
        window_domains_3 = set()
        window_signals_3 = []
        for wd in range(d - 2, d + 1):
            for sig in by_day.get(wd, []):
                window_domains_3.add(sig["domain"])
                window_signals_3.append(sig)

        if len(window_domains_3) >= 2:
            crisis_events.append({
                "level": 2,
                "level_label": CRISIS_LEVELS[2],
                "day_index": d,
                "date": by_day[d][0]["date"] if by_day[d] else "",
                "domains": sorted(window_domains_3),
                "num_domains": len(window_domains_3),
                "signals": [s["type"] for s in window_signals_3],
                "window": f"day {max(1, d - 2)}-{d}",
            })
            continue

        # Level 1: 单域
        if by_day[d]:
            domains_today = set(s["domain"] for s in by_day[d])
            crisis_events.append({
                "level": 1,
                "level_label": CRISIS_LEVELS[1],
                "day_index": d,
                "date": by_day[d][0]["date"],
                "domains": sorted(domains_today),
                "num_domains": len(domains_today),
                "signals": [s["type"] for s in by_day[d]],
                "window": f"day {d}",
            })

    # 去重: 同一天只保留最高等级
    best_by_day = {}
    for evt in crisis_events:
        d = evt["day_index"]
        if d not in best_by_day or evt["level"] > best_by_day[d]["level"]:
            best_by_day[d] = evt

    return sorted(best_by_day.values(), key=lambda x: x["day_index"])


# ── 检测主逻辑 ───────────────────────────────────────────────────


def detect_user_crises(data_dir, user_id):
    """对单个用户运行全部危机检测"""
    user_data = load_user_data(data_dir, user_id)
    if not user_data:
        return {"user_id": user_id, "signals": [], "crisis_events": [], "error": "无数据"}

    all_signals = []

    # 域级别检测
    if "dailyn" in user_data:
        all_signals.extend(detect_dailyn_anomalies(user_data["dailyn"]))
    if "mealens" in user_data:
        all_signals.extend(detect_mealens_anomalies(user_data["mealens"]))
    if "ururu" in user_data:
        all_signals.extend(detect_ururu_anomalies(user_data["ururu"]))
    if "narrus" in user_data:
        all_signals.extend(detect_narrus_anomalies(user_data["narrus"]))

    # 数据缺失检测
    all_signals.extend(detect_data_absence(user_data))

    # 跨域危机等级判定
    crisis_events = assign_crisis_levels(all_signals)

    # 加载 meta 信息
    meta = user_data.get("meta", {})

    return {
        "user_id": user_id,
        "name": meta.get("name", user_id),
        "drift_class": meta.get("v3_extensions", {}).get("drift_class", "unknown"),
        "signals": all_signals,
        "crisis_events": crisis_events,
        "signal_count": len(all_signals),
        "crisis_count_by_level": {
            lvl: sum(1 for e in crisis_events if e["level"] == lvl)
            for lvl in [1, 2, 3]
        },
    }


# ── 模式 1: 检测 ────────────────────────────────────────────────


def run_detect(data_dir, output_dir):
    """对全部用户运行危机检测"""
    print("=" * 65)
    print("  Prism v3 — 跨域危机检测")
    print("=" * 65)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    all_results = {}
    total_signals = 0
    level_totals = {1: 0, 2: 0, 3: 0}

    print(f"\n{'用户':<14} {'信号数':>6} {'L1关注':>7} {'L2预警':>7} {'L3危机':>7} {'漂移':>10}")
    print("-" * 60)

    for user_id in ALL_USERS:
        result = detect_user_crises(data_dir, user_id)
        all_results[user_id] = result

        n_sig = result["signal_count"]
        total_signals += n_sig
        by_level = result["crisis_count_by_level"]
        for lvl in [1, 2, 3]:
            level_totals[lvl] += by_level.get(lvl, 0)

        dc = result.get("drift_class", "?")
        print(f"{user_id:<14} {n_sig:>6} {by_level.get(1, 0):>7} {by_level.get(2, 0):>7} {by_level.get(3, 0):>7} {dc:>10}")

        # 保存单用户结果
        user_path = output_path / f"{user_id}_signals.json"
        with open(user_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    print("-" * 60)
    print(f"{'总计':<14} {total_signals:>6} {level_totals[1]:>7} {level_totals[2]:>7} {level_totals[3]:>7}")

    # 保存汇总
    summary = {
        "total_users": len(ALL_USERS),
        "total_signals": total_signals,
        "level_totals": {f"L{k}": v for k, v in level_totals.items()},
        "users": {uid: {
            "signal_count": r["signal_count"],
            "crisis_count_by_level": r["crisis_count_by_level"],
            "drift_class": r.get("drift_class"),
        } for uid, r in all_results.items()},
    }
    summary_path = output_path / "detection_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n结果已保存到: {output_path}/")


# ── 模式 2: 评估 (vs Ground Truth) ──────────────────────────────


def run_evaluate(data_dir, output_dir):
    """将检测结果与 ground truth crisis_windows 对比"""
    print("=" * 65)
    print("  Prism v3 — 危机检测评估 (vs Ground Truth)")
    print("=" * 65)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # 按等级统计 TP / FP / FN
    level_stats = {lvl: {"tp": 0, "fp": 0, "fn": 0} for lvl in [1, 2, 3]}
    user_reports = {}

    print(f"\n{'用户':<14} {'GT窗口':>7} {'检出':>6} {'TP':>5} {'FP':>5} {'FN':>5}")
    print("-" * 50)

    for user_id in ALL_USERS:
        user_data = load_user_data(data_dir, user_id)
        meta = user_data.get("meta", {})
        gt_windows = meta.get("v3_extensions", {}).get("crisis_windows", [])

        # 运行检测
        result = detect_user_crises(data_dir, user_id)
        detected = result["crisis_events"]

        # 将 ground truth crisis windows 转为 day_index 集合
        gt_day_sets = []
        for gw in gt_windows:
            dr = gw.get("day_range", [1, 1])
            gt_days = set(range(dr[0], dr[1] + 1))
            gt_day_sets.append({
                "days": gt_days,
                "trigger": gw.get("trigger", ""),
                "severity": gw.get("expected_severity", ""),
                "matched": False,
            })

        # 对每个检测到的危机事件，检查是否落在 ground truth 窗口内
        tp = 0
        fp = 0
        for evt in detected:
            d = evt["day_index"]
            matched = False
            for gt in gt_day_sets:
                if d in gt["days"]:
                    matched = True
                    gt["matched"] = True
                    break
            if matched:
                tp += 1
            else:
                fp += 1

        # 未匹配的 ground truth 窗口算作 FN
        fn = sum(1 for gt in gt_day_sets if not gt["matched"])

        # 按最高检测级别分配到对应等级统计
        max_level = max((e["level"] for e in detected), default=1)
        level_stats[max_level]["tp"] += tp
        level_stats[max_level]["fp"] += fp
        level_stats[max_level]["fn"] += fn

        user_reports[user_id] = {
            "gt_windows": len(gt_windows),
            "detected_events": len(detected),
            "tp": tp, "fp": fp, "fn": fn,
        }

        print(f"{user_id:<14} {len(gt_windows):>7} {len(detected):>6} {tp:>5} {fp:>5} {fn:>5}")

    print("-" * 50)

    # 计算整体和按等级的 P/R/F1
    print(f"\n{'等级':<12} {'Precision':>10} {'Recall':>10} {'F1':>10}")
    print("-" * 45)

    overall_tp = 0
    overall_fp = 0
    overall_fn = 0

    for lvl in [1, 2, 3]:
        stats = level_stats[lvl]
        tp = stats["tp"]
        fp = stats["fp"]
        fn = stats["fn"]
        overall_tp += tp
        overall_fp += fp
        overall_fn += fn

        precision = tp / max(1, tp + fp)
        recall = tp / max(1, tp + fn)
        f1 = 2 * precision * recall / max(1e-10, precision + recall)
        print(f"L{lvl} {CRISIS_LEVELS[lvl]:<8} {precision:>10.3f} {recall:>10.3f} {f1:>10.3f}")

    # 整体
    overall_p = overall_tp / max(1, overall_tp + overall_fp)
    overall_r = overall_tp / max(1, overall_tp + overall_fn)
    overall_f1 = 2 * overall_p * overall_r / max(1e-10, overall_p + overall_r)
    print("-" * 45)
    print(f"{'整体':<12} {overall_p:>10.3f} {overall_r:>10.3f} {overall_f1:>10.3f}")

    # 保存评估报告
    eval_report = {
        "overall": {
            "precision": round(overall_p, 4),
            "recall": round(overall_r, 4),
            "f1": round(overall_f1, 4),
            "tp": overall_tp,
            "fp": overall_fp,
            "fn": overall_fn,
        },
        "by_level": {
            f"L{lvl}": {
                "precision": round(level_stats[lvl]["tp"] / max(1, level_stats[lvl]["tp"] + level_stats[lvl]["fp"]), 4),
                "recall": round(level_stats[lvl]["tp"] / max(1, level_stats[lvl]["tp"] + level_stats[lvl]["fn"]), 4),
                "f1": round(
                    2 * (level_stats[lvl]["tp"] / max(1, level_stats[lvl]["tp"] + level_stats[lvl]["fp"]))
                    * (level_stats[lvl]["tp"] / max(1, level_stats[lvl]["tp"] + level_stats[lvl]["fn"]))
                    / max(1e-10,
                          (level_stats[lvl]["tp"] / max(1, level_stats[lvl]["tp"] + level_stats[lvl]["fp"]))
                          + (level_stats[lvl]["tp"] / max(1, level_stats[lvl]["tp"] + level_stats[lvl]["fn"]))),
                    4
                ),
            }
            for lvl in [1, 2, 3]
        },
        "user_reports": user_reports,
    }

    report_path = output_path / "evaluation_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(eval_report, f, ensure_ascii=False, indent=2)

    print(f"\n评估报告已保存: {report_path}")


# ── 主入口 ───────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Prism v3 跨域危机检测")
    parser.add_argument("--mode", required=True, choices=["detect", "evaluate"],
                        help="模式: detect(运行检测) 或 evaluate(对比评估)")
    parser.add_argument("--data_dir", default="v3/data/users",
                        help="数据目录 (默认 v3/data/users)")
    parser.add_argument("--output_dir", default="v3/results/crisis_detection",
                        help="输出目录 (默认 v3/results/crisis_detection)")
    args = parser.parse_args()

    if args.mode == "detect":
        run_detect(args.data_dir, args.output_dir)
    elif args.mode == "evaluate":
        run_evaluate(args.data_dir, args.output_dir)


if __name__ == "__main__":
    main()
