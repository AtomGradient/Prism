#!/usr/bin/env python3
"""
Prism v2 — 局域网联邦协议 (实验D)
统一 llama.cpp /v1/chat/completions API。

两种角色:
  - data_node: 在设备上暴露 app 数据摘要接口（模拟手机/平板）
  - panorama_node: 全景节点，联邦查询各数据节点，送入 LLM 生成洞察
"""

import argparse
import json
import time
import requests
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify


# ── 数据节点 ─────────────────────────────────────────────────────


def create_data_node_app(node_name, apps, data_dir, user_id):
    """创建数据节点 Flask 应用（v2 schema）"""
    app = Flask(__name__)
    app.config["node_name"] = node_name
    app.config["apps"] = apps
    app.config["data_dir"] = data_dir
    app.config["user_id"] = user_id

    def load_app_data(app_name, uid):
        filepath = Path(data_dir) / uid / f"{app_name}.json"
        if filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def summarize_data(app_name, records, days=14):
        """将原始数据压缩为摘要（隐私保护：不传输原始数据）— v2 schema"""
        if not records:
            return {"summary": "无数据", "record_count": 0, "raw_bytes": 0}

        raw_bytes = len(json.dumps(records, ensure_ascii=False).encode("utf-8"))

        # 按时间过滤最近N天
        dates = sorted(set(r.get("date", "") for r in records))
        if len(dates) > days:
            cutoff = dates[-days]
            records = [r for r in records if r.get("date", "") >= cutoff]

        summary = {}

        if app_name == "dailyn":
            total_expense = 0
            monthly_income = 0
            cat_totals = {}
            daily_totals = {}
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
                daily_totals[date] = day_total
            summary = {
                "total_income": monthly_income,
                "total_expense": round(total_expense, 2),
                "category_breakdown": cat_totals,
                "daily_expense_trend": daily_totals,
                "expense_count": sum(len(r.get("records", [])) for r in records),
                "avg_daily_expense": round(total_expense / max(1, len(daily_totals)), 2),
            }

        elif app_name == "mealens":
            total_meals = 0
            healthy_count = 0
            skip_count = 0
            total_cal = 0
            meal_dist = {}
            food_count = {}
            for day_rec in records:
                total_cal += day_rec.get("daily_calories", 0)
                has_breakfast = False
                for meal in day_rec.get("meals", []):
                    total_meals += 1
                    mt = meal.get("meal_type", "other")
                    meal_dist[mt] = meal_dist.get(mt, 0) + 1
                    if mt == "breakfast":
                        has_breakfast = True
                    tags = meal.get("tags", [])
                    if "健康" in tags or "自制" in tags:
                        healthy_count += 1
                    for food in meal.get("foods", []):
                        food_count[food] = food_count.get(food, 0) + 1
                if not has_breakfast:
                    skip_count += 1
            summary = {
                "total_meals": total_meals,
                "healthy_count": healthy_count,
                "skip_breakfast_days": skip_count,
                "avg_calories": round(total_cal / max(1, len(records)), 0),
                "meal_distribution": meal_dist,
                "top_foods": dict(sorted(food_count.items(), key=lambda x: -x[1])[:5]),
            }

        elif app_name == "ururu":
            moods = [r.get("mood_score", 0.5) for r in records]
            emotions = {}
            for r in records:
                e = r.get("primary_emotion", "")
                emotions[e] = emotions.get(e, 0) + 1
            summary = {
                "avg_mood": round(sum(moods) / max(1, len(moods)), 2),
                "mood_trend": {r["date"]: r.get("mood_score", 0.5) for r in records},
                "emotion_distribution": emotions,
                "avg_sleep_hours": round(sum(r.get("sleep_hours", 7) for r in records) / max(1, len(records)), 1),
                "avg_stress": round(sum(r.get("stress_level", 5) for r in records) / max(1, len(records)), 1),
                "journal_excerpts": [r.get("journal_snippet", "")[:100] for r in records[:3] if r.get("journal_snippet")],
            }

        elif app_name == "narrus":
            topic_count = {}
            total_reads = 0
            total_minutes = 0
            reading_days = 0
            total_highlights = 0
            recent_titles = []
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
                    recent_titles.append(sess.get("title", ""))
            summary = {
                "total_reads": total_reads,
                "total_minutes": total_minutes,
                "reading_days": reading_days,
                "topic_distribution": topic_count,
                "total_highlights": total_highlights,
                "recent_titles": list(set(recent_titles[-10:])),
            }

        transmitted = json.dumps(summary, ensure_ascii=False).encode("utf-8")
        return {
            "summary": summary,
            "record_count": len(records),
            "raw_bytes": raw_bytes,
            "transmitted_bytes": len(transmitted),
            "compression_ratio": round(raw_bytes / max(1, len(transmitted)), 1),
        }

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({
            "status": "ok",
            "node_name": node_name,
            "apps": apps,
            "user_id": user_id,
            "timestamp": datetime.now().isoformat(),
        })

    @app.route("/query", methods=["POST"])
    def query():
        """联邦查询接口：返回数据摘要（不是原始数据）"""
        req = request.get_json() or {}
        query_apps = req.get("apps", apps)
        query_user = req.get("user_id", user_id)
        days = req.get("days", 14)

        results = {}
        total_raw = 0
        total_transmitted = 0

        for a in query_apps:
            if a in apps:
                records = load_app_data(a, query_user)
                result = summarize_data(a, records, days)
                results[a] = result
                total_raw += result["raw_bytes"]
                total_transmitted += result["transmitted_bytes"]

        return jsonify({
            "node_name": node_name,
            "user_id": query_user,
            "apps_queried": list(results.keys()),
            "data": {k: v["summary"] for k, v in results.items()},
            "privacy_audit": {
                "raw_bytes": total_raw,
                "transmitted_bytes": total_transmitted,
                "compression_ratio": round(total_raw / max(1, total_transmitted), 1),
                "raw_data_transmitted": False,
            },
        })

    return app


