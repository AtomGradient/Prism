#!/usr/bin/env python3
"""
Prism v2 — 设备性能基准测试 (实验C)
统一 llama.cpp /v1/chat/completions API。
测量各模型在不同设备上的 TPS、TTFT、总延迟。
"""

import argparse
import json
import time
import requests
from datetime import datetime
from pathlib import Path


# ── 测试 prompt（3种长度）────────────────────────────────────────

BENCHMARK_PROMPTS = {
    "short": {
        "messages": [
            {"role": "user", "content": "用一句话总结：什么是个性化AI？"}
        ],
        "max_tokens": 100,
        "label": "短文本(~100 tokens)",
    },
    "medium": {
        "messages": [
            {"role": "user", "content": (
                "请分析以下用户行为数据并给出洞察：\n"
                "- 过去一周消费：餐饮480元（外卖占90%），交通120元，购物350元\n"
                "- 饮食模式：跳过早餐4次，深夜进食3次，蔬菜摄入明显不足\n"
                "- 情绪记录：焦虑(4次)，疲惫(3次)，平静(2次)\n"
                "- 睡眠：平均5.8小时，入睡时间普遍在凌晨1点后\n"
                "请从健康、财务、情绪三个维度分析，并给出具体建议。"
            )},
        ],
        "max_tokens": 500,
        "label": "中等文本(~500 tokens)",
    },
    "long": {
        "messages": [
            {"role": "user", "content": (
                "你是一个个人生活分析助手。以下是用户过去30天的跨域数据摘要。\n\n"
                "【财务数据 - Dailyn】\n"
                "月收入: 7000元 | 总支出: 6850元 | 储蓄率: 2.1%\n"
                "支出分布: 餐饮2100(30.7%), 房租2000(29.2%), 交通450(6.6%), "
                "购物1200(17.5%), 娱乐600(8.8%), 社交500(7.3%)\n"
                "异常: 第15天单日消费1200元(聚餐+购物), 月底最后5天日均消费降至35元\n\n"
                "【饮食数据 - Mealens】\n"
                "日均热量: 2200kcal | 早餐跳过率: 47% | 外卖率: 78%\n"
                "蔬菜摄入天数: 12/30 | 深夜进食(22:00后): 8次\n"
                "高频食物: 炸鸡(6次), 麻辣烫(5次), 泡面(4次)\n\n"
                "【情绪数据 - Ururu】\n"
                "情绪均值: 0.52/1.0 | 主要情绪: 焦虑(35%), 疲惫(25%), 平静(20%)\n"
                "睡眠均值: 6.1h | 入睡均值: 01:15 | 压力指数: 6.8/10\n"
                "日记关键词: '论文', '导师', '外卖', '失眠', '焦虑'\n\n"
                "【阅读数据 - Narrus】\n"
                "阅读天数: 22/30 | 日均阅读: 35分钟\n"
                "主题分布: 机器学习(40%), 深度学习(30%), NLP(20%), 其他(10%)\n"
                "高亮数: 45处 | 最频繁阅读时段: 23:00-01:00\n\n"
                "请进行全面的跨域联合分析：\n"
                "1. 识别跨域关联模式（如情绪-饮食-消费的联动）\n"
                "2. 发现隐含的健康风险\n"
                "3. 给出具有操作性的改善建议（至少5条）\n"
                "4. 预测如果不改变，未来3个月可能的变化趋势"
            )},
        ],
        "max_tokens": 1500,
        "label": "长文本(~1500 tokens)",
    },
}


