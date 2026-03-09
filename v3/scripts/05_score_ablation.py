#!/usr/bin/env python3
"""
Prism v3 — 消融结果 LLM-as-Judge 评分

对 Step 2 产出的 112 组 LLM 原始洞察进行自动评分，作为 baseline。
评分维度沿用 V2:
  - relevance    (相关性, 0-25)
  - specificity  (具体性, 0-25)
  - cross_domain (跨域价值, 0-25)
  - actionability(可操作性, 0-25)
  - total        (总分, 0-100)

输出: v3/results/ablation/scored/ 下每用户一个 JSON 文件 + summary.json
"""

import argparse
import json
import re
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path

# ── 常量 ─────────────────────────────────────────────────────────

SCORE_DIMS = ["relevance", "specificity", "cross_domain", "actionability"]

JUDGE_PROMPT_TEMPLATE = """\
你是一个专业的数据分析质量评审专家。请对以下"个人生活洞察分析"进行评分。

## 被评对象背景
用户: {user_desc}
数据配置: {config_label}（使用了 {app_list} 的数据）

## 待评分的洞察内容
{insight}

## 评分维度（每项 0-25 分）

1. **relevance (相关性)**: 洞察是否切中用户的真实处境和核心问题？
   - 0-5: 完全无关或泛泛而谈
   - 6-12: 部分相关但有遗漏
   - 13-19: 较好地把握了用户处境
   - 20-25: 精准切中核心，洞察深刻

2. **specificity (具体性)**: 建议是否具体、有数据支撑、可直接操作？
   - 0-5: "注意健康"级别的空泛建议
   - 6-12: 有一定具体性但缺乏数据引用
   - 13-19: 引用了具体数据，建议较明确
   - 20-25: 引用具体数字和日期，建议可直接执行

3. **cross_domain (跨域价值)**: 洞察是否体现了跨域数据融合的独特价值？
   - 0-5: 单域数据即可得出的结论
   - 6-12: 提到了多域但关联较浅
   - 13-19: 发现了有意义的跨域关联模式
   - 20-25: 揭示了仅凭单域数据不可能发现的深层联动

4. **actionability (可操作性)**: 用户能否基于洞察采取具体行动？
   - 0-5: 无法操作或过于笼统
   - 6-12: 方向正确但缺乏步骤
   - 13-19: 给出了较清晰的行动建议
   - 20-25: 给出了带时间表/优先级的具体行动方案

## 注意
- 单域配置(仅1个数据源)的 cross_domain 分数通常较低(0-8)，这是正常的
- 全景配置(4个数据源)应在 cross_domain 上有显著优势
- 请严格按维度独立评分，不要让某一维度影响其他维度

请只输出 JSON 格式，不要输出其他内容:
{{"relevance": <分数>, "specificity": <分数>, "cross_domain": <分数>, "actionability": <分数>}}
"""


def call_llm(endpoint, model_name, prompt, max_tokens=256, temperature=0.1, timeout=120):
    """调用 llama.cpp /v1/chat/completions"""
    url = f"{endpoint}/v1/chat/completions"
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

    start_time = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    elapsed = time.time() - start_time

    content = result["choices"][0]["message"]["content"]
    return content, elapsed


def parse_scores(text):
    """从 LLM 输出中提取评分 JSON"""
    # 尝试直接解析
    try:
        obj = json.loads(text.strip())
        if all(d in obj for d in SCORE_DIMS):
            return {d: int(obj[d]) for d in SCORE_DIMS}
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # 尝试从 markdown code block 中提取
    m = re.search(r"```(?:json)?\s*(\{[^}]+\})\s*```", text, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group(1))
            if all(d in obj for d in SCORE_DIMS):
                return {d: int(obj[d]) for d in SCORE_DIMS}
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    # 尝试找到任意 JSON 对象
    m = re.search(r"\{[^{}]*\}", text)
    if m:
        try:
            obj = json.loads(m.group())
            if all(d in obj for d in SCORE_DIMS):
                return {d: int(obj[d]) for d in SCORE_DIMS}
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    # 逐维度正则提取
    scores = {}
    for dim in SCORE_DIMS:
        m = re.search(rf'"{dim}"\s*:\s*(\d+)', text)
        if m:
            scores[dim] = int(m.group(1))
    if len(scores) == 4:
        return scores

    return None


