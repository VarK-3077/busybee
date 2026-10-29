# Judge benchmark (CPU)

Set: data/judge/entailment.jsonl, 1571 unique pairs. LLM verdict `supported`=1, `partial`/`unsupported`=0.
Sample: every non-numeric pair plus a seeded random draw of numeric pairs up to 600 total (numeric stratum up-weighted to its share of the full set); all aggregate numbers below are stratum-weighted to the full set, per-slice rows are unweighted within the slice. Passage windowed to +-1000 chars around the first statement number found in the passage (else first 2000 chars). Latency = single pair, batch 1, 5 torch threads on a shared 20-core CPU (4 models ran concurrently, so expect somewhat better in isolation).

Cells: agreement with LLM / precision of 'supported' / recall of 'supported' at thresholds 0.5 | 0.7 | 0.9; band = share of pairs scoring 0.35-0.8.

| model | slice | n | thr 0.5 | thr 0.7 | thr 0.9 | uncertain band | s/pair |
|---|---|---|---|---|---|---|---|
| hhem | all | 600 | 64 / 95.5 / 55 | 55 / 96.5 / 43 | 42 / 98.3 / 25 | 22% | 0.63 |
| hhem | numeric | 469 | 63 / 96.1 / 54 | 54 / 96.8 / 41 | 40 / 98.8 / 23 | 23% | 0.63 |
| hhem | non-numeric | 131 | 73 / 90.0 / 64 | 71 / 94.2 / 58 | 65 / 95.2 / 48 | 13% | 0.62 |
| hhem | kind=annual_report | 453 | 58 / 95.1 / 46 | 48 / 95.7 / 33 | 36 / 100.0 / 16 | 25% | 0.66 |
| hhem | kind=financial_statements | 11 | 64 / 100.0 / 43 | 45 / 100.0 / 14 | 36 / nan / 0 | 64% | 0.47 |
| hhem | kind=news | 25 | 77 / 90.6 / 76 | 83 / 100.0 / 76 | 66 / 100.0 / 53 | 6% | 0.45 |
| hhem | kind=rating_rationale | 94 | 87 / 96.5 / 87 | 81 / 96.8 / 79 | 63 / 95.6 / 57 | 12% | 0.60 |
| minicheck_deb | all | 528 | 45 / 99.7 / 28 | 40 / 100.0 / 21 | 34 / 100.0 / 14 | 13% | 3.37 |
| minicheck_deb | numeric | 416 | 43 / 100.0 / 26 | 38 / 100.0 / 20 | 32 / 100.0 / 13 | 13% | 3.37 |
| minicheck_deb | non-numeric | 112 | 69 / 97.4 / 52 | 63 / 100.0 / 42 | 55 / 100.0 / 30 | 11% | 3.36 |
| minicheck_deb | kind=annual_report | 400 | 39 / 99.4 / 21 | 33 / 100.0 / 13 | 28 / 100.0 / 6 | 14% | 3.48 |
| minicheck_deb | kind=financial_statements | 11 | 36 / nan / 0 | 36 / nan / 0 | 36 / nan / 0 | 0% | 3.76 |
| minicheck_deb | kind=news | 21 | 72 / 100.0 / 61 | 72 / 100.0 / 61 | 70 / 100.0 / 58 | 7% | 2.51 |
| minicheck_deb | kind=rating_rationale | 81 | 62 / 100.0 / 53 | 60 / 100.0 / 50 | 51 / 100.0 / 40 | 7% | 3.10 |
| minicheck_t5 | all | 494 | 56 / 100.0 / 42 | 52 / 100.0 / 37 | 44 / 100.0 / 27 | 11% | 3.02 |
| minicheck_t5 | numeric | 390 | 54 / 100.0 / 42 | 51 / 100.0 / 37 | 42 / 100.0 / 26 | 11% | 3.01 |
| minicheck_t5 | non-numeric | 104 | 70 / 100.0 / 52 | 67 / 100.0 / 48 | 61 / 100.0 / 37 | 6% | 3.06 |
| minicheck_t5 | kind=annual_report | 376 | 52 / 100.0 / 37 | 47 / 100.0 / 31 | 38 / 100.0 / 20 | 14% | 3.13 |
| minicheck_t5 | kind=financial_statements | 10 | 30 / nan / 0 | 30 / nan / 0 | 30 / nan / 0 | 0% | 3.30 |
| minicheck_t5 | kind=news | 21 | 79 / 100.0 / 71 | 79 / 100.0 / 71 | 72 / 100.0 / 61 | 0% | 2.24 |
| minicheck_t5 | kind=rating_rationale | 72 | 71 / 100.0 / 63 | 71 / 100.0 / 63 | 64 / 100.0 / 55 | 2% | 2.79 |
| nli | all | 574 | 58 / 97.6 / 47 | 50 / 98.3 / 35 | 45 / 98.8 / 29 | 40% | 3.32 |
| nli | numeric | 447 | 57 / 97.6 / 46 | 49 / 98.4 / 35 | 44 / 99.0 / 28 | 40% | 3.32 |
| nli | non-numeric | 127 | 68 / 97.6 / 51 | 63 / 97.2 / 43 | 59 / 96.8 / 37 | 39% | 3.31 |
| nli | kind=annual_report | 433 | 55 / 97.6 / 43 | 47 / 98.9 / 31 | 42 / 100.0 / 24 | 41% | 3.42 |
| nli | kind=financial_statements | 11 | 100 / 100.0 / 100 | 100 / 100.0 / 100 | 100 / 100.0 / 100 | 0% | 3.26 |
| nli | kind=news | 25 | 83 / 100.0 / 76 | 77 / 100.0 / 68 | 76 / 100.0 / 66 | 8% | 2.57 |
| nli | kind=rating_rationale | 90 | 55 / 95.3 / 45 | 45 / 93.8 / 34 | 40 / 92.4 / 27 | 50% | 3.15 |

