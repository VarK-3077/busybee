# Laya benchmark (CPU)

Laya (Convai Innovations, ModernBERT-large 421M, non-autoregressive typed decisions). Same 600-pair sample, labels, weighting and metric code as `data/judge/benchmark.md` (`tools/bench_judges.py`; tools/bench_laya.py reuses them). Checkpoint `convaiinnovations/laya-typed-decisions` (the fine-tuned one), question type `noul` (P(true)), state = `Statement: ...` + `Passage: ...`, `max_len=4096` so the full passage is read (longest passage ~2.2k tokens). Latency = single pair, batch 1, torch 4 threads, nice 19, on the user's workstation with other load.

Cells: agreement / precision of 'supported' / recall of 'supported' at 0.5 | 0.7 | 0.9. Aggregates stratum-weighted as in benchmark.md.

| variant | slice | n | thr 0.5 | thr 0.7 | thr 0.9 | uncertain band 0.35-0.8 | s/pair |
|---|---|---|---|---|---|---|---|
| full | all | 121 | 33 / 100.0 / 11 | 24 / nan / 0 | 24 / nan / 0 | 44% | 1.85 |
| full | numeric | 95 | 29 / 100.0 / 9 | 22 / nan / 0 | 22 / nan / 0 | 42% | 1.86 |
| full | non-numeric | 26 | 73 / 100.0 / 46 | 50 / nan / 0 | 50 / nan / 0 | 69% | 1.82 |
| full | kind=annual_report | 91 | 34 / 100.0 / 12 | 25 / nan / 0 | 25 / nan / 0 | 42% | 1.89 |
| full | kind=rating_rationale | 16 | 30 / 100.0 / 10 | 22 / nan / 0 | 22 / nan / 0 | 37% | 2.09 |
| win | all | 600 | 30 / 80.8 / 10 | 24 / 100.0 / 0 | 24 / nan / 0 | 39% | 1.09 |
| win | numeric | 469 | 28 / 79.5 / 9 | 23 / 100.0 / 0 | 23 / nan / 0 | 38% | 1.10 |
| win | non-numeric | 131 | 54 / 85.3 / 35 | 36 / nan / 0 | 36 / nan / 0 | 60% | 1.04 |
| win | kind=annual_report | 453 | 28 / 74.7 / 7 | 24 / 100.0 / 0 | 24 / nan / 0 | 34% | 1.14 |
| win | kind=financial_statements | 11 | 36 / nan / 0 | 36 / nan / 0 | 36 / nan / 0 | 64% | 1.31 |
| win | kind=news | 25 | 56 / 85.6 / 47 | 28 / nan / 0 | 28 / nan / 0 | 81% | 0.76 |
| win | kind=rating_rationale | 94 | 33 / 97.1 / 17 | 19 / nan / 0 | 19 / nan / 0 | 53% | 0.96 |
| ft_win | all | 302 | 76 / 76.5 / 99 | 33 / 82.4 / 15 | 24 / nan / 0 | 98% | 1.12 |
| ft_win | numeric | 228 | 77 / 77.5 / 99 | 31 / 85.7 / 14 | 22 / nan / 0 | 99% | 1.14 |
| ft_win | non-numeric | 74 | 66 / 65.3 / 100 | 51 / 70.4 / 40 | 36 / nan / 0 | 96% | 1.05 |
| ft_win | kind=annual_report | 229 | 75 / 75.4 / 99 | 30 / 76.1 / 11 | 25 / nan / 0 | 98% | 1.16 |
| ft_win | kind=news | 12 | 84 / 84.0 / 100 | 79 / 100.0 / 76 | 16 / nan / 0 | 96% | 0.82 |
| ft_win | kind=rating_rationale | 45 | 83 / 82.8 / 100 | 40 / 88.2 / 32 | 17 / nan / 0 | 100% | 1.02 |

## Accept-only, full (zero-shot, full passage)

Auto-accept 'supported' when score >= th. 'False accept' = accepted where the LLM verdict is not supported (the 99.5-99.7% precision goal).

| th | accepted (n, of 121) | accepted share | false-accept rate | precision | recall of supported |
|---|---|---|---|---|---|
| 0.5 | 13 | 8.7% | 0.0% (0 unweighted) | 100.0% | 11.5% |
| 0.8 | 0 | 0.0% | 0.0% (0 unweighted) | nan% | 0.0% |
| 0.9 | 0 | 0.0% | 0.0% (0 unweighted) | nan% | 0.0% |
| 0.95 | 0 | 0.0% | 0.0% (0 unweighted) | nan% | 0.0% |

### Calibration (reliability bins), full

| score bin | n | weighted share | mean score | observed P(LLM supported) |
|---|---|---|---|---|
| 0.1-0.2 | 4 | 2.6% | 0.18 | 0.75 |
| 0.2-0.3 | 41 | 37.6% | 0.25 | 0.68 |
| 0.3-0.4 | 35 | 29.3% | 0.35 | 0.82 |
| 0.4-0.5 | 28 | 21.9% | 0.44 | 0.69 |
| 0.5-0.6 | 7 | 4.8% | 0.54 | 1.00 |
| 0.6-0.7 | 6 | 3.9% | 0.65 | 1.00 |

ECE (weighted, 10 bins) = 0.406

## Accept-only, win (zero-shot, 1,500-char window around first statement number)

Auto-accept 'supported' when score >= th. 'False accept' = accepted where the LLM verdict is not supported (the 99.5-99.7% precision goal).