def score_one_insight(endpoint, model_name, user_meta, config_key, config_data):
    """对单个配置的洞察进行评分"""
    user_desc = f"{user_meta.get('name', '?')}, {user_meta.get('age', '?')}岁, {user_meta.get('profile', '')}"
    config_label = config_data.get("label", config_key)
    apps = config_data.get("apps", [])
    insight = config_data.get("insight", "")

    if not insight:
        return {"relevance": 0, "specificity": 0, "cross_domain": 0, "actionability": 0, "total": 0, "error": "空洞察"}

    prompt = JUDGE_PROMPT_TEMPLATE.format(
        user_desc=user_desc,
        config_label=config_label,
        app_list="、".join(apps),
        insight=insight[:3000],  # 截断过长的洞察
    )

    max_retries = 2
    for attempt in range(max_retries + 1):
        try:
            response_text, elapsed = call_llm(endpoint, model_name, prompt)
            scores = parse_scores(response_text)
            if scores:
                scores["total"] = sum(scores[d] for d in SCORE_DIMS)
                scores["judge_latency_s"] = round(elapsed, 2)
                return scores
            if attempt < max_retries:
                time.sleep(1)
        except Exception as e:
            if attempt < max_retries:
                time.sleep(2)
            else:
                return {"relevance": 0, "specificity": 0, "cross_domain": 0, "actionability": 0,
                        "total": 0, "error": str(e)}

    return {"relevance": 0, "specificity": 0, "cross_domain": 0, "actionability": 0,
            "total": 0, "error": "评分解析失败"}