## Against the eval_citation label (second judge call on the final fact; only pairs with that label)

| model | n | thr | agree | prec(supported) | recall | LLM-entailment agree with eval (reference) |
|---|---|---|---|---|---|---|
| hhem | 395 | 0.5 | 46% | 100.0% | 46% | 88% |
| hhem | 395 | 0.7 | 36% | 100.0% | 36% | 88% |
| hhem | 395 | 0.9 | 21% | 100.0% | 21% | 88% |
| minicheck_deb | 344 | 0.5 | 21% | 100.0% | 21% | 89% |
| minicheck_deb | 344 | 0.7 | 16% | 100.0% | 15% | 89% |
| minicheck_deb | 344 | 0.9 | 10% | 100.0% | 10% | 89% |
| minicheck_t5 | 322 | 0.5 | 33% | 99.0% | 32% | 89% |
| minicheck_t5 | 322 | 0.7 | 29% | 98.9% | 28% | 89% |
| minicheck_t5 | 322 | 0.9 | 20% | 100.0% | 20% | 89% |
| nli | 376 | 0.5 | 36% | 99.3% | 36% | 88% |
| nli | 376 | 0.7 | 25% | 98.9% | 25% | 88% |
| nli | 376 | 0.9 | 19% | 98.6% | 18% | 88% |

## Tier simulation: classifier decides outside [lo, hi], LLM gets the rest

Accept 'supported' if score >= hi, reject if score < lo (rows treated as unsupported), else LLM. Error = classifier decision differs from LLM verdict; 'false-accept' = classifier says supported where the LLM says not (hurts citation precision).

