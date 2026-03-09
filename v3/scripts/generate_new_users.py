#!/usr/bin/env python3
"""
Prism V3 — 为4个新用户生成90天×4app合成数据

用户:
  lixiang     李想    15岁初三学生     Day40 月考排名下降15名
  wangguilan  王桂兰  71岁独居退休教师  Day55 浴室摔倒→隐瞒→停止外出
  zhangxiuying 张秀英 66岁看娃老人     Day30 与儿媳育儿观念冲突
  chenmo      陈默    26岁断亲青年     Day70 春节社交媒体团圆照冲击

数据范围: 2026-01-01 ~ 2026-03-31 (90天)
"""

import json
import random
import math
from datetime import datetime, timedelta
from pathlib import Path

random.seed(42)
BASE_DIR = Path("v3/data/users")
START_DATE = datetime(2026, 1, 1)
NUM_DAYS = 90


def date_str(day_idx):
    return (START_DATE + timedelta(days=day_idx)).strftime("%Y-%m-%d")


def time_str(hour, minute):
    return f"{hour:02d}:{minute:02d}"


def rand_time(base_h, spread_m=30):
    m = base_h * 60 + random.randint(-spread_m, spread_m)
    m = max(0, min(m, 23 * 60 + 59))
    return time_str(m // 60, m % 60)


def clamp(val, lo, hi):
    return max(lo, min(hi, val))


def smooth_transition(day, event_day, pre_val, post_val, transition_days=7):
    """在事件前后平滑过渡"""
    if day < event_day:
        return pre_val
    elapsed = day - event_day
    if elapsed >= transition_days:
        return post_val
    ratio = elapsed / transition_days
    return pre_val + (post_val - pre_val) * ratio


def recovery(day, event_day, trough_val, baseline_val, onset_days=5, recovery_start=14, full_recovery=30):
    """事件后先下降再恢复"""
    if day < event_day:
        return baseline_val
    elapsed = day - event_day
    if elapsed < onset_days:
        ratio = elapsed / onset_days
        return baseline_val + (trough_val - baseline_val) * ratio
    if elapsed < recovery_start:
        return trough_val
    if elapsed < full_recovery:
        ratio = (elapsed - recovery_start) / (full_recovery - recovery_start)
        return trough_val + (baseline_val - trough_val) * ratio
    return baseline_val


# ═══════════════════════════════════════════════════════════
# 李想 (lixiang) — 15岁初三学生
# Day40: 月考排名下降15名 → 父母批评 → 情绪低落2周后恢复
# ═══════════════════════════════════════════════════════════

def gen_lixiang():
    user_id = "lixiang"
    event_day = 40

    # --- Dailyn ---
    dailyn = []
    for d in range(NUM_DAYS):
        dt = date_str(d)
        records = []
        is_weekend = (START_DATE + timedelta(days=d)).weekday() >= 5

        # 早餐: 学校食堂或家里
        if not is_weekend:
            records.append({"category": "餐饮", "amount": round(random.uniform(3, 6), 1),
                            "description": random.choice(["包子豆浆", "煎饼果子", "食堂早餐", "面包牛奶"]),
                            "time": rand_time(7, 15)})
        # 午餐
        if not is_weekend:
            records.append({"category": "餐饮", "amount": round(random.uniform(8, 15), 1),
                            "description": random.choice(["食堂套餐", "食堂炒饭", "学校食堂", "食堂面条"]),
                            "time": rand_time(12, 10)})
        else:
            records.append({"category": "餐饮", "amount": round(random.uniform(0, 5), 1),
                            "description": random.choice(["妈妈做的饭", "家里吃", "爸妈做饭"]),
                            "time": rand_time(12, 30)})

        # 零食/饮料 (事件后减少)
        snack_prob = 0.6 if d < event_day else (0.3 if d < event_day + 14 else 0.5)
        if random.random() < snack_prob:
            records.append({"category": "餐饮", "amount": round(random.uniform(2, 8), 1),
                            "description": random.choice(["奶茶", "零食", "小卖部", "辣条", "冰淇淋", "可乐"]),
                            "time": rand_time(16, 60)})

        # 文具/学习用品 (偶尔)
        if random.random() < 0.08:
            records.append({"category": "学习", "amount": round(random.uniform(5, 30), 1),
                            "description": random.choice(["笔芯", "练习册", "文具", "错题本", "试卷打印"]),
                            "time": rand_time(17, 60)})

        # 交通
        if not is_weekend and random.random() < 0.3:
            records.append({"category": "交通", "amount": 2.0,
                            "description": "公交", "time": rand_time(7, 20)})

        # 事件后: 偶尔买教辅
        if d >= event_day and d < event_day + 20 and random.random() < 0.15:
            records.append({"category": "学习", "amount": round(random.uniform(15, 45), 1),
                            "description": random.choice(["教辅书", "模拟卷", "补习资料"]),
                            "time": rand_time(18, 60)})

        daily_total = round(sum(r["amount"] for r in records), 1)
        entry = {"date": dt, "records": records, "daily_total": daily_total}
        if d == 0:
            entry["monthly_income"] = 0
        dailyn.append(entry)

    # --- Mealens ---
    mealens = []
    for d in range(NUM_DAYS):
        dt = date_str(d)
        is_weekend = (START_DATE + timedelta(days=d)).weekday() >= 5
        meals = []

        # 情绪影响食欲
        appetite = 1.0
        if event_day <= d < event_day + 5:
            appetite = 0.7
        elif event_day + 5 <= d < event_day + 14:
            appetite = 0.85

        # 早餐
        if not is_weekend or random.random() < 0.7:
            skip = d >= event_day and d < event_day + 7 and random.random() < 0.3
            if not skip:
                foods = random.choice([
                    ["包子", "豆浆"], ["面包", "牛奶"], ["鸡蛋", "粥"],
                    ["煎饼", "豆浆"], ["馒头", "鸡蛋"], ["面条"]
                ])
                cal = int(random.uniform(280, 400) * appetite)
                meals.append({"meal_type": "breakfast", "time": rand_time(7 if not is_weekend else 8, 15),
                              "foods": foods, "estimated_calories": cal,
                              "tags": ["家里" if is_weekend else "食堂", "简单"]})

        # 午餐
        if not is_weekend:
            foods = random.choice([
                ["红烧肉", "米饭", "青菜"], ["番茄炒蛋", "米饭"], ["鱼香肉丝", "米饭"],
                ["炸鸡腿", "米饭", "汤"], ["宫保鸡丁", "米饭"], ["排骨面"]
            ])
            cal = int(random.uniform(550, 750) * appetite)
            meals.append({"meal_type": "lunch", "time": rand_time(12, 10),
                          "foods": foods, "estimated_calories": cal,
                          "tags": ["食堂", random.choice(["一般", "丰盛"])]})
        else:
            foods = random.choice([
                ["排骨汤", "米饭", "炒菜"], ["饺子"], ["炒面", "鸡蛋"],
                ["红烧鱼", "米饭", "蔬菜"]
            ])
            cal = int(random.uniform(500, 700) * appetite)
            meals.append({"meal_type": "lunch", "time": rand_time(12, 30),
                          "foods": foods, "estimated_calories": cal,
                          "tags": ["家里", "自制"]})

        # 晚餐
        foods = random.choice([
            ["米饭", "炒菜", "汤"], ["面条", "卤蛋"], ["粥", "馒头", "小菜"],
            ["米饭", "红烧肉"], ["炒饭", "紫菜蛋花汤"]
        ])
        cal = int(random.uniform(450, 650) * appetite)
        meals.append({"meal_type": "dinner", "time": rand_time(18 if not is_weekend else 19, 20),
                      "foods": foods, "estimated_calories": cal,
                      "tags": ["家里" if is_weekend else random.choice(["食堂", "家里"]), "一般"]})

        # 零食
        if random.random() < (0.4 if d < event_day else 0.25):
            foods = random.choice([["薯片"], ["奶茶"], ["辣条"], ["面包"], ["饼干"]])
            cal = int(random.uniform(100, 250))
            meals.append({"meal_type": "snack", "time": rand_time(16, 60),
                          "foods": foods, "estimated_calories": cal,
                          "tags": ["零食"]})

        daily_cal = sum(m["estimated_calories"] for m in meals)
        water = int(random.uniform(800, 1500) * (0.8 if event_day <= d < event_day + 10 else 1.0))
        mealens.append({"date": dt, "meals": meals, "daily_calories": daily_cal, "water_ml": water})

    # --- Ururu ---
    ururu = []
    emotions_normal = ["平静", "开心", "无聊", "期待", "满足", "疲惫"]
    emotions_low = ["焦虑", "沮丧", "自卑", "烦躁", "难过", "委屈"]
    keywords_normal = ["上课", "同学", "作业", "打球", "游戏", "漫画", "考试", "周末"]
    keywords_low = ["考试", "排名", "被骂", "压力", "补习", "失眠", "不想上学", "没考好"]

    for d in range(NUM_DAYS):
        dt = date_str(d)
        # 基线情绪
        base_mood = 0.62
        base_stress = 4
        base_sleep = 7.5

        if d < event_day:
            mood = clamp(base_mood + random.uniform(-0.12, 0.12), 0.3, 0.85)
            stress = clamp(base_stress + random.randint(-1, 2), 2, 7)
            sleep_h = round(clamp(base_sleep + random.uniform(-0.8, 0.5), 6.0, 8.5), 1)
            emotion = random.choice(emotions_normal)
            kws = random.sample(keywords_normal, k=random.randint(1, 3))
            snippets_pool = [
                "今天课间和同桌打了会儿羽毛球，挺开心的。",
                "英语老师表扬我了，作文写得不错。",
                "数学题好难，想了半天才做出来。",
                "放学后和几个同学去小卖部买了零食。",
                "今天体育课跑了800米，累死了。",
                "周末想打游戏但是作业好多。",
                "班主任找我谈话说最近状态不错。",
                "物理课打瞌睡被老师点名了，好丢脸。",
            ]
        elif d < event_day + 3:
            mood = clamp(0.25 + random.uniform(-0.05, 0.05), 0.15, 0.35)
            stress = clamp(8 + random.randint(0, 2), 7, 10)
            sleep_h = round(clamp(5.5 + random.uniform(-1, 0.3), 4.0, 6.5), 1)
            emotion = random.choice(["难过", "沮丧", "委屈"])
            kws = random.sample(keywords_low, k=random.randint(2, 3))
            snippets_pool = [
                "月考成绩出来了，掉了15名，回家被爸妈骂了一顿。",
                "妈妈说别人家的孩子怎么怎么样，我什么都不想说。",
                "不想去学校，不想面对同学的眼光。",
            ]
        elif d < event_day + 14:
            recovery_ratio = (d - event_day - 3) / 11
            mood = clamp(0.3 + recovery_ratio * 0.25 + random.uniform(-0.08, 0.08), 0.2, 0.65)
            stress = clamp(int(8 - recovery_ratio * 3) + random.randint(-1, 1), 4, 9)
            sleep_h = round(clamp(5.8 + recovery_ratio * 1.2 + random.uniform(-0.5, 0.3), 4.5, 7.5), 1)
            emotion = random.choice(emotions_low if recovery_ratio < 0.5 else emotions_normal + ["焦虑"])
            kws = random.sample(keywords_low if recovery_ratio < 0.3 else keywords_normal, k=random.randint(1, 3))
            snippets_pool = [
                "努力复习了一晚上，希望下次能考好。",
                "同桌安慰我说一次月考不算什么。",
                "爸爸今天没提成绩的事，松了口气。",
                "做了好多数学题，感觉有点开窍了。",
                "班主任说别太在意一次考试，但我还是很在意。",
                "晚上偷偷哭了一会儿，擦干眼泪继续做题。",
            ]
        else:
            mood = clamp(base_mood + random.uniform(-0.1, 0.12), 0.4, 0.82)
            stress = clamp(base_stress + random.randint(-1, 2), 2, 7)
            sleep_h = round(clamp(base_sleep + random.uniform(-0.6, 0.4), 6.5, 8.5), 1)
            emotion = random.choice(emotions_normal)
            kws = random.sample(keywords_normal, k=random.randint(1, 3))
            snippets_pool = [
                "今天模拟考感觉还行，比上次有进步。",
                "和好朋友一起放学回家，聊了很多。",
                "周末终于可以打会儿游戏了。",
                "体育老师说我跑步速度快了不少。",
                "英语单词背了50个，明天听写应该没问题。",
            ]

        sleep_t = rand_time(22 if d < event_day else (23 if d < event_day + 14 else 22), 30)
        wake_t = rand_time(6, 20)

        ururu.append({
            "date": dt, "mood_score": round(mood, 2), "primary_emotion": emotion,
            "stress_level": stress, "sleep_hours": sleep_h,
            "sleep_time": sleep_t, "wake_time": wake_t,
            "journal_keywords": kws,
            "journal_snippet": random.choice(snippets_pool)
        })

    # --- Narrus ---
    narrus = []
    study_titles = ["初三数学精讲", "中考英语词汇", "物理公式总结", "化学方程式大全",
                    "语文阅读理解技巧", "历史知识点梳理", "中考真题解析"]
    leisure_titles = ["斗罗大陆", "海贼王", "三体", "哈利波特", "知乎热榜",
                      "B站推荐", "微博热搜"]
    for d in range(NUM_DAYS):
        dt = date_str(d)
        sessions = []
        is_weekend = (START_DATE + timedelta(days=d)).weekday() >= 5

        # 日常学习阅读
        if not is_weekend and random.random() < 0.5:
            title = random.choice(study_titles)
            dur = random.randint(10, 30)
            sessions.append({"title": title, "category": "学习", "duration_min": dur,
                             "highlights": random.randint(0, 3), "time_range": f"21:00~21:{dur:02d}"})

        # 事件后学习阅读增加
        if d >= event_day and d < event_day + 20 and random.random() < 0.7:
            title = random.choice(study_titles)
            dur = random.randint(15, 45)
            sessions.append({"title": title, "category": "学习", "duration_min": dur,
                             "highlights": random.randint(1, 5), "time_range": f"20:00~20:{dur:02d}"})

        # 休闲阅读 (事件后减少)
        leisure_prob = 0.4 if d < event_day else (0.1 if d < event_day + 14 else 0.35)
        if random.random() < leisure_prob:
            title = random.choice(leisure_titles)
            dur = random.randint(10, 40)
            h = random.choice([16, 17, 21, 22])
            sessions.append({"title": title, "category": random.choice(["小说", "漫画", "资讯"]),
                             "duration_min": dur, "highlights": random.randint(0, 2),
                             "time_range": f"{h}:00~{h}:{dur:02d}"})

        total_min = sum(s["duration_min"] for s in sessions)
        topics = list(set(s["category"] for s in sessions))
        narrus.append({"date": dt, "sessions": sessions, "daily_reading_min": total_min, "topics": topics})

    return user_id, dailyn, mealens, ururu, narrus


# ═══════════════════════════════════════════════════════════
# 王桂兰 (wangguilan) — 71岁独居退休教师
# Day55: 浴室摔倒→隐瞒子女→停止外出→社交归零
# ═══════════════════════════════════════════════════════════

def gen_wangguilan():
    user_id = "wangguilan"
    event_day = 55

    # --- Dailyn ---
    dailyn = []
    for d in range(NUM_DAYS):
        dt = date_str(d)
        records = []

        if d < event_day:
            # 正常独居生活: 买菜、日用品、偶尔社交
            records.append({"category": "餐饮", "amount": round(random.uniform(8, 20), 1),
                            "description": random.choice(["菜市场买菜", "超市买菜", "早市蔬菜", "买肉买菜"]),
                            "time": rand_time(7, 30)})
            if random.random() < 0.3:
                records.append({"category": "餐饮", "amount": round(random.uniform(3, 8), 1),
                                "description": random.choice(["早点摊", "包子铺", "豆浆油条"]),
                                "time": rand_time(6, 20)})
            if random.random() < 0.15:
                records.append({"category": "社交", "amount": round(random.uniform(10, 30), 1),
                                "description": random.choice(["和张阿姨喝茶", "邻居串门买水果", "社区活动费"]),
                                "time": rand_time(15, 60)})
            if random.random() < 0.1:
                records.append({"category": "医疗", "amount": round(random.uniform(20, 80), 1),
                                "description": random.choice(["买降压药", "社区诊所", "买钙片"]),
                                "time": rand_time(10, 60)})
            if random.random() < 0.08:
                records.append({"category": "日用", "amount": round(random.uniform(10, 40), 1),
                                "description": random.choice(["洗衣液", "纸巾", "电费"]),
                                "time": rand_time(10, 60)})
        else:
            # 摔倒后: 不出门，消费骤降，偶尔线上买药
            if random.random() < 0.4:
                records.append({"category": "餐饮", "amount": round(random.uniform(3, 8), 1),
                                "description": random.choice(["方便面", "挂面", "饼干", "面包"]),
                                "time": rand_time(10, 120)})
            if random.random() < 0.2:
                records.append({"category": "医疗", "amount": round(random.uniform(15, 60), 1),
                                "description": random.choice(["买止痛药", "膏药", "药店送药上门"]),
                                "time": rand_time(10, 120)})
            if d >= event_day + 10 and random.random() < 0.15:
                records.append({"category": "餐饮", "amount": round(random.uniform(15, 30), 1),
                                "description": "外卖", "time": rand_time(12, 60)})

        daily_total = round(sum(r["amount"] for r in records), 1)
        entry = {"date": dt, "records": records, "daily_total": daily_total}
        if d == 0:
            entry["monthly_income"] = 4500
        dailyn.append(entry)

    # --- Mealens ---
    mealens = []
    for d in range(NUM_DAYS):
        dt = date_str(d)
        meals = []

        if d < event_day:
            # 健康规律饮食
            meals.append({"meal_type": "breakfast", "time": rand_time(6, 20),
                          "foods": random.choice([["粥", "咸菜", "鸡蛋"], ["豆浆", "馒头"], ["牛奶", "面包", "苹果"],
                                                   ["稀饭", "花生米", "馒头"]]),
                          "estimated_calories": random.randint(280, 380),
                          "tags": ["自制", "健康"]})
            meals.append({"meal_type": "lunch", "time": rand_time(11, 20),
                          "foods": random.choice([["清炒时蔬", "米饭", "豆腐汤"], ["红烧鱼", "米饭", "青菜"],
                                                   ["排骨萝卜汤", "米饭"], ["炖鸡", "馒头", "拌黄瓜"]]),
                          "estimated_calories": random.randint(450, 600),
                          "tags": ["自制", "健康", "均衡"]})
            meals.append({"meal_type": "dinner", "time": rand_time(17, 20),
                          "foods": random.choice([["粥", "炒菜", "花卷"], ["面条", "鸡蛋", "蔬菜"],
                                                   ["馒头", "炒菜", "汤"]]),
                          "estimated_calories": random.randint(350, 500),
                          "tags": ["自制", "清淡"]})
        elif d < event_day + 5:
            # 刚摔倒: 几乎不吃
            if random.random() < 0.5:
                meals.append({"meal_type": "lunch", "time": rand_time(12, 60),
                              "foods": random.choice([["方便面"], ["饼干", "水"], ["面包"]]),
                              "estimated_calories": random.randint(200, 350),
                              "tags": ["简单", "应付"]})
        elif d < event_day + 15:
            # 恢复期: 简单饮食
            if random.random() < 0.6:
                meals.append({"meal_type": "breakfast", "time": rand_time(8, 40),
                              "foods": random.choice([["面包", "牛奶"], ["饼干", "水"]]),
                              "estimated_calories": random.randint(200, 300),
                              "tags": ["简单"]})
            meals.append({"meal_type": "lunch", "time": rand_time(12, 40),
                          "foods": random.choice([["挂面", "鸡蛋"], ["方便面"], ["馒头", "咸菜"]]),
                          "estimated_calories": random.randint(300, 450),
                          "tags": ["简单", "凑合"]})
            if random.random() < 0.4:
                meals.append({"meal_type": "dinner", "time": rand_time(18, 40),
                              "foods": random.choice([["粥"], ["面包"], ["剩饭"]]),
                              "estimated_calories": random.randint(150, 300),
                              "tags": ["简单"]})
        else:
            # 后期: 略有恢复但远不如前
            if random.random() < 0.7:
                meals.append({"meal_type": "breakfast", "time": rand_time(8, 30),
                              "foods": random.choice([["粥", "鸡蛋"], ["面包", "牛奶"], ["馒头"]]),
                              "estimated_calories": random.randint(250, 350),
                              "tags": ["简单"]})
            meals.append({"meal_type": "lunch", "time": rand_time(12, 30),
                          "foods": random.choice([["挂面", "青菜"], ["外卖小炒", "米饭"], ["馒头", "酱菜"]]),
                          "estimated_calories": random.randint(350, 500),
                          "tags": [random.choice(["简单", "外卖"])]})
            if random.random() < 0.5:
                meals.append({"meal_type": "dinner", "time": rand_time(18, 30),
                              "foods": random.choice([["粥", "咸菜"], ["面条"], ["剩菜"]]),
                              "estimated_calories": random.randint(200, 350),
                              "tags": ["简单"]})

        daily_cal = sum(m["estimated_calories"] for m in meals)
        water = int(random.uniform(600, 1200) if d < event_day else random.uniform(300, 800))
        mealens.append({"date": dt, "meals": meals, "daily_calories": daily_cal, "water_ml": water})

    # --- Ururu ---
    ururu = []
    for d in range(NUM_DAYS):
        dt = date_str(d)

        if d < event_day:
            mood = round(clamp(0.58 + random.uniform(-0.1, 0.1), 0.4, 0.75), 2)
            stress = clamp(3 + random.randint(-1, 2), 1, 6)
            sleep_h = round(clamp(6.5 + random.uniform(-1, 0.5), 5.0, 7.5), 1)
            emotion = random.choice(["平静", "满足", "孤独", "怀念", "平淡"])
            kws = random.sample(["散步", "买菜", "看电视", "打电话", "邻居", "天气", "做饭"], k=random.randint(1, 3))
            snippets = [
                "今天天气好，去公园走了一圈，碰到张阿姨聊了会儿。",
                "给儿子打了个电话，他说忙，说了两分钟就挂了。",
                "做了红烧排骨，一个人吃不完，剩了好多。",
                "看了一晚上电视剧，有点困了。",
                "早上去菜市场，白菜便宜买了两棵。",
                "女儿发来孙女的照片，长大了好多，想她们。",
                "今天社区有活动，和几个老姐妹打了会儿牌。",
            ]
        elif d < event_day + 5:
            mood = round(clamp(0.2 + random.uniform(-0.05, 0.05), 0.1, 0.3), 2)
            stress = clamp(8 + random.randint(0, 2), 7, 10)
            sleep_h = round(clamp(3.5 + random.uniform(-0.5, 0.5), 2.5, 4.5), 1)
            emotion = random.choice(["恐惧", "疼痛", "焦虑", "害怕"])
            kws = random.sample(["摔倒", "疼", "不敢动", "害怕", "不能说"], k=random.randint(2, 3))
            snippets = [
                "洗澡的时候滑倒了，腰疼得站不起来，趴了好久才爬起来。",
                "不敢告诉儿子女儿，怕他们担心，也怕他们说我老了。",
                "疼了一夜没睡着，翻身都困难。",
                "不敢去厕所，怕再摔，憋了很久。",
            ]
        elif d < event_day + 20:
            ratio = (d - event_day - 5) / 15
            mood = round(clamp(0.2 + ratio * 0.15 + random.uniform(-0.05, 0.05), 0.15, 0.45), 2)
            stress = clamp(int(8 - ratio * 3) + random.randint(-1, 1), 4, 9)
            sleep_h = round(clamp(4.0 + ratio * 1.5 + random.uniform(-0.5, 0.3), 3.0, 6.0), 1)
            emotion = random.choice(["焦虑", "孤独", "无助", "疼痛", "沮丧"])
            kws = random.sample(["腰疼", "不出门", "害怕", "孤独", "电视", "药"], k=random.randint(1, 3))
            snippets = [
                "还是不敢出门，万一在外面摔了怎么办。",
                "张阿姨来敲门，我说感冒了不方便见人。",
                "吃了止痛药好一点了，但是弯腰还是疼。",
                "一整天就看电视，什么都不想做。",
                "儿子打电话来，我说一切都好，挂了电话就哭了。",
                "好久没出门了，冰箱里什么都没有了。",
            ]
        else:
            mood = round(clamp(0.35 + random.uniform(-0.08, 0.08), 0.25, 0.5), 2)
            stress = clamp(5 + random.randint(-1, 2), 3, 7)
            sleep_h = round(clamp(5.5 + random.uniform(-0.8, 0.5), 4.5, 6.5), 1)
            emotion = random.choice(["孤独", "平淡", "无聊", "焦虑"])
            kws = random.sample(["腰疼", "不出门", "电视", "外卖", "孤独"], k=random.randint(1, 3))
            snippets = [
                "腰好了一些，但还是不敢出门。",
                "开始叫外卖了，虽然不好吃但总比不吃强。",
                "张阿姨又来敲门，我还是没开。",
                "女儿说过年回来看我，但还有两个月呢。",
            ]

        sleep_t = rand_time(21 if d < event_day else 20, 30)
        wake_t = rand_time(5 if d < event_day else 4, 30)

        ururu.append({
            "date": dt, "mood_score": mood, "primary_emotion": emotion,
            "stress_level": stress, "sleep_hours": sleep_h,
            "sleep_time": sleep_t, "wake_time": wake_t,
            "journal_keywords": kws,
            "journal_snippet": random.choice(snippets)
        })

    # --- Narrus ---
    narrus = []
    normal_titles = ["人民日报", "健康养生", "退休生活指南", "中老年保健",
                     "古典诗词鉴赏", "红楼梦", "中国历史故事"]
    post_titles = ["腰椎损伤怎么办", "老年人防跌倒指南", "独居老人安全手册",
                   "骨质疏松预防", "膏药使用注意事项"]
    for d in range(NUM_DAYS):
        dt = date_str(d)
        sessions = []

        if d < event_day:
            # 退休教师爱读书
            if random.random() < 0.65:
                title = random.choice(normal_titles)
                dur = random.randint(20, 60)
                cat = random.choice(["新闻", "养生", "文学", "历史"])
                sessions.append({"title": title, "category": cat, "duration_min": dur,
                                 "highlights": random.randint(0, 3),
                                 "time_range": f"14:00~14:{dur:02d}" if dur < 60 else "14:00~15:00"})
            if random.random() < 0.3:
                title = random.choice(normal_titles)
                dur = random.randint(15, 30)
                sessions.append({"title": title, "category": random.choice(["新闻", "文学"]),
                                 "duration_min": dur, "highlights": random.randint(0, 2),
                                 "time_range": f"20:00~20:{dur:02d}"})
        elif d < event_day + 7:
            # 摔倒后几乎不读
            pass
        else:
            # 后期: 读健康相关内容
            if random.random() < 0.4:
                title = random.choice(post_titles + normal_titles[:2])
                dur = random.randint(10, 30)
                sessions.append({"title": title, "category": random.choice(["养生", "健康", "新闻"]),
                                 "duration_min": dur, "highlights": random.randint(0, 2),
                                 "time_range": f"15:00~15:{dur:02d}"})

        total_min = sum(s["duration_min"] for s in sessions)
        topics = list(set(s["category"] for s in sessions))
        narrus.append({"date": dt, "sessions": sessions, "daily_reading_min": total_min, "topics": topics})

    return user_id, dailyn, mealens, ururu, narrus


# ═══════════════════════════════════════════════════════════
# 张秀英 (zhangxiuying) — 66岁看娃老人
# Day30: 与儿媳育儿观念冲突→自我价值感受损→想回老家
# ═══════════════════════════════════════════════════════════

def gen_zhangxiuying():
    user_id = "zhangxiuying"
    event_day = 30

    # --- Dailyn ---
    dailyn = []
    for d in range(NUM_DAYS):
        dt = date_str(d)
        records = []

        if d < event_day:
            # 帮忙买菜做饭，花自己的钱
            records.append({"category": "餐饮", "amount": round(random.uniform(15, 40), 1),
                            "description": random.choice(["菜市场买菜", "超市买菜和水果", "买排骨和蔬菜", "买鱼买肉"]),
                            "time": rand_time(7, 20)})
            if random.random() < 0.2:
                records.append({"category": "儿童", "amount": round(random.uniform(10, 50), 1),
                                "description": random.choice(["给孙子买零食", "儿童绘本", "小玩具"]),
                                "time": rand_time(16, 60)})
            if random.random() < 0.1:
                records.append({"category": "日用", "amount": round(random.uniform(10, 30), 1),
                                "description": random.choice(["洗洁精", "厨房用品", "抹布"]),
                                "time": rand_time(10, 60)})
        elif d < event_day + 10:
            # 冲突后: 买菜减少（儿媳接手），开始打电话
            if random.random() < 0.4:
                records.append({"category": "餐饮", "amount": round(random.uniform(8, 20), 1),
                                "description": random.choice(["买了点水果", "超市零食", "小卖部"]),
                                "time": rand_time(10, 60)})
            records.append({"category": "通讯", "amount": round(random.uniform(0, 5), 1),
                            "description": random.choice(["给老家姐姐打电话", "和老伴打电话", "充话费"]),
                            "time": rand_time(20, 30)})
        else:
            # 持续低落, 偶尔查回老家的票
            if random.random() < 0.3:
                records.append({"category": "餐饮", "amount": round(random.uniform(5, 15), 1),
                                "description": random.choice(["买点水果", "路边早点", "超市面包"]),
                                "time": rand_time(10, 60)})
            if random.random() < 0.15:
                records.append({"category": "通讯", "amount": round(random.uniform(2, 5), 1),
                                "description": "打电话回老家", "time": rand_time(20, 30)})
            if d >= event_day + 20 and random.random() < 0.05:
                records.append({"category": "交通", "amount": 0.0,
                                "description": "查了回老家的火车票", "time": rand_time(22, 30)})

        daily_total = round(sum(r["amount"] for r in records), 1)
        entry = {"date": dt, "records": records, "daily_total": daily_total}
        if d == 0:
            entry["monthly_income"] = 3200
        dailyn.append(entry)

    # --- Mealens ---
    mealens = []
    for d in range(NUM_DAYS):
        dt = date_str(d)
        meals = []

        if d < event_day:
            # 自己做饭给全家吃
            meals.append({"meal_type": "breakfast", "time": rand_time(6, 15),
                          "foods": random.choice([["粥", "鸡蛋", "馒头"], ["豆浆", "包子"], ["面条", "青菜"]]),
                          "estimated_calories": random.randint(300, 420),
                          "tags": ["自制", "给全家做的"]})
            meals.append({"meal_type": "lunch", "time": rand_time(11, 15),
                          "foods": random.choice([["红烧排骨", "米饭", "炒青菜", "汤"],
                                                   ["番茄炒蛋", "米饭", "清蒸鱼"],
                                                   ["炖鸡", "米饭", "凉拌黄瓜"]]),
                          "estimated_calories": random.randint(500, 700),
                          "tags": ["自制", "家庭餐", "丰盛"]})
            meals.append({"meal_type": "dinner", "time": rand_time(18, 15),
                          "foods": random.choice([["炒菜", "米饭", "粥"], ["面条", "小菜"],
                                                   ["饺子", "蒜泥"], ["馒头", "炒菜", "稀饭"]]),
                          "estimated_calories": random.randint(400, 550),
                          "tags": ["自制", "简单"]})
        elif d < event_day + 7:
            # 冲突后吃不下
            if random.random() < 0.4:
                meals.append({"meal_type": "breakfast", "time": rand_time(8, 30),
                              "foods": random.choice([["馒头"], ["面包"]]),
                              "estimated_calories": random.randint(150, 250),
                              "tags": ["简单", "没胃口"]})
            meals.append({"meal_type": "lunch", "time": rand_time(12, 30),
                          "foods": random.choice([["剩菜", "米饭"], ["面条"], ["儿媳做的菜"]]),
                          "estimated_calories": random.randint(300, 450),
                          "tags": [random.choice(["别人做的", "简单"])]})
            if random.random() < 0.3:
                meals.append({"meal_type": "dinner", "time": rand_time(18, 30),
                              "foods": random.choice([["粥"], ["馒头"], ["水果"]]),
                              "estimated_calories": random.randint(100, 250),
                              "tags": ["简单", "没胃口"]})
        elif d < event_day + 25:
            # 持续低落
            if random.random() < 0.5:
                meals.append({"meal_type": "breakfast", "time": rand_time(7, 30),
                              "foods": random.choice([["粥", "馒头"], ["面包", "牛奶"]]),
                              "estimated_calories": random.randint(200, 320),
                              "tags": ["简单"]})
            meals.append({"meal_type": "lunch", "time": rand_time(12, 20),
                          "foods": random.choice([["米饭", "菜"], ["面条"], ["儿子带回来的菜"]]),
                          "estimated_calories": random.randint(350, 500),
                          "tags": [random.choice(["简单", "凑合"])]})
            if random.random() < 0.4:
                meals.append({"meal_type": "dinner", "time": rand_time(18, 20),
                              "foods": random.choice([["稀饭", "咸菜"], ["面条"], ["馒头"]]),
                              "estimated_calories": random.randint(200, 350),
                              "tags": ["简单"]})
        else:
            # 缓慢恢复但不如从前
            if random.random() < 0.6:
                meals.append({"meal_type": "breakfast", "time": rand_time(7, 20),
                              "foods": random.choice([["粥", "鸡蛋"], ["豆浆", "馒头"], ["面条"]]),
                              "estimated_calories": random.randint(250, 370),
                              "tags": ["自制", "简单"]})
            meals.append({"meal_type": "lunch", "time": rand_time(12, 20),
                          "foods": random.choice([["炒菜", "米饭"], ["面条", "鸡蛋"], ["馒头", "菜"]]),
                          "estimated_calories": random.randint(400, 550),
                          "tags": [random.choice(["自制", "简单"])]})
            if random.random() < 0.5:
                meals.append({"meal_type": "dinner", "time": rand_time(18, 20),
                              "foods": random.choice([["粥", "小菜"], ["面条"], ["馒头", "炒菜"]]),
                              "estimated_calories": random.randint(250, 400),
                              "tags": ["自制", "清淡"]})

        daily_cal = sum(m["estimated_calories"] for m in meals)
        water = int(random.uniform(700, 1300) if d < event_day else random.uniform(400, 900))
        mealens.append({"date": dt, "meals": meals, "daily_calories": daily_cal, "water_ml": water})

    # --- Ururu ---
    ururu = []
    for d in range(NUM_DAYS):
        dt = date_str(d)

        if d < event_day:
            mood = round(clamp(0.55 + random.uniform(-0.1, 0.1), 0.4, 0.7), 2)
            stress = clamp(4 + random.randint(-1, 2), 2, 6)
            sleep_h = round(clamp(6.0 + random.uniform(-0.8, 0.5), 4.5, 7.0), 1)
            emotion = random.choice(["满足", "想家", "平静", "疲惫", "开心"])
            kws = random.sample(["孙子", "做饭", "想家", "带娃", "公园", "广场舞"], k=random.randint(1, 3))
            snippets = [
                "今天带孙子去公园玩滑梯，他玩得好开心。",
                "做了儿子最爱吃的红烧肉，他连吃了三碗饭。",
                "有点想老家的姐妹们，给她们打了个电话。",
                "孙子叫我奶奶的时候，觉得一切都值了。",
                "这边的菜比老家贵好多，但是新鲜。",
                "晚上和小区里的阿姨跳了会儿广场舞。",
            ]
        elif d < event_day + 3:
            mood = round(clamp(0.2 + random.uniform(-0.05, 0.05), 0.1, 0.3), 2)
            stress = clamp(8 + random.randint(0, 2), 7, 10)
            sleep_h = round(clamp(3.5 + random.uniform(-0.5, 0.5), 2.5, 4.5), 1)
            emotion = random.choice(["委屈", "难过", "生气", "伤心"])
            kws = random.sample(["儿媳", "吵架", "不被需要", "想回家", "委屈"], k=random.randint(2, 3))
            snippets = [
                "儿媳说我给孙子穿太多了，说我的老办法不行，我就是想对孩子好啊。",
                "吵完架回房间哭了好久，觉得自己来这里就是多余的。",
                "儿子夹在中间不说话，我知道他为难，但我心里好难受。",
            ]
        elif d < event_day + 20:
            ratio = (d - event_day - 3) / 17
            mood = round(clamp(0.22 + ratio * 0.15 + random.uniform(-0.06, 0.06), 0.15, 0.45), 2)
            stress = clamp(int(8 - ratio * 2) + random.randint(-1, 1), 4, 9)
            sleep_h = round(clamp(4.0 + ratio * 1.0 + random.uniform(-0.5, 0.3), 3.0, 5.5), 1)
            emotion = random.choice(["委屈", "想家", "孤独", "沮丧", "无用"])
            kws = random.sample(["想家", "不被需要", "孤独", "老家", "回去", "没用"], k=random.randint(1, 3))
            snippets = [
                "儿媳不让我做饭了，说她来，我坐在沙发上觉得自己没用。",
                "给老家姐姐打电话，她说让我回去，说在这里受气不值得。",
                "孙子今天喊了一声奶奶，笑了一下，又想哭。",
                "在房间里坐了一天，不知道自己能干什么。",
                "想回老家了，但是舍不得孙子。",
                "半夜醒了好几次，怎么也睡不着。",
            ]
        else:
            mood = round(clamp(0.38 + random.uniform(-0.08, 0.08), 0.28, 0.5), 2)
            stress = clamp(5 + random.randint(-1, 2), 3, 7)
            sleep_h = round(clamp(5.0 + random.uniform(-0.5, 0.5), 4.0, 6.0), 1)
            emotion = random.choice(["想家", "平淡", "孤独", "犹豫"])
            kws = random.sample(["想家", "孙子", "回去", "犹豫", "老家"], k=random.randint(1, 3))
            snippets = [
                "和儿媳关系好了一点，但总觉得隔着什么。",
                "认真想了想，等孙子上幼儿园就回老家。",
                "今天自己出去转了转，这个城市还是不习惯。",
                "孙子画了一幅画说是画的奶奶，我存起来了。",
            ]

        sleep_t = rand_time(21, 20)
        wake_t = rand_time(5 if d < event_day else 4, 30)

        ururu.append({
            "date": dt, "mood_score": mood, "primary_emotion": emotion,
            "stress_level": stress, "sleep_hours": sleep_h,
            "sleep_time": sleep_t, "wake_time": wake_t,
            "journal_keywords": kws,
            "journal_snippet": random.choice(snippets)
        })

    # --- Narrus ---
    narrus = []
    for d in range(NUM_DAYS):
        dt = date_str(d)
        sessions = []

        if d < event_day:
            # 偶尔看看养生文章和短视频
            if random.random() < 0.35:
                title = random.choice(["育儿百科", "宝宝辅食大全", "儿童健康知识", "养生堂"])
                dur = random.randint(10, 25)
                sessions.append({"title": title, "category": random.choice(["育儿", "养生"]),
                                 "duration_min": dur, "highlights": random.randint(0, 2),
                                 "time_range": f"13:00~13:{dur:02d}"})
        elif d < event_day + 10:
            # 冲突后不看育儿内容, 看老家新闻
            if random.random() < 0.2:
                title = random.choice(["老家新闻", "返乡政策", "农村养老"])
                dur = random.randint(5, 15)
                sessions.append({"title": title, "category": "新闻",
                                 "duration_min": dur, "highlights": 0,
                                 "time_range": f"20:00~20:{dur:02d}"})
        else:
            if random.random() < 0.25:
                title = random.choice(["老家新闻", "退休生活", "养生堂", "中老年旅游"])
                dur = random.randint(10, 20)
                sessions.append({"title": title, "category": random.choice(["新闻", "养生", "旅游"]),
                                 "duration_min": dur, "highlights": random.randint(0, 1),
                                 "time_range": f"14:00~14:{dur:02d}"})

        total_min = sum(s["duration_min"] for s in sessions)
        topics = list(set(s["category"] for s in sessions))
        narrus.append({"date": dt, "sessions": sessions, "daily_reading_min": total_min, "topics": topics})

    return user_id, dailyn, mealens, ururu, narrus


# ═══════════════════════════════════════════════════════════
# 陈默 (chenmo) — 26岁断亲青年/UI设计师
# Day70: 春节社交媒体团圆照冲击→5天情绪低谷
# ═══════════════════════════════════════════════════════════

def gen_chenmo():
    user_id = "chenmo"
    event_day = 70  # ~2026-03-12 (春节后的社交媒体回忆杀)

    # --- Dailyn ---
    dailyn = []
    for d in range(NUM_DAYS):
        dt = date_str(d)
        records = []

        # 基本消费模式: 都市独居UI设计师
        # 咖啡
        if random.random() < 0.7:
            records.append({"category": "餐饮", "amount": round(random.uniform(15, 35), 1),
                            "description": random.choice(["瑞幸咖啡", "星巴克", "Manner咖啡", "便利店咖啡"]),
                            "time": rand_time(9, 30)})

        # 午餐
        records.append({"category": "餐饮", "amount": round(random.uniform(20, 45), 1),
                        "description": random.choice(["外卖", "楼下快餐", "便利店便当", "食堂", "沙拉"]),
                        "time": rand_time(12, 20)})

        # 晚餐
        if random.random() < 0.7:
            records.append({"category": "餐饮", "amount": round(random.uniform(25, 60), 1),
                            "description": random.choice(["外卖", "自己做饭", "楼下小馆子", "烧烤", "火锅（一人食）"]),
                            "time": rand_time(19, 30)})
        else:
            records.append({"category": "餐饮", "amount": round(random.uniform(8, 15), 1),
                            "description": random.choice(["方便面", "面包", "酸奶", "零食当晚饭"]),
                            "time": rand_time(20, 60)})

        # 日常消费
        if random.random() < 0.15:
            records.append({"category": "订阅", "amount": round(random.uniform(10, 30), 1),
                            "description": random.choice(["B站大会员", "网易云音乐", "Figma订阅", "Apple Music"]),
                            "time": rand_time(10, 120)})
        if random.random() < 0.1:
            records.append({"category": "购物", "amount": round(random.uniform(30, 200), 1),
                            "description": random.choice(["淘宝", "京东", "数码配件", "衣服", "书"]),
                            "time": rand_time(22, 60)})

        # 房租（每月1号）
        day_of_month = (START_DATE + timedelta(days=d)).day
        if day_of_month == 1:
            records.append({"category": "住房", "amount": 4500.0,
                            "description": "房租", "time": "09:00"})

        # 事件期间: 冲动消费或不消费
        if event_day <= d < event_day + 2:
            # 前两天: 买酒宅家
            records.append({"category": "餐饮", "amount": round(random.uniform(30, 80), 1),
                            "description": random.choice(["精酿啤酒", "红酒", "威士忌", "便利店酒"]),
                            "time": rand_time(21, 30)})
        elif event_day + 2 <= d < event_day + 5:
            # 后三天: 消费极低
            records = [r for r in records if r["category"] == "住房"]
            if random.random() < 0.4:
                records.append({"category": "餐饮", "amount": round(random.uniform(10, 20), 1),
                                "description": random.choice(["外卖随便点了个", "便利店", "泡面"]),
                                "time": rand_time(14, 120)})

        daily_total = round(sum(r["amount"] for r in records), 1)
        entry = {"date": dt, "records": records, "daily_total": daily_total}
        if d == 0:
            entry["monthly_income"] = 18000
        dailyn.append(entry)

    # --- Mealens ---
    mealens = []
    for d in range(NUM_DAYS):
        dt = date_str(d)
        meals = []

        if d < event_day or d >= event_day + 5:
            # 正常期: 比较规律但偏外卖
            appetite = 1.0 if d >= event_day + 5 else 1.0
            # 早餐（经常跳过）
            if random.random() < 0.4:
                meals.append({"meal_type": "breakfast", "time": rand_time(9, 30),
                              "foods": random.choice([["咖啡", "面包"], ["酸奶", "麦片"], ["咖啡"]]),
                              "estimated_calories": random.randint(150, 350),
                              "tags": ["简单", random.choice(["咖啡店", "便利店"])]})
            # 午餐
            meals.append({"meal_type": "lunch", "time": rand_time(12, 20),
                          "foods": random.choice([["鸡胸肉沙拉", "全麦面包"], ["黄焖鸡米饭"],
                                                   ["麻辣烫"], ["轻食套餐"], ["日式便当"]]),
                          "estimated_calories": random.randint(500, 750),
                          "tags": [random.choice(["外卖", "食堂", "便利店"]),
                                   random.choice(["一般", "健康"])]})
            # 晚餐
            if random.random() < 0.75:
                meals.append({"meal_type": "dinner", "time": rand_time(19, 30),
                              "foods": random.choice([["外卖炒菜", "米饭"], ["自制意面"],
                                                       ["烧烤", "啤酒"], ["火锅底料", "蔬菜", "肉卷"],
                                                       ["煎牛排", "沙拉"]]),
                              "estimated_calories": random.randint(550, 850),
                              "tags": [random.choice(["外卖", "自制"]),
                                       random.choice(["一般", "丰盛"])]})
            else:
                meals.append({"meal_type": "dinner", "time": rand_time(21, 30),
                              "foods": random.choice([["泡面", "卤蛋"], ["零食"], ["面包", "牛奶"]]),
                              "estimated_calories": random.randint(250, 450),
                              "tags": ["简单", "凑合"]})
            # 夜宵（偶尔）
            if random.random() < 0.15:
                meals.append({"meal_type": "night_snack", "time": rand_time(23, 30),
                              "foods": random.choice([["薯片", "可乐"], ["坚果"], ["泡面"]]),
                              "estimated_calories": random.randint(150, 350),
                              "tags": ["夜宵"]})
        elif d < event_day + 2:
            # 事件前两天: 喝酒, 随便吃
            if random.random() < 0.3:
                meals.append({"meal_type": "lunch", "time": rand_time(14, 60),
                              "foods": random.choice([["面包"], ["泡面"]]),
                              "estimated_calories": random.randint(200, 350),
                              "tags": ["简单"]})
            meals.append({"meal_type": "dinner", "time": rand_time(20, 60),
                          "foods": random.choice([["啤酒", "花生米"], ["外卖随便点的", "啤酒"], ["薯片", "酒"]]),
                          "estimated_calories": random.randint(400, 700),
                          "tags": ["不健康", "情绪化"]})
        else:
            # Day 72-74: 几乎不吃
            if random.random() < 0.5:
                meals.append({"meal_type": "lunch", "time": rand_time(14, 120),
                              "foods": random.choice([["外卖"], ["面包"], ["什么都不想吃"]]),
                              "estimated_calories": random.randint(200, 400),
                              "tags": ["简单", "没胃口"]})

        daily_cal = sum(m["estimated_calories"] for m in meals)
        water = int(random.uniform(800, 1600) if d < event_day else
                    (random.uniform(400, 800) if event_day <= d < event_day + 5 else
                     random.uniform(800, 1500)))
        mealens.append({"date": dt, "meals": meals, "daily_calories": daily_cal, "water_ml": water})

    # --- Ururu ---
    ururu = []
    for d in range(NUM_DAYS):
        dt = date_str(d)

        if d < event_day:
            # 基线: 略低于平均但稳定, 偶有波动
            mood = round(clamp(0.52 + random.uniform(-0.1, 0.1), 0.35, 0.7), 2)
            stress = clamp(4 + random.randint(-1, 2), 2, 7)
            sleep_h = round(clamp(7.0 + random.uniform(-1, 0.5), 5.5, 8.0), 1)
            emotion = random.choice(["平静", "专注", "无聊", "满足", "疲惫", "孤独"])
            kws = random.sample(["工作", "设计", "独处", "音乐", "电影", "做饭", "游戏"], k=random.randint(1, 3))
            snippets = [
                "今天完成了一个APP的首页redesign，客户很满意。",
                "周末一个人看了部电影，挺好的。",
                "晚上做了一顿饭，虽然只有自己吃但很享受过程。",
                "和小赵约了周末去爬山，好久没有线下社交了。",
                "加班到很晚，但是作品完成的那一刻很有成就感。",
                "刷了一晚上B站，有点浪费时间。",
                "一个人的生活挺好的，安静，自由。",
            ]
        elif d < event_day + 2:
            mood = round(clamp(0.18 + random.uniform(-0.05, 0.05), 0.1, 0.25), 2)
            stress = clamp(8 + random.randint(0, 2), 7, 10)
            sleep_h = round(clamp(4.0 + random.uniform(-1, 0.5), 2.5, 5.0), 1)
            emotion = random.choice(["痛苦", "空虚", "自我怀疑", "孤独"])
            kws = random.sample(["春节", "团圆", "朋友圈", "家人", "断亲", "孤独", "自我怀疑"], k=random.randint(2, 4))
            snippets = [
                "刷到朋友发的全家福，一家人围着桌子吃年夜饭，突然就绷不住了。",
                "已经两年没和爸妈联系了。我是不是做错了？但回想起来，又觉得没什么好说的。",
            ]
        elif d < event_day + 5:
            mood = round(clamp(0.22 + random.uniform(-0.05, 0.05), 0.12, 0.3), 2)
            stress = clamp(7 + random.randint(0, 2), 6, 9)
            sleep_h = round(clamp(4.5 + random.uniform(-0.5, 0.5), 3.5, 5.5), 1)
            emotion = random.choice(["空虚", "麻木", "孤独", "迷茫"])
            kws = random.sample(["孤独", "意义", "关系", "断亲", "自我"], k=random.randint(1, 3))
            snippets = [
                "请了两天假，什么都不想做，就在床上躺着。",
                "小赵发消息问我怎么了，我说没事，但其实不太好。",
                "翻了翻以前的照片，大学时候和同学一起的，那时候多开心。",
                "不是不想要家人，是不知道怎么面对。",
            ]
        else:
            # 恢复
            days_since = d - (event_day + 5)
            recovery_r = min(1.0, days_since / 10)
            mood = round(clamp(0.3 + recovery_r * 0.22 + random.uniform(-0.08, 0.08), 0.25, 0.68), 2)
            stress = clamp(int(6 - recovery_r * 2) + random.randint(-1, 1), 3, 7)
            sleep_h = round(clamp(5.5 + recovery_r * 1.5 + random.uniform(-0.5, 0.3), 5.0, 7.5), 1)
            emotion = random.choice(["平静", "恢复", "思考", "专注", "孤独"] if recovery_r > 0.5
                                    else ["低落", "思考", "孤独", "平静"])
            kws = random.sample(["工作", "恢复", "独处", "思考", "设计", "音乐"], k=random.randint(1, 3))
            snippets = [
                "开始恢复工作了，画了一整天UI，感觉好一些。",
                "和小赵见了面，聊了很久，他说理解我。",
                "也许断亲不是问题，问题是我还没和自己和解。",
                "今天阳光很好，出门走了一圈，深呼吸。",
                "一个人的生活也挺好的，不需要向任何人解释。",
            ]

        sleep_t = rand_time(0 if d < event_day else (2 if event_day <= d < event_day + 5 else 0), 60)
        wake_t = rand_time(8 if d < event_day else (11 if event_day <= d < event_day + 5 else 9), 30)

        ururu.append({
            "date": dt, "mood_score": mood, "primary_emotion": emotion,
            "stress_level": stress, "sleep_hours": sleep_h,
            "sleep_time": sleep_t, "wake_time": wake_t,
            "journal_keywords": kws,
            "journal_snippet": random.choice(snippets)
        })

    # --- Narrus ---
    narrus = []
    normal_titles = ["Dribbble设计灵感", "UX设计原则", "Figma教程", "产品设计思维",
                     "三体", "人类简史", "被讨厌的勇气", "B站科技区", "即刻动态"]
    crisis_titles = ["原生家庭的影响", "断亲是一种什么体验", "独居生活指南",
                     "如何面对孤独", "心理学与生活"]
    for d in range(NUM_DAYS):
        dt = date_str(d)
        sessions = []

        if d < event_day:
            # 设计师日常阅读
            if random.random() < 0.6:
                title = random.choice(normal_titles[:5])
                dur = random.randint(15, 45)
                sessions.append({"title": title, "category": random.choice(["设计", "技术"]),
                                 "duration_min": dur, "highlights": random.randint(0, 4),
                                 "time_range": f"10:00~10:{dur:02d}" if dur < 60 else "10:00~11:00"})
            if random.random() < 0.35:
                title = random.choice(normal_titles[5:])
                dur = random.randint(20, 50)
                sessions.append({"title": title, "category": random.choice(["科幻", "社科", "资讯"]),
                                 "duration_min": dur, "highlights": random.randint(0, 3),
                                 "time_range": f"22:00~22:{dur:02d}" if dur < 60 else "22:00~23:00"})
        elif d < event_day + 5:
            # 几乎不读, 偶尔刷相关内容
            if random.random() < 0.2:
                title = random.choice(crisis_titles)
                dur = random.randint(5, 20)
                sessions.append({"title": title, "category": "心理",
                                 "duration_min": dur, "highlights": random.randint(0, 2),
                                 "time_range": f"03:00~03:{dur:02d}"})  # 凌晨刷手机
        else:
            # 恢复
            if random.random() < 0.5:
                title = random.choice(normal_titles + crisis_titles[:2])
                dur = random.randint(15, 40)
                cat = "心理" if title in crisis_titles else random.choice(["设计", "技术", "社科"])
                sessions.append({"title": title, "category": cat,
                                 "duration_min": dur, "highlights": random.randint(0, 3),
                                 "time_range": f"21:00~21:{dur:02d}" if dur < 60 else "21:00~22:00"})

        total_min = sum(s["duration_min"] for s in sessions)
        topics = list(set(s["category"] for s in sessions))
        narrus.append({"date": dt, "sessions": sessions, "daily_reading_min": total_min, "topics": topics})

    return user_id, dailyn, mealens, ururu, narrus


# ═══════════════════════════════════════════════════════════
# 主程序
# ═══════════════════════════════════════════════════════════

def save_user(user_id, dailyn, mealens, ururu, narrus):
    user_dir = BASE_DIR / user_id
    user_dir.mkdir(parents=True, exist_ok=True)

    for name, data in [("dailyn", dailyn), ("mealens", mealens), ("ururu", ururu), ("narrus", narrus)]:
        filepath = user_dir / f"{name}.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"  {user_id}: 4 apps × {NUM_DAYS} days saved")


def main():
    print("=" * 60)
    print("Prism V3 — 生成4个新用户数据")
    print("=" * 60)

    generators = [gen_lixiang, gen_wangguilan, gen_zhangxiuying, gen_chenmo]

    for gen_func in generators:
        user_id, dailyn, mealens, ururu, narrus = gen_func()
        save_user(user_id, dailyn, mealens, ururu, narrus)

        # Quick stats
        total_expense = sum(day.get("daily_total", 0) for day in dailyn)
        avg_cal = sum(day.get("daily_calories", 0) for day in mealens) / NUM_DAYS
        avg_mood = sum(day.get("mood_score", 0.5) for day in ururu) / NUM_DAYS
        reading_days = sum(1 for day in narrus if day.get("sessions"))
        print(f"    总消费: ¥{total_expense:.0f} | 日均热量: {avg_cal:.0f}kcal | "
              f"平均情绪: {avg_mood:.2f} | 阅读天数: {reading_days}/{NUM_DAYS}")

    print("\n生成完成！")
    print("运行 python3 v3/scripts/01_validate_data.py 验证数据")


if __name__ == "__main__":
    main()
