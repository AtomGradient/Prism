#!/usr/bin/env python3
"""
Prism v3 — 专家评估框架
为消融实验结果生成盲评表单，并分析完成的专家评分。

两种模式:
  --mode prepare  → 生成盲评表单（匿名化配置，供专家打分）
  --mode analyze  → 分析已完成的专家评分（Fleiss' kappa, INR, 相关性）

评分维度 (5维 × 1-5分):
  1. 准确性 (Accuracy)       — 洞察是否准确反映数据中的真实模式
  2. 深度 (Depth)             — 分析是否超越表面统计，触及行为机制
  3. 新颖性 (Novelty)         — 是否发现了非显而易见的、有价值的洞察
  4. 可操作性 (Actionability) — 建议是否具体、可执行、对用户有帮助
  5. 跨域整合 (Integration)   — 是否有效利用多维数据间的关联
"""

import argparse
import json
import random
import string
from collections import defaultdict
from pathlib import Path

# ── 常量 ─────────────────────────────────────────────────────────

ALL_USERS = [f"user_{i:02d}" for i in range(1, 11)] + [
    "lixiang", "wangguilan", "zhangxiuying", "chenmo",
]

CONFIG_KEYS = list("ABCDEFGH")

RATING_DIMENSIONS = {
    "accuracy": {
        "name": "准确性 (Accuracy)",
        "description": "洞察是否准确反映数据中的真实模式",
        "scale": {
            1: "完全不准确，存在明显错误",
            2: "部分准确但有较多误判",
            3: "基本准确，少量偏差",
            4: "准确且可靠",
            5: "高度准确，洞察与数据完美对应",
        },
    },
    "depth": {
        "name": "深度 (Depth)",
        "description": "分析是否超越表面统计，触及行为机制",
        "scale": {
            1: "仅重复原始数据",
            2: "简单统计描述",
            3: "初步分析因果关系",
            4: "深入机制分析",
            5: "揭示深层行为模式和心理机制",
        },
    },
    "novelty": {
        "name": "新颖性 (Novelty)",
        "description": "是否发现了非显而易见的、有价值的洞察",
        "scale": {
            1: "全部为显而易见的观察",
            2: "大部分为常规发现",
            3: "有1-2个有趣发现",
            4: "多个非显而易见的洞察",
            5: "包含令人意外的深层发现",
        },
    },
    "actionability": {
        "name": "可操作性 (Actionability)",
        "description": "建议是否具体、可执行、对用户有帮助",
        "scale": {
            1: "无具体建议或建议不可行",
            2: "建议模糊笼统",
            3: "部分建议可操作",
            4: "多数建议具体可执行",
            5: "建议具体、分步骤、可立即行动",
        },
    },
    "integration": {
        "name": "跨域整合 (Integration)",
        "description": "是否有效利用多维数据间的关联",
        "scale": {
            1: "完全未进行跨域分析",
            2: "简单并列各维度结果",
            3: "初步关联2个维度",
            4: "有效整合多维度数据",
            5: "发现深层跨域模式，展现数据整合独特价值",
        },
    },
}

SINGLE_DOMAIN_CONFIGS = ["A", "B", "C", "D"]

# ── 工具函数 ─────────────────────────────────────────────────────


def generate_blind_id():
    """生成 8 字符随机盲审 ID"""
    return "".join(random.choices(string.ascii_uppercase + string.digits, k=8))


def load_ablation_results(results_dir):
    """加载消融实验结果（scored/ 优先，fallback 到 raw/）"""
    results_dir = Path(results_dir)
    scored_dir = results_dir / "scored"
    raw_dir = results_dir / "raw"

    search_dir = scored_dir if scored_dir.exists() and any(scored_dir.glob("*.json")) else raw_dir
    if not search_dir.exists():
        print(f"结果目录不存在: {search_dir}")
        return {}

    all_results = {}
    for filepath in sorted(search_dir.glob("*.json")):
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        user_id = data.get("user_id", filepath.stem)
        all_results[user_id] = data

    return all_results


# ── 模式 1: 生成盲评表单 ────────────────────────────────────────