def benchmark_single(endpoint, messages, max_tokens, model_name="", stream=True):
    """单次推理测试，返回性能指标。统一 llama.cpp /v1/ API。"""
    url = f"{endpoint}/v1/chat/completions"
    payload = {
        "model": model_name,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.7,
        "stream": stream,
    }

    start_time = time.time()
    first_token_time = None
    total_tokens = 0
    output_text = ""

    if stream:
        resp = requests.post(url, json=payload, stream=True, timeout=600)
        resp.raise_for_status()

        for line in resp.iter_lines():
            if not line:
                continue
            line = line.decode("utf-8")
            if line.startswith("data: "):
                data_str = line[6:]
                if data_str.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                    delta = chunk.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        if first_token_time is None:
                            first_token_time = time.time()
                        output_text += content
                        total_tokens += 1  # approximate per-chunk
                    # llama.cpp includes usage in the final chunk
                    usage = chunk.get("usage")
                    if usage and usage.get("completion_tokens"):
                        total_tokens = usage["completion_tokens"]
                except json.JSONDecodeError:
                    continue
    else:
        resp = requests.post(url, json=payload, timeout=600)
        resp.raise_for_status()
        result = resp.json()
        first_token_time = time.time()
        output_text = result["choices"][0]["message"]["content"]
        usage = result.get("usage", {})
        total_tokens = usage.get("completion_tokens", len(output_text) // 2)

    end_time = time.time()

    # 更精确的 token 计数回退
    if total_tokens < 5:
        total_tokens = max(total_tokens, len(output_text) // 2)

    total_time = end_time - start_time
    ttft = (first_token_time - start_time) if first_token_time else total_time
    tps = total_tokens / total_time if total_time > 0 else 0

    return {
        "total_tokens": total_tokens,
        "total_time_s": round(total_time, 3),
        "ttft_s": round(ttft, 3),
        "tps": round(tps, 1),
        "output_length": len(output_text),
    }


def run_benchmark(endpoint, model_name, device, n_runs, output_dir):
    """运行完整基准测试"""
    print(f"\n{'=' * 60}")
    print(f"  推理基准测试: {model_name}")
    print(f"  设备: {device}")
    print(f"  端点: {endpoint}")
    print(f"  运行次数: {n_runs}")
    print(f"{'=' * 60}")

    # 验证模型服务
    try:
        r = requests.get(f"{endpoint}/v1/models", timeout=10)
        r.raise_for_status()
        model_info = r.json()
        model_id = model_info.get("data", [{}])[0].get("id", model_name) if model_info.get("data") else model_name
        print(f"  模型ID: {model_id}")
    except Exception as e:
        print(f"  模型列表查询失败 ({e})，继续尝试推理...")
        model_id = model_name

    results = {"benchmarks": {}}

    for size, cfg in BENCHMARK_PROMPTS.items():
        print(f"\n  [{cfg['label']}] 运行 {n_runs} 次...")
        runs = []

        for i in range(n_runs):
            try:
                r = benchmark_single(endpoint, cfg["messages"], cfg["max_tokens"],
                                     model_name=model_name)
                runs.append(r)
                print(f"    Run {i + 1}: {r['tps']:.1f} tps, "
                      f"{r['total_time_s']:.2f}s, "
                      f"TTFT {r['ttft_s']:.3f}s, "
                      f"{r['total_tokens']} tokens")
            except Exception as e:
                print(f"    Run {i + 1}: error - {e}")

        if runs:
            tps_vals = [r["tps"] for r in runs]
            lat_vals = [r["total_time_s"] for r in runs]
            ttft_vals = [r["ttft_s"] for r in runs]

            summary = {
                "tps_mean": round(sum(tps_vals) / len(tps_vals), 1),
                "tps_min": round(min(tps_vals), 1),
                "tps_max": round(max(tps_vals), 1),
                "latency_mean_s": round(sum(lat_vals) / len(lat_vals), 2),
                "ttft_mean_s": round(sum(ttft_vals) / len(ttft_vals), 3),
                "n_runs": len(runs),
            }

            results["benchmarks"][size] = {
                "label": cfg["label"],
                "max_tokens": cfg["max_tokens"],
                "model_id": model_id,
                "runs": runs,
                "summary": summary,
            }

            print(f"    -> 平均: {summary['tps_mean']:.1f} tps, "
                  f"{summary['latency_mean_s']:.2f}s, "
                  f"TTFT {summary['ttft_mean_s']:.3f}s")

    results["device"] = device
    results["model_name"] = model_name
    results["endpoint"] = endpoint
    results["engine"] = "llama.cpp"
    results["timestamp"] = datetime.now().isoformat()

    # 保存结果
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    safe_model = model_name.replace("/", "_").replace(" ", "_")
    safe_device = device.replace(" ", "_")
    filename = f"benchmark_{safe_model}_{safe_device}_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    filepath = output_path / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n  结果已保存: {filepath}")
    return results


def main():
    parser = argparse.ArgumentParser(description="Prism v2 推理性能基准测试")
    parser.add_argument("--device", required=True, help="设备名称 (如 'M2 Ultra 192G')")
    parser.add_argument("--model_endpoint", required=True, help="llama.cpp API端点")
    parser.add_argument("--model_name", required=True, help="模型名称")
    parser.add_argument("--n_runs", type=int, default=5, help="每项测试运行次数")
    parser.add_argument("--output_dir", default="results/benchmark", help="输出目录")
    args = parser.parse_args()

    run_benchmark(
        endpoint=args.model_endpoint,
        model_name=args.model_name,
        device=args.device,
        n_runs=args.n_runs,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
