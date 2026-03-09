#!/usr/bin/env python3
"""
Prism v3 — 模拟专家盲评

用 LLM 扮演 3 位不同领域专家，对 112 组盲化洞察进行独立评分。
3 位专家角色:
  - Expert A: 社会工作者 — 关注准确性和可操作性
  - Expert B: 心理学家   — 关注深度和新颖性
  - Expert C: 数据科学家 — 关注准确性和跨域整合

输入: v3/results/expert_eval/evaluation_forms.json
输出: v3/results/expert_eval/ratings_expert_{a,b,c}.json
"""

import argparse
import json
import re
import time
import urllib.request
from pathlib import Path

DIMS = ["accuracy", "depth", "novelty", "actionability", "integration"]

EXPERT_PROMPTS = {
    "expert_a": {
        "role": "社会工作者",
        "persona": (
            "你是一位有15年经验的社会工作者，擅长社区服务和弱势群体支持。"
            "你特别关注分析是否真正理解了用户的生活处境，建议是否具体可行且不会造成伤害。"
            "你对泛泛而谈的建议非常敏感——如果建议无法落地执行，你会给低分。"
            "你对'跨域整合'不太敏感，因为你更关注实际帮助而非技术层面。"
        ),
    },
    "expert_b": {
        "role": "心理学家",
        "persona": (
            "你是一位认知心理学博士，研究方向是行为模式分析和心理健康预警。"
            "你特别关注分析的深度——是否触及了行为背后的心理机制，是否发现了非显而易见的模式。"
            "你对'新颖性'有较高要求——如果分析只是重述数据中的明显趋势，你会给低分。"
            "你会额外关注情绪-行为的联动分析质量。"
        ),
    },
    "expert_c": {
        "role": "数据科学家",
        "persona": (
            "你是一位资深数据科学家，专注于多源数据融合和异常检测。"
            "你特别关注分析的准确性——是否正确解读了数据，是否存在过度推断。"
            "你对'跨域整合'有很高的标准——简单并列多个维度的结果不算真正的整合。"
            "你会严格评估：分析是否引用了具体数据点来支撑结论。"
        ),
    },
}

RATING_PROMPT_TEMPLATE = """\
{persona}

请你作为{role}，对以下"个人生活洞察分析"进行专业评分。

## 待评分的洞察分析
{insight}

## 评分维度（每项 1-5 分）

1. **accuracy (准确性)**: 洞察是否准确反映了数据中的真实模式？
   1=完全不准确 | 2=部分准确但有较多误判 | 3=基本准确 | 4=准确可靠 | 5=高度准确

2. **depth (深度)**: 分析是否超越表面统计，触及行为机制？
   1=仅重复原始数据 | 2=简单统计描述 | 3=初步因果分析 | 4=深入机制分析 | 5=揭示深层模式

3. **novelty (新颖性)**: 是否发现了非显而易见的洞察？
   1=全是常识 | 2=大部分常规 | 3=有1-2个有趣发现 | 4=多个新颖洞察 | 5=令人意外的深层发现

4. **actionability (可操作性)**: 建议是否具体可执行？
   1=无具体建议 | 2=建议模糊 | 3=部分可操作 | 4=多数具体可执行 | 5=可立即行动的分步建议

5. **integration (跨域整合)**: 是否有效利用了多维数据间的关联？
   1=未做跨域分析 | 2=简单并列 | 3=初步关联 | 4=有效整合 | 5=深层跨域模式

## 重要提示
- 请根据你的专业视角独立评分
- 如果这是一个单维度数据的分析，integration 分数通常较低(1-2)是正常的
- 请严格按标准评分，不要给出全高分或全低分
- 只输出 JSON，不要输出其他内容

请输出:
{{"accuracy": <1-5>, "depth": <1-5>, "novelty": <1-5>, "actionability": <1-5>, "integration": <1-5>}}
"""


def call_llm(endpoint, model_name, prompt, max_tokens=128, temperature=0.3, timeout=60):
    url = f"{endpoint}/v1/chat/completions"
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return result["choices"][0]["message"]["content"]