# ── 全景节点 ─────────────────────────────────────────────────────


def create_panorama_node_app(llm_endpoint):
    """创建全景节点 Flask 应用。统一 llama.cpp /v1/ API。"""
    app = Flask(__name__)
    app.config["llm_endpoint"] = llm_endpoint
    registered_nodes = {}

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({
            "status": "ok",
            "role": "panorama_node",
            "registered_nodes": len(registered_nodes),
            "nodes": {nid: {"name": n["name"], "apps": n["apps"]} for nid, n in registered_nodes.items()},
            "llm_endpoint": llm_endpoint,
            "timestamp": datetime.now().isoformat(),
        })

    @app.route("/register_node", methods=["POST"])
    def register_node():
        req = request.get_json()
        node_id = req.get("node_id")
        if not node_id:
            return jsonify({"error": "node_id required"}), 400

        registered_nodes[node_id] = {
            "name": req.get("name", node_id),
            "endpoint": req.get("endpoint"),
            "apps": req.get("apps", []),
            "device": req.get("device", "unknown"),
            "simulates": req.get("simulates", "unknown"),
            "registered_at": datetime.now().isoformat(),
        }
        return jsonify({"status": "registered", "node_id": node_id, "total_nodes": len(registered_nodes)})

    @app.route("/panorama", methods=["POST"])
    def panorama():
        """执行全景联邦查询"""
        req = request.get_json() or {}
        days = req.get("days", 14)
        user_id = req.get("user_id", "user_01")

        start_time = time.time()
        federated_data = {}
        privacy_audit = {
            "total_raw_data_bytes": 0,
            "total_transmitted_bytes": 0,
            "raw_data_left_devices": False,
            "nodes_queried": [],
        }

        # 联邦查询各数据节点
        federation_start = time.time()
        for nid, node in registered_nodes.items():
            try:
                resp = requests.post(
                    f"{node['endpoint']}/query",
                    json={"apps": node["apps"], "user_id": user_id, "days": days},
                    timeout=30,
                )
                resp.raise_for_status()
                result = resp.json()

                for app_name, app_data in result.get("data", {}).items():
                    federated_data[app_name] = app_data

                audit = result.get("privacy_audit", {})
                privacy_audit["total_raw_data_bytes"] += audit.get("raw_bytes", 0)
                privacy_audit["total_transmitted_bytes"] += audit.get("transmitted_bytes", 0)
                privacy_audit["nodes_queried"].append({
                    "node_id": nid,
                    "name": node["name"],
                    "apps": list(result.get("data", {}).keys()),
                    "device": node["device"],
                })

            except Exception as e:
                print(f"查询节点 {nid} 失败: {e}")

        federation_time = time.time() - federation_start

        if privacy_audit["total_transmitted_bytes"] > 0:
            privacy_audit["data_compression_ratio"] = round(
                privacy_audit["total_raw_data_bytes"] / privacy_audit["total_transmitted_bytes"], 1
            )
        else:
            privacy_audit["data_compression_ratio"] = 0

        # 构建 LLM prompt
        data_text = ""
        for app_name, app_data in federated_data.items():
            data_text += f"\n【{app_name}数据摘要】\n{json.dumps(app_data, ensure_ascii=False, indent=2)}\n"

        prompt = (
            f"你是一个运行在用户家庭服务器上的个人AI助手。\n"
            f"以下是从用户各设备联邦查询收集的数据摘要（过去{days}天）。\n"
            f"重要：你看到的是压缩后的摘要，不是原始数据。原始数据从未离开用户设备。\n"
            f"\n用户ID: {user_id}\n"
            f"{data_text}\n"
            f"请进行全景跨域分析：\n"
            f"1. 识别跨数据域的关联模式\n"
            f"2. 发现潜在的健康/财务/心理风险\n"
            f"3. 给出个性化的、具体可操作的建议\n"
            f"4. 说明哪些洞察是单个app永远无法产生的"
        )

        # 调用 LLM（统一 llama.cpp /v1/）
        llm_start = time.time()
        insight = ""
        try:
            resp = requests.post(
                f"{llm_endpoint}/v1/chat/completions",
                json={
                    "model": "local-model",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 2000,
                    "temperature": 0.7,
                },
                timeout=300,
            )
            resp.raise_for_status()
            result = resp.json()
            insight = result["choices"][0]["message"]["content"]
        except Exception as e:
            insight = f"LLM调用失败: {e}"

        llm_time = time.time() - llm_start
        total_time = time.time() - start_time

        return jsonify({
            "user_id": user_id,
            "days": days,
            "federated_apps": list(federated_data.keys()),
            "insight": insight,
            "performance": {
                "federation_time_ms": round(federation_time * 1000, 1),
                "llm_inference_time_s": round(llm_time, 2),
                "total_time_s": round(total_time, 2),
            },
            "privacy_audit": privacy_audit,
            "timestamp": datetime.now().isoformat(),
        })

    return app


# ── 主入口 ───────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="Prism v2 局域网联邦协议")
    parser.add_argument("--role", required=True, choices=["data_node", "panorama_node"])
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--host", default="0.0.0.0")

    # data_node 参数
    parser.add_argument("--node_name", default="DataNode")
    parser.add_argument("--apps", nargs="+", default=[])
    parser.add_argument("--data_dir", default="data/users")
    parser.add_argument("--user_id", default="user_01")

    # panorama_node 参数
    parser.add_argument("--llm_endpoint", default="http://localhost:9200")

    args = parser.parse_args()

    if args.role == "data_node":
        print(f"启动数据节点: {args.node_name}")
        print(f"  Apps: {args.apps}")
        print(f"  端口: {args.port}")
        print(f"  数据目录: {args.data_dir}")
        app = create_data_node_app(args.node_name, args.apps, args.data_dir, args.user_id)
        app.run(host=args.host, port=args.port, debug=False)

    elif args.role == "panorama_node":
        print(f"启动全景节点")
        print(f"  端口: {args.port}")
        print(f"  LLM端点: {args.llm_endpoint}")
        app = create_panorama_node_app(args.llm_endpoint)
        app.run(host=args.host, port=args.port, debug=False)


if __name__ == "__main__":
    main()