| th | accepted (n, of 600) | accepted share | false-accept rate | precision | recall of supported |
|---|---|---|---|---|---|
| 0.5 | 73 | 9.8% | 19.2% (13 unweighted) | 80.8% | 10.4% |
| 0.8 | 0 | 0.0% | 0.0% (0 unweighted) | nan% | 0.0% |
| 0.9 | 0 | 0.0% | 0.0% (0 unweighted) | nan% | 0.0% |
| 0.95 | 0 | 0.0% | 0.0% (0 unweighted) | nan% | 0.0% |

### Calibration (reliability bins), win

| score bin | n | weighted share | mean score | observed P(LLM supported) |
|---|---|---|---|---|
| 0.1-0.2 | 44 | 7.7% | 0.18 | 0.53 |
| 0.2-0.3 | 214 | 38.4% | 0.25 | 0.74 |
| 0.3-0.4 | 160 | 26.4% | 0.35 | 0.77 |
| 0.4-0.5 | 109 | 17.7% | 0.44 | 0.87 |
| 0.5-0.6 | 60 | 8.2% | 0.54 | 0.79 |
| 0.6-0.7 | 12 | 1.4% | 0.65 | 0.91 |
| 0.7-0.8 | 1 | 0.2% | 0.71 | 1.00 |

ECE (weighted, 10 bins) = 0.425

## Accept-only, ft_win (fine-tuned on the other ~970 pairs, 1,500-char window)

Auto-accept 'supported' when score >= th. 'False accept' = accepted where the LLM verdict is not supported (the 99.5-99.7% precision goal).

| th | accepted (n, of 302) | accepted share | false-accept rate | precision | recall of supported |
|---|---|---|---|---|---|
| 0.5 | 299 | 99.4% | 23.5% (76 unweighted) | 76.5% | 99.5% |
| 0.8 | 6 | 1.5% | 0.0% (0 unweighted) | 100.0% | 2.0% |
| 0.9 | 0 | 0.0% | 0.0% (0 unweighted) | nan% | 0.0% |
| 0.95 | 0 | 0.0% | 0.0% (0 unweighted) | nan% | 0.0% |

### Calibration (reliability bins), ft_win

| score bin | n | weighted share | mean score | observed P(LLM supported) |
|---|---|---|---|---|
| 0.4-0.5 | 3 | 0.6% | 0.49 | 0.64 |
| 0.5-0.6 | 88 | 32.2% | 0.56 | 0.71 |
| 0.6-0.7 | 156 | 52.9% | 0.65 | 0.78 |
| 0.7-0.8 | 49 | 12.8% | 0.73 | 0.80 |
| 0.8-0.9 | 6 | 1.5% | 0.81 | 1.00 |

ECE (weighted, 10 bins) = 0.129

## Relevance zero-shot (indoco-v2 notebook, verify_relevance keep/drop)

200 random entries (seed 0); LLM keep=94, drop=106. Question: 'Is this fact relevant to deciding a credit line for the company?'. Mean 0.20 s/entry.

| th | predicted keep | agreement | precision(keep) | recall(keep) | precision(drop) | recall(drop) |
|---|---|---|---|---|---|---|
| 0.3 | 105 | 47.5% | 44.8% | 50.0% | 50.5% | 45.3% |
| 0.5 | 20 | 54.0% | 55.0% | 11.7% | 53.9% | 91.5% |
| 0.7 | 0 | 53.0% | n/a | 0.0% | 53.0% | 100.0% |
| 0.9 | 0 | 53.0% | n/a | 0.0% | 53.0% | 100.0% |

AUROC keep vs drop = 0.485 (majority-class agreement = 53.0%).

## Fine-tuning (partial) and conclusions

* Zero-shot `laya-typed-decisions` (variant `win`, n=600): scores never exceed ~0.8 (max bin 0.6-0.7), nothing is accepted at >=0.8, precision at 0.5 is 80.8% with 10% recall, ECE is high; `full` passage (n=121 only, the run was cut for time, 1.85 s/pair) behaves the same (13 accepts at 0.5, none at 0.8). The gate (precision at >=0.8 below 99.5% or recall below 40%) therefore fired.
* Fine-tune (variant `ft_win`): library recipe `laya.train.finetune` (RLCD + temperature calibration), encoder frozen (CPU cost), 600 of the ~970 non-sample pairs (540 train / 60 calibration), 1,500-char window format, 2 epochs, 3,300 s (epoch 1 took ~26 min, over the 25-min limit; run finished anyway because the library saves only at the end). Evaluated on the first 302 of the 600 held-out pairs only (PARTIAL; time box). Result: the head collapsed toward the majority class (77% of pairs are 'supported'): recall 99% at 0.5 but precision 76.5% = base rate, scores confined to 0.5-0.8, only 6 accepts at >=0.8 (all correct, 2% recall). Not useful as a judge. Unfrozen-encoder fine-tuning (~4x cost per pair) was not feasible on 4 CPU threads in the time box, so a full fine-tune is untested.
* Relevance zero-shot: AUROC 0.485 (chance) on 200 indoco-v2 entries; unusable.
* Speed: ~1.1 s/pair at 1,500 chars, ~1.9-2.5 s/pair full passage (4 threads, shared workstation), no faster than MiniCheck-T5 (3 s) by enough to matter and much worse in quality.
* No sidecar backend was added (nothing usable to serve).
* Recommendation: do not use Laya for entailment or relevance here. Keep MiniCheck-T5 accept-only (>=0.8) + LLM for the rest. Revisit only with a GPU encoder-unfrozen fine-tune on thousands of labelled pairs.