def prepare_evaluation_forms(results_dir, output_dir):
    """生成匿名化的专家评估表单（始终从 raw/ 加载，因为需要 insight 原文）"""
    print("=" * 60)
    print("  Prism v3 — 生成专家盲评表单")
    print("=" * 60)

    raw_dir = Path(results_dir) / "raw"
    all_results = {}
    if raw_dir.exists():
        for filepath in sorted(raw_dir.glob("*.json")):
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            user_id = data.get("user_id", filepath.stem)
            all_results[user_id] = data

    if not all_results:
        print("\n未找到消融实验结果，请先运行 02_ablation_experiment.py")
        return

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # 生成盲审 ID 映射
    blind_map = {}   # blind_id -> (user_id, config_key)
    entries = []

    for user_id, data in all_results.items():
        configs = data.get("configs", {})
        for config_key in CONFIG_KEYS:
            if config_key not in configs:
                continue
            config_data = configs[config_key]
            insight = config_data.get("insight", "")
            if not insight:
                continue

            blind_id = generate_blind_id()
            while blind_id in blind_map:
                blind_id = generate_blind_id()
            blind_map[blind_id] = (user_id, config_key)

            entry = {
                "blind_id": blind_id,
                "insight_text": insight,
                "ratings": {
                    dim: {
                        "name": info["name"],
                        "description": info["description"],
                        "scale": {str(k): v for k, v in info["scale"].items()},
                        "score": None,  # 专家填写 1-5
                        "comment": "",  # 专家可选备注
                    }
                    for dim, info in RATING_DIMENSIONS.items()
                },
            }
            entries.append(entry)

    # 打乱顺序，确保盲评
    random.shuffle(entries)

    # 保存评估表单
    forms_path = output_path / "evaluation_forms.json"
    with open(forms_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

    # 保存盲审映射（仅研究者可见）
    mapping_path = output_path / "blind_mapping.json"
    mapping_data = {bid: {"user_id": uid, "config": cfg} for bid, (uid, cfg) in blind_map.items()}
    with open(mapping_path, "w", encoding="utf-8") as f:
        json.dump(mapping_data, f, ensure_ascii=False, indent=2)

    print(f"\n已生成 {len(entries)} 个评估条目")
    print(f"评估表单: {forms_path}")
    print(f"盲审映射: {mapping_path}（请勿提供给评审专家）")
    print(f"\n评分维度:")
    for dim, info in RATING_DIMENSIONS.items():
        print(f"  - {info['name']}: {info['description']}")


# ── 模式 2: 分析专家评分 ────────────────────────────────────────


def analyze_expert_ratings(eval_dir):
    """分析已完成的专家评分"""
    print("=" * 60)
    print("  Prism v3 — 专家评分分析")
    print("=" * 60)

    eval_path = Path(eval_dir)

    # 加载盲审映射
    mapping_path = eval_path / "blind_mapping.json"
    if not mapping_path.exists():
        print(f"\n盲审映射不存在: {mapping_path}")
        return
    with open(mapping_path, "r", encoding="utf-8") as f:
        blind_map = json.load(f)

    # 加载所有评分文件（支持多评审员）
    rating_files = sorted(eval_path.glob("ratings_*.json"))
    if not rating_files:
        # fallback: 从 evaluation_forms.json 读取已填写的评分
        forms_path = eval_path / "evaluation_forms.json"
        if forms_path.exists():
            rating_files = [forms_path]
        else:
            print("\n未找到评分文件（ratings_*.json 或已填写的 evaluation_forms.json）")
            return

    all_rater_scores = []  # list of {blind_id -> {dim -> score}}
    for rf in rating_files:
        with open(rf, "r", encoding="utf-8") as f:
            ratings = json.load(f)
        rater_scores = {}
        for entry in ratings:
            bid = entry.get("blind_id", "")
            scores = {}
            for dim in RATING_DIMENSIONS:
                dim_data = entry.get("ratings", {}).get(dim, {})
                score = dim_data.get("score")
                if score is not None:
                    scores[dim] = int(score)
            if scores:
                rater_scores[bid] = scores
        all_rater_scores.append(rater_scores)

    num_raters = len(all_rater_scores)
    print(f"\n评审员数量: {num_raters}")

    # ── 汇总得分 by config ──
    config_scores = defaultdict(lambda: defaultdict(list))  # config -> dim -> [scores]
    for rater_scores in all_rater_scores:
        for bid, scores in rater_scores.items():
            mapping = blind_map.get(bid, {})
            config = mapping.get("config", "?")
            for dim, score in scores.items():
                config_scores[config][dim].append(score)

    # 打印各配置各维度均分
    print(f"\n{'配置':<8}", end="")
    for dim in RATING_DIMENSIONS:
        print(f"  {dim[:6]:>8}", end="")
    print(f"  {'均分':>8}")
    print("-" * (8 + 10 * (len(RATING_DIMENSIONS) + 1)))

    config_means = {}
    for config_key in CONFIG_KEYS:
        scores_by_dim = config_scores.get(config_key, {})
        print(f"  {config_key:<6}", end="")
        dim_means = []
        for dim in RATING_DIMENSIONS:
            vals = scores_by_dim.get(dim, [])
            mean = sum(vals) / max(1, len(vals)) if vals else 0
            dim_means.append(mean)
            print(f"  {mean:>8.2f}", end="")
        overall = sum(dim_means) / max(1, len(dim_means)) if dim_means else 0
        config_means[config_key] = {"dims": dict(zip(RATING_DIMENSIONS.keys(), dim_means)), "overall": overall}
        print(f"  {overall:>8.2f}")

    # ── Fleiss' kappa ──
    if num_raters >= 2:
        kappa = compute_fleiss_kappa(all_rater_scores, blind_map)
        print(f"\nFleiss' kappa (评审员间一致性): {kappa:.4f}")
        if kappa < 0.2:
            print("  解读: 一致性差")
        elif kappa < 0.4:
            print("  解读: 一般一致性")
        elif kappa < 0.6:
            print("  解读: 中等一致性")
        elif kappa < 0.8:
            print("  解读: 较好一致性")
        else:
            print("  解读: 优秀一致性")
    else:
        print("\n仅1位评审员，跳过 Fleiss' kappa 计算")

    # ── INR (Integrated Novelty Ratio) ──
    h_novelty = config_scores.get("H", {}).get("novelty", [])
    single_novelty = []
    for cfg in SINGLE_DOMAIN_CONFIGS:
        single_novelty.extend(config_scores.get(cfg, {}).get("novelty", []))

    if h_novelty and single_novelty:
        mean_h = sum(h_novelty) / len(h_novelty)
        mean_single = sum(single_novelty) / len(single_novelty)
        inr = mean_h / max(0.01, mean_single)
        print(f"\nINR (Integrated Novelty Ratio): {inr:.3f}")
        print(f"  H均值新颖性: {mean_h:.2f} | 单域均值新颖性: {mean_single:.2f}")
        if inr > 1.0:
            print(f"  全景整合在新颖性上优于单域 {(inr - 1) * 100:.1f}%")
        else:
            print(f"  全景整合未展现新颖性优势")
    else:
        print("\n数据不足，无法计算 INR")

    # ── 专家评分 vs 自动化 IIR 相关性 ──
    # 尝试加载 scored/ 目录中的 IIR
    scored_dir = Path(eval_dir).parent / "ablation" / "scored"
    if scored_dir.exists():
        iir_scores = load_iir_scores(scored_dir)
        if iir_scores:
            compute_expert_iir_correlation(config_scores, iir_scores)

    # ── 保存报告 ──
    report = {
        "num_raters": num_raters,
        "config_means": config_means,
        "inr": inr if (h_novelty and single_novelty) else None,
    }
    report_path = eval_path / "analysis_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n分析报告已保存: {report_path}")


