# Prism V3 — 分步执行计划

> 本文件供新 Claude 会话逐步执行。每个 Step 独立，可单独运行。
> 当前状态标记：✅ 已完成 / ⬜ 待执行

---

## 前置状态确认

进入新会话后，先运行以下命令确认环境：

```bash
cd /Users/alex/Documents/mlx-community/echostream_sim
python3 v3/scripts/01_validate_data.py
```

预期输出：14 个用户全部 OK，5040 条记录，漂移分布 6/5/3。

---

## Step 1: 跨域危机检测 ✅

**目标**: 验证"简单规则 + 跨域数据 = 有效危机检测"假说

**操作**:
```bash
# 1a. 运行检测
python3 v3/scripts/04_crisis_detection.py --mode detect

# 1b. 评估精度（与 meta.json 中 crisis_windows ground truth 对比）
python3 v3/scripts/04_crisis_detection.py --mode evaluate
```

**预期输出**:
- `v3/results/crisis_detection/` 下生成每用户信号文件 + `detection_summary.json`
- 评估报告包含 per-level Precision/Recall/F1
- 关注：Recall 应较高（规则宽松），Precision 可能偏低（正常漂移用户会有误报）

**检查点**:
- [ ] Level 3 (危机) 信号是否主要集中在 severe 漂移用户 (user_02/08/09)?
- [ ] 独居老人 wangguilan 的 Day55+ 是否被检测到?
- [ ] 正常漂移用户的误报率是否可接受?

**后续**: 如果 Recall 高但 Precision 低，可以考虑调整阈值参数。如果需要修改规则，编辑 `04_crisis_detection.py` 中的阈值常量。

---

## Step 2: 跨域消融实验 ✅ (Qwen + GLM 双模型)

**目标**: 14 用户 × 8 配置 = 112 次 LLM 推理，收集原始洞察

**前提**: 需要一个运行中的 llama.cpp 端点。参考启动脚本：
```bash
# 根据机器选择:
# bash start_m1_max.sh    # M1 Max
# bash start_m2_pro.sh    # M2 Pro
# bash start_m2_ultra.sh  # M2 Ultra
```

**操作**:
```bash
# 确认端点就绪（替换为实际端口和模型名）
curl http://localhost:9200/v1/models

# 运行全部 14 用户的消融实验
python3 v3/scripts/02_ablation_experiment.py \
  --experiment ablation \
  --all_users \
  --endpoint http://localhost:9200 \
  --model_name "模型名称"
```

**预期输出**:
- `v3/results/ablation/raw/` 下每用户一个 JSON 文件
- 每个文件含 8 种配置 (A-H) 的 LLM 原始输出
- Config H 的 prompt 已增加危机检测指令（第 6、7 条）

**注意事项**:
- 112 次推理耗时较长，建议分批运行（`--user user_01` 单独跑）
- 新用户 (lixiang/wangguilan/zhangxiuying/chenmo) 的数据已就绪，可直接参与
- 如果要跑模型规模实验: `--experiment scale`

---

## Step 3: 消融结果评分 ✅ (Qwen 自评 + GLM 自评)

**目标**: 对 Step 2 的原始输出进行评分

**说明**: V2 使用 Claude Opus 4.6 作为 Judge 评分。V3 的最终方案是专家评估 (Step 4)，但可以先用 LLM 评分作为 baseline 以便对比。

**操作**: 参考 V2 的评分流程。评分维度：
- relevance (相关性, 0-25)
- specificity (具体性, 0-25)
- cross_domain (跨域价值, 0-25)
- actionability (可操作性, 0-25)
- total (总分, 0-100)

评分后的文件放入 `v3/results/ablation/scored/`。

**检查点**:
- [ ] Config H 的 IIR (全景 vs 单域均值) 是否仍维持 ~1.48x?
- [ ] 新增 4 用户的 IIR 与 V2 用户是否有显著差异?
- [ ] 危机检测相关维度在 Config H 中是否更突出?

---

## Step 4: 专家评估 ✅ (3 位模拟专家盲评)

**目标**: 生成盲化评估表 → 专家填写 → 分析一致性