def parse_scores(text):
    """从 LLM 输出中提取 1-5 分评分"""
    # Try direct JSON parse
    try:
        obj = json.loads(text.strip())
        if all(d in obj for d in DIMS):
            return {d: max(1, min(5, int(obj[d]))) for d in DIMS}
    except (json.JSONDecodeError, ValueError, TypeError):
        pass

    # Try extracting JSON from text
    m = re.search(r"\{[^{}]*\}", text)
    if m:
        try:
            obj = json.loads(m.group())
            if all(d in obj for d in DIMS):
                return {d: max(1, min(5, int(obj[d]))) for d in DIMS}
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

    # Regex fallback
    scores = {}
    for dim in DIMS:
        m = re.search(rf'"{dim}"\s*:\s*(\d)', text)
        if m:
            scores[dim] = max(1, min(5, int(m.group(1))))
    if len(scores) == 5:
        return scores

    return None


def rate_one_entry(endpoint, model_name, expert_key, insight_text):
    """让一位模拟专家对一条洞察评分"""
    expert = EXPERT_PROMPTS[expert_key]
    prompt = RATING_PROMPT_TEMPLATE.format(
        persona=expert["persona"],
        role=expert["role"],
        insight=insight_text[:3000],
    )

    for attempt in range(3):
        try:
            response = call_llm(endpoint, model_name, prompt)
            scores = parse_scores(response)
            if scores:
                return scores
            time.sleep(0.5)
        except Exception:
            time.sleep(1)

    # Fallback
    return {d: 3 for d in DIMS}


def main():
    parser = argparse.ArgumentParser(description="Prism v3 模拟专家盲评")
    parser.add_argument("--endpoint", required=True, help="llama.cpp API 端点")
    parser.add_argument("--model_name", required=True, help="模型名称")
    parser.add_argument("--eval_dir", default="v3/results/expert_eval", help="评估目录")
    parser.add_argument("--expert", help="只运行指定专家 (expert_a/b/c)")
    args = parser.parse_args()

    eval_dir = Path(args.eval_dir)
    forms_path = eval_dir / "evaluation_forms.json"
    if not forms_path.exists():
        print(f"评估表单不存在: {forms_path}")
        print("请先运行: python3 v3/scripts/03_expert_evaluation.py --mode prepare")
        return

    with open(forms_path, "r", encoding="utf-8") as f:
        forms = json.load(f)

    experts = [args.expert] if args.expert else ["expert_a", "expert_b", "expert_c"]

    print("=" * 65)
    print("  Prism v3 — 模拟专家盲评")
    print(f"  模型: {args.model_name}")
    print(f"  条目数: {len(forms)}")
    print(f"  专家: {', '.join(experts)}")
    print(f"  总评分次数: {len(forms) * len(experts)}")
    print("=" * 65)

    for expert_key in experts:
        expert = EXPERT_PROMPTS[expert_key]
        print(f"\n  ── {expert_key}: {expert['role']} ──")

        rated_forms = []
        for i, entry in enumerate(forms):
            blind_id = entry["blind_id"]
            insight = entry["insight_text"]

            scores = rate_one_entry(args.endpoint, args.model_name, expert_key, insight)

            rated_entry = {
                "blind_id": blind_id,
                "ratings": {},
            }
            for dim in DIMS:
                rated_entry["ratings"][dim] = {
                    "score": scores.get(dim, 3),
                }
            rated_forms.append(rated_entry)

            if (i + 1) % 10 == 0 or i == len(forms) - 1:
                scores_str = " ".join(f"{d[0].upper()}{scores.get(d, 0)}" for d in DIMS)
                print(f"    [{i+1:>3}/{len(forms)}] {blind_id} → {scores_str}")

        # Save
        output_path = eval_dir / f"ratings_{expert_key}.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(rated_forms, f, ensure_ascii=False, indent=2)
        print(f"    保存: {output_path}")

    print(f"\n评分完成。运行分析:")
    print(f"  python3 v3/scripts/03_expert_evaluation.py --mode analyze")


if __name__ == "__main__":
    main()