def compute_fleiss_kappa(all_rater_scores, blind_map):
    """计算 Fleiss' kappa"""
    # 收集所有 blind_ids 和所有评分
    all_bids = set()
    for rs in all_rater_scores:
        all_bids.update(rs.keys())
    all_bids = sorted(all_bids)

    if not all_bids:
        return 0.0

    n_raters = len(all_rater_scores)
    categories = list(range(1, 6))  # 评分 1-5
    n_categories = len(categories)

    # 构建评分矩阵: 每个条目×每个维度 -> 一行
    # 为简化，将所有维度的评分展平
    rows = []
    for bid in all_bids:
        for dim in RATING_DIMENSIONS:
            counts = [0] * n_categories
            total = 0
            for rs in all_rater_scores:
                scores = rs.get(bid, {})
                score = scores.get(dim)
                if score is not None and 1 <= score <= 5:
                    counts[score - 1] += 1
                    total += 1
            if total >= 2:  # 至少两个评审员评了这个条目
                rows.append((counts, total))

    if not rows:
        return 0.0

    N = len(rows)
    n = rows[0][1] if rows else n_raters  # 假设各行评审员数量一致

    # P_i: 每行的一致性
    P_i_list = []
    for counts, ni in rows:
        if ni <= 1:
            continue
        sum_sq = sum(c * c for c in counts)
        P_i = (sum_sq - ni) / (ni * (ni - 1)) if ni > 1 else 0
        P_i_list.append(P_i)

    if not P_i_list:
        return 0.0

    P_bar = sum(P_i_list) / len(P_i_list)

    # P_e: 期望一致性
    total_ratings = sum(ni for _, ni in rows)
    category_proportions = [0.0] * n_categories
    for counts, ni in rows:
        for j in range(n_categories):
            category_proportions[j] += counts[j]
    total_all = sum(category_proportions)
    if total_all > 0:
        category_proportions = [p / total_all for p in category_proportions]

    P_e = sum(p * p for p in category_proportions)

    if abs(1 - P_e) < 1e-10:
        return 1.0 if P_bar == 1.0 else 0.0

    kappa = (P_bar - P_e) / (1 - P_e)
    return kappa