def main():
    parser = argparse.ArgumentParser(description="Prism v3 消融结果 LLM-as-Judge 评分")
    parser.add_argument("--raw_dir", default="v3/results/ablation/raw", help="原始结果目录")
    parser.add_argument("--output_dir", default="v3/results/ablation/scored", help="评分输出目录")
    parser.add_argument("--endpoint", required=True, help="llama.cpp API 端点")
    parser.add_argument("--model_name", required=True, help="评分模型名称")
    parser.add_argument("--user", help="只评分指定用户")
    args = parser.parse_args()

    raw_dir = Path(args.raw_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 找到所有原始结果文件
    raw_files = sorted(raw_dir.glob("*.json"))
    if args.user:
        raw_files = [f for f in raw_files if f.name.startswith(args.user + "_")]

    print("=" * 65)
    print("  Prism v3 — LLM-as-Judge 消融评分")
    print(f"  评分模型: {args.model_name}")
    print(f"  原始文件: {len(raw_files)}")
    print("=" * 65)

    all_scored = {}
    total_calls = 0
    total_time = 0

    for raw_file in raw_files:
        with open(raw_file, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        user_id = raw_data["user_id"]
        user_meta = raw_data.get("user_meta", {})
        configs = raw_data.get("configs", {})

        print(f"\n  {user_id} ({user_meta.get('name', '?')})")

        scored_configs = {}
        for config_key in "ABCDEFGH":
            if config_key not in configs:
                continue
            config_data = configs[config_key]
            print(f"    [{config_key}] {config_data.get('label', '')}...", end=" ", flush=True)

            scores = score_one_insight(args.endpoint, args.model_name, user_meta, config_key, config_data)
            total_calls += 1
            total_time += scores.get("judge_latency_s", 0)

            scored_configs[config_key] = {
                "label": config_data.get("label", ""),
                "apps": config_data.get("apps", []),
                "scores": {d: scores.get(d, 0) for d in SCORE_DIMS},
                "total_score": scores.get("total", 0),
                "completion_tokens": config_data.get("completion_tokens", 0),
                "latency_s": config_data.get("latency_s", 0),
            }
            if "error" in scores:
                scored_configs[config_key]["error"] = scores["error"]

            print(f"{scores.get('total', 0):>3} (R{scores.get('relevance',0)} S{scores.get('specificity',0)} X{scores.get('cross_domain',0)} A{scores.get('actionability',0)})")

        # 计算 IIR
        h_score = scored_configs.get("H", {}).get("total_score", 0)
        single_scores = [scored_configs.get(k, {}).get("total_score", 0) for k in "ABCD"]
        avg_single = sum(single_scores) / max(1, len([s for s in single_scores if s > 0]))
        iir = h_score / max(1, avg_single)

        print(f"    IIR = {iir:.2f} (H={h_score} / 单域均={avg_single:.1f})")

        scored_output = {
            "user_id": user_id,
            "model_name": raw_data.get("model_name", ""),
            "user_meta": user_meta,
            "scores": scored_configs,
            "iir": round(iir, 4),
            "scoring_model": args.model_name,
            "scoring_method": "LLM-as-Judge, 4 dimensions x 25 points",
            "timestamp": datetime.now().isoformat(),
        }

        scored_file = output_dir / f"{user_id}_scored.json"
        with open(scored_file, "w", encoding="utf-8") as f:
            json.dump(scored_output, f, ensure_ascii=False, indent=2)

        all_scored[user_id] = {
            "iir": round(iir, 4),
            "h_score": h_score,
            "avg_single": round(avg_single, 1),
            "drift_class": user_meta.get("v3_extensions", {}).get("drift_class", "unknown"),
            "per_config": {k: v.get("total_score", 0) for k, v in scored_configs.items()},
        }

    # 汇总
    print("\n" + "=" * 65)
    print("  汇总")
    print("=" * 65)
    print(f"\n{'用户':<14} {'漂移':>10} {'A':>4} {'B':>4} {'C':>4} {'D':>4} {'E':>4} {'F':>4} {'G':>4} {'H':>4} {'IIR':>6}")
    print("-" * 72)

    iirs = []
    for uid, info in sorted(all_scored.items()):
        pc = info["per_config"]
        print(f"{uid:<14} {info['drift_class']:>10} {pc.get('A',0):>4} {pc.get('B',0):>4} {pc.get('C',0):>4} {pc.get('D',0):>4} {pc.get('E',0):>4} {pc.get('F',0):>4} {pc.get('G',0):>4} {pc.get('H',0):>4} {info['iir']:>6.2f}")
        iirs.append(info["iir"])

    print("-" * 72)
    print(f"{'平均 IIR':<14} {'':>10} {'':>4} {'':>4} {'':>4} {'':>4} {'':>4} {'':>4} {'':>4} {'':>4} {sum(iirs)/max(1,len(iirs)):>6.2f}")

    # 按 drift_class 分组
    drift_groups = {}
    for uid, info in all_scored.items():
        dc = info["drift_class"]
        drift_groups.setdefault(dc, []).append(info["iir"])

    print("\n按漂移类型:")
    for dc in ["normal", "unexpected", "severe"]:
        vals = drift_groups.get(dc, [])
        if vals:
            print(f"  {dc:<12} 平均 IIR = {sum(vals)/len(vals):.2f} (n={len(vals)})")

    summary = {
        "total_users": len(all_scored),
        "total_calls": total_calls,
        "total_judge_time_s": round(total_time, 1),
        "avg_iir": round(sum(iirs) / max(1, len(iirs)), 4),
        "by_drift_class": {
            dc: {"avg_iir": round(sum(vals)/len(vals), 4), "n": len(vals)}
            for dc, vals in drift_groups.items()
        },
        "users": all_scored,
        "scoring_model": args.model_name,
        "timestamp": datetime.now().isoformat(),
    }
    summary_path = output_dir / "scoring_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n总耗时: {total_time:.0f}s ({total_time/60:.1f}min)")
    print(f"汇总已保存: {summary_path}")


if __name__ == "__main__":
    main()