| model | lo | hi | LLM share | auto-accept | auto-reject | false-accept (of auto-accepts) | missed-support (of auto-rejects) | overall disagreement |
|---|---|---|---|---|---|---|---|---|
| hhem | 0.35 | 0.8 | 22% | 28% | 50% | 2.5% | 57.2% | 29.1% |
| hhem | 0.2 | 0.9 | 40% | 19% | 41% | 1.7% | 50.7% | 20.9% |
| hhem | 0.1 | 0.9 | 52% | 19% | 29% | 1.7% | 44.0% | 13.1% |
| hhem | 0.05 | 0.95 | 71% | 11% | 18% | 0.6% | 30.5% | 5.7% |
| hhem | 0.02 | 0.98 | 87% | 2% | 11% | 0.0% | 24.1% | 2.6% |
| minicheck_deb | 0.35 | 0.8 | 13% | 14% | 73% | 0.0% | 68.2% | 50.0% |
| minicheck_deb | 0.2 | 0.9 | 22% | 11% | 66% | 0.0% | 65.5% | 43.5% |
| minicheck_deb | 0.1 | 0.9 | 34% | 11% | 54% | 0.0% | 58.8% | 32.0% |
| minicheck_deb | 0.05 | 0.95 | 55% | 8% | 37% | 0.0% | 46.0% | 17.1% |
| minicheck_deb | 0.02 | 0.98 | 84% | 1% | 14% | 0.0% | 35.9% | 5.2% |
| minicheck_t5 | 0.35 | 0.8 | 11% | 26% | 63% | 0.0% | 63.2% | 39.7% |
| minicheck_t5 | 0.2 | 0.9 | 21% | 21% | 58% | 0.0% | 60.9% | 35.6% |
| minicheck_t5 | 0.1 | 0.9 | 30% | 21% | 50% | 0.0% | 55.0% | 27.2% |
| minicheck_t5 | 0.05 | 0.95 | 48% | 15% | 37% | 0.0% | 48.6% | 18.1% |
| minicheck_t5 | 0.02 | 0.98 | 85% | 2% | 13% | 0.0% | 25.9% | 3.5% |
| nli | 0.35 | 0.8 | 40% | 25% | 35% | 1.9% | 53.7% | 19.1% |
| nli | 0.2 | 0.9 | 49% | 22% | 29% | 1.2% | 52.6% | 15.5% |
| nli | 0.1 | 0.9 | 54% | 22% | 24% | 1.2% | 47.9% | 11.8% |
| nli | 0.05 | 0.95 | 61% | 20% | 19% | 1.4% | 46.1% | 9.2% |
| nli | 0.02 | 0.98 | 69% | 16% | 15% | 1.3% | 41.2% | 6.5% |

## Notes and conclusions

* Sample sizes: HHEM n=600 complete; the three larger models were stopped after 494-574 of 600 for the time box (hash-ordered prefix of the same sample, so still random; stratum weights recomputed from the rows present).
* Models downloaded and ran on CPU: HHEM-2.1-Open, MiniCheck-DeBERTa-v3-Large, MiniCheck-Flan-T5-Large (T5 decoding of logits 3/209, 1024 tokens), DeBERTa-v3-large mnli-fever-anli-ling-wanli. Bespoke-MiniCheck-7B not tried (no GPU).
* The classifiers are conservative, not calibrated to this LLM judge: precision of "supported" is high (HHEM 95.5% at 0.5, MiniCheck 99.7-100%) but recall is only 28-55%. Classifier-only rejection is not usable (50-68% of auto-rejects are LLM-supported); only auto-accept is.
* Auto-accept with no false accepts vs the LLM in this sample: MiniCheck-T5 >=0.8 accepts ~26% of pairs, MiniCheck-DeBERTa >=0.8 ~14%; HHEM >=0.9 accepts ~19% with 1.7% false accepts (misses the 99.7% goal), NLI >=0.9 ~22% with ~1.2% false accepts.
* The LLM verdict agrees with the later eval_citation judgement on only 88-89% of pairs, so agreement with the LLM understates the achievable ceiling.
* Latency: HHEM ~0.6 s/pair; the 0.4-0.8B models 3.0-3.4 s/pair (bs=1, 5 threads, 4 models running concurrently on a shared CPU). GPU: tens of ms.
* Windowing +-1000 chars around the first number probably costs recall on multi-claim statements; untested improvement: sentence-level premises with max over windows (MiniCheck's own pipeline).