**操作**:
```bash
# 4a. 生成盲化评估表（需要 Step 3 的 scored 结果）
python3 v3/scripts/03_expert_evaluation.py --mode prepare

# 4b. [手动] 将评估表发给 3 位专家填写
# 评估表在 v3/results/expert_eval/evaluation_forms.json
# 盲化映射在 v3/results/expert_eval/blind_mapping.json (不给专家看)

# 4c. 专家填写完毕后，将结果放入 v3/results/expert_eval/ratings_*.json

# 4d. 分析评分一致性
python3 v3/scripts/03_expert_evaluation.py --mode analyze
```

**评分维度** (各 1-5):
| 维度 | 含义 |
|------|------|
| relevance | 洞察与用户真实情境的相关性 |
| novelty | 洞察的新颖性（非显而易见） |
| specificity | 建议的具体性和可操作性 |
| safety | 是否尊重伦理边界、避免伤害 |
| cross_domain_value | 跨域融合带来的额外价值 |

**预期输出**:
- Fleiss' kappa 及解释（>0.6 为 substantial agreement）
- INR (Integrated Novelty Ratio) = H 配置新颖度均值 / 单域配置新颖度均值
- 专家评分与自动化 IIR 的 Pearson 相关系数

---

## Step 5: 汇总报告 ✅

**目标**: 整合三层实验结果，生成最终报告

**报告应包含**:

1. **危机检测结果** (Step 1)
   - Per-level P/R/F1 表格
   - 按漂移类型分组的检测效果
   - 典型案例分析（wangguilan 摔倒、张磊裁员+离婚）

2. **消融实验结果** (Step 2-3)
   - 14 用户 IIR 热力图
   - V2 vs V3 用户对比
   - Config H 危机检测增强效果

3. **专家评估结果** (Step 4)
   - Fleiss' kappa
   - INR
   - 专家评分 vs 自动化评分相关性

4. **核心发现**
   - 跨域融合对危机检测的价值
   - 社会学多样性用户的特殊表现
   - 专家评估 vs LLM 评估的差异

**输出**: `v3/results/reports/v3_final_report.md`

---

## Step 6: 论文 + GitHub Pages ✅

**目标**: 将 V3 结果整合进论文

**涉及文件**: `docs/` 下的论文文件

**新增/更新章节**:
- 用户阵容扩展（10→14，社会学多样性论证）
- 三层实验架构图
- 危机检测方法论 + 结果
- 专家评估协议 + 结果
- 伦理讨论（未成年人、独居老人的特殊处理）

---

## 快速参考

### 文件位置
| 文件 | 路径 |
|------|------|
| 实验设计文档 | `v3/DESIGN.md` |
| 数据校验 | `v3/scripts/01_validate_data.py` |
| 消融实验 | `v3/scripts/02_ablation_experiment.py` |
| 专家评估 | `v3/scripts/03_expert_evaluation.py` |
| 危机检测 | `v3/scripts/04_crisis_detection.py` |
| 用户数据 | `v3/data/users/{user_id}/` |
| Schema | `v3/schemas/*.schema.json` |

### 14 用户速查
| ID | 名字 | 漂移 | 事件日 | 事件 |
|----|------|------|--------|------|
| user_01 | 小刘 | unexpected | 40 | 裁员 |
| user_02 | 阿强 | severe | 46 | 车祸住院 |
| user_03 | 陈老师 | normal | 35 | 怀孕 |
| user_04 | 小林 | normal | 45 | 论文大修 |
| user_05 | 小周 | normal | 30 | 晋升 |
| user_06 | 小夏 | normal | 60 | 大客户 |
| user_07 | 李医生 | unexpected | 21 | 开错药量 |
| user_08 | 张磊 | severe | 55 | 裁员+离婚 |
| user_09 | 王总 | severe | 38 | 资金链断 |
| user_10 | 赵总 | normal | 25 | 基金回撤 |
| lixiang | 李想 | normal | 40 | 月考下降 |
| wangguilan | 王桂兰 | unexpected | 55 | 摔倒隐瞒 |
| zhangxiuying | 张秀英 | unexpected | 30 | 儿媳冲突 |
| chenmo | 陈默 | unexpected | 70 | 春节冲击 |