def load_iir_scores(scored_dir):
    """从 scored 目录加载自动化 IIR 评分"""
    iir_scores = {}  # (user_id, config) -> iir
    for filepath in scored_dir.glob("*.json"):
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        user_id = data.get("user_id", "")
        configs = data.get("configs", {})
        for cfg_key, cfg_data in configs.items():
            iir = cfg_data.get("iir_score") or cfg_data.get("score")
            if iir is not None:
                iir_scores[(user_id, cfg_key)] = float(iir)
    return iir_scores


def compute_expert_iir_correlation(config_scores, iir_scores):
    """计算专家评分与自动化 IIR 的 Pearson 相关系数"""
    expert_vals = []
    iir_vals = []

    for (user_id, config), iir in iir_scores.items():
        expert_dim_scores = config_scores.get(config, {})
        # 使用专家各维度均分作为总分
        all_scores = []
        for dim in RATING_DIMENSIONS:
            all_scores.extend(expert_dim_scores.get(dim, []))
        if all_scores:
            expert_vals.append(sum(all_scores) / len(all_scores))
            iir_vals.append(iir)

    if len(expert_vals) < 3:
        print("\n数据不足（<3对），跳过专家-IIR相关性计算")
        return

    # Pearson 相关
    n = len(expert_vals)
    mean_e = sum(expert_vals) / n
    mean_i = sum(iir_vals) / n
    cov = sum((e - mean_e) * (i - mean_i) for e, i in zip(expert_vals, iir_vals)) / n
    std_e = (sum((e - mean_e) ** 2 for e in expert_vals) / n) ** 0.5
    std_i = (sum((i - mean_i) ** 2 for i in iir_vals) / n) ** 0.5

    if std_e < 1e-10 or std_i < 1e-10:
        print("\n专家评分或IIR方差为零，无法计算相关性")
        return

    r = cov / (std_e * std_i)
    print(f"\n专家评分 vs 自动化IIR Pearson相关: r = {r:.4f}")
    if abs(r) > 0.7:
        print("  解读: 强相关 — 自动化评分与专家判断高度一致")
    elif abs(r) > 0.4:
        print("  解读: 中等相关")
    else:
        print("  解读: 弱相关 — 自动化评分与专家判断存在差异")


# ── 主入口 ───────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Prism v3 专家评估框架")
    parser.add_argument("--mode", required=True, choices=["prepare", "analyze"],
                        help="模式: prepare(生成盲评表单) 或 analyze(分析评分结果)")
    parser.add_argument("--results_dir", default="v3/results/ablation",
                        help="消融实验结果目录 (默认 v3/results/ablation)")
    parser.add_argument("--eval_dir", default="v3/results/expert_eval",
                        help="专家评估目录 (默认 v3/results/expert_eval)")
    args = parser.parse_args()

    if args.mode == "prepare":
        prepare_evaluation_forms(args.results_dir, args.eval_dir)
    elif args.mode == "analyze":
        analyze_expert_ratings(args.eval_dir)


if __name__ == "__main__":
    main()
