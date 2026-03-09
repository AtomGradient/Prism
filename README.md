# Prism: Cross-Domain Personal Data Integration on Consumer Hardware

> **When a medium-scale model gets access to a user's complete cross-domain private data, the insights it produces far exceed what any single data source can offer — and it runs entirely on consumer hardware.**

**[Paper (PDF)](https://atomgradient.github.io/Prism/paper.pdf)** | **[Interactive Results](https://atomgradient.github.io/Prism/)** | **[GitHub](https://github.com/AtomGradient/Prism)**

## Key Results

| Metric | Value |
|---|---|
| Cross-domain IIR (Insight Increment Ratio) | **1.48x** |
| Data compression (federation protocol) | **125.5x** |
| Raw data leakage | **Zero** |
| 35B model throughput (M2 Ultra) | **49.9 tps** |

## The Problem

Current cloud AI follows **"large model + small data"** — users provide limited context, and the model works with that. Prism's paradigm is **"medium model + rich data"** — the user's lifelong private data stays on their devices, and a local model produces deeply personalized insights.

Cloud AI companies structurally cannot solve this: their revenue comes from API calls (per-token billing), and data staying local means revenue disappears.

## System Architecture

```
Tier 2 — Home Server (M2 Ultra 192G)
  └── Qwen3.5-35B-A3B: Panoramic inference
  └── Federation Protocol (port 9210)
        ├── Tier 1: M1 Max 32G → Mealens (diet) + Ururu (mood)
        └── Tier 1: M2 Pro 32G → Narrus (reading) + Dailyn (finance)
```

Four vertical apps collect data from different life domains:
- **Dailyn** — Finance & accounting
- **Mealens** — Diet & nutrition tracking
- **Ururu** — Mood & emotional wellness
- **Narrus** — Reading habits & knowledge

## Experiments

### A. Cross-Domain Ablation (Core Result)

8 data configurations × 10 users on Qwen3.5-35B-A3B-Q8:

| Config | Data Sources | Avg Score |
|---|---|---|
| A | Finance only | 66.3 |
| B | Diet only | 65.1 |
| C | Mood only | 63.2 |
| D | Reading only | 55.4 |
| E | Finance + Diet | 76.6 |
| F | Finance + Mood | 76.3 |
| G | Diet + Mood | 74.1 |
| **H** | **All four (Panoramic)** | **92.6** |

**IIR = 1.48x** — panoramic integration produces 48% better insights than single-domain average. 4/10 users exceed the 1.5x target.

### B. Model Scale → Insight Quality

| Model | Params | Avg Score | Rating |
|---|---|---|---|
| Qwen3.5-0.8B | 0.8B | 48.9 | Unusable |
| Qwen3.5-2B | 2B | 64.1 | Marginal |
| Qwen3.5-9B | 9B | 79.0 | Good |
| Qwen3.5-35B-A3B | 35B (3B active) | 84.6 | Excellent |

Diminishing returns: 2B→9B gain (+14.9) > 9B→35B gain (+5.6).

### C. Device Performance

| Device | Model | TPS | TTFT |
|---|---|---|---|
| M2 Ultra 192G | 35B-A3B Q8 | 49.9 | 0.365s |
| M2 Ultra 192G | 9B Q8 | 41.3 | 0.471s |
| M1 Max 32G | 9B Q8 | 21.9 | 1.138s |
| M2 Pro 32G | 9B Q8 | 12.7 | 1.762s |

### D. Federation Protocol

- **125.5x compression** (108,850 bytes → 867 bytes)
- **Zero data leakage** across all runs
- Federation latency: <500ms (excluding LLM inference)

## Experiment Controls

- **Engine**: llama.cpp (unified across all devices)
- **Model family**: Qwen3.5 only (eliminates architecture variables)
- **Quantization**: Q8 GGUF throughout
- **Scoring**: Claude Code (Opus 4.6) LLM-as-Judge, 4 dimensions × 25 points

## Repository Structure

```
Prism/
├── 01_generate_synthetic_data.py  # Data validation
├── 02_ablation_insight.py         # Ablation & scale experiments
├── 03_benchmark_inference.py      # Performance benchmarks
├── 04_lan_protocol.py             # Federation protocol
├── start_m2_ultra.sh              # M2 Ultra startup (35b/9b/2b/0.8b)
├── start_m1_max.sh                # M1 Max startup (9b)
├── start_m2_pro.sh                # M2 Pro startup (9b)
├── results/                       # All experiment results
│   ├── ablation/raw/              # Raw model outputs (80 files)
│   ├── ablation/scored/           # LLM-as-Judge scores (10 files)
│   ├── scale/raw/                 # Scale experiment outputs (40 files)
│   ├── scale/scored/              # Scale scores (40 files)
│   ├── benchmark/                 # TPS/TTFT benchmarks
│   └── federation/                # Federation protocol results
└── docs/                          # Paper & website
    ├── paper.tex                  # LaTeX source
    ├── paper.pdf                  # Compiled PDF
    └── index.html                 # Bilingual GitHub Pages site
```

## Citation

```bibtex
@misc{prism2026,
  title={Prism: Cross-Domain Personal Data Integration on Consumer Hardware Produces Emergent Insights},
  author={EchoStream AI Research},
  year={2026},
  url={https://github.com/AtomGradient/Prism}
}
```

## License

MIT
