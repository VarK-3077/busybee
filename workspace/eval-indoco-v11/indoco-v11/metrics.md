# Evaluation: indoco_remedies (run indoco-v11)

Report facts: 261

| Metric | Value |
| --- | --- |
| Important-statement recall | 93.3% |
| Recall (must-have only) | 93.3% |
| Important-statement precision | 92.7% |
| Citation precision | 99.2% |
| Page-exact rate | 100.0% |
| Planted-error catch rate | n/a |
| Proof pass rate | 100.0% |
| Run time (s) | 2352.5 |
| LLM calls | 364 |

| Fact set | Facts | Recall | Recall (must-have) | Precision |
| --- | --- | --- | --- | --- |
| main | 96 | 70.0% | 70.0% | 91.7% |
| main + appendix | 261 | 93.3% | 93.3% | 92.7% |
| all facts | 261 | 93.3% | 93.3% | 92.7% |

| LLM task | Calls |
| --- | --- |
| adversary_answer | 12 |
| adversary_questions | 1 |
| compose | 1 |
| compose_verdict_check | 1 |
| extract | 25 |
| infer | 1 |
| infer_check | 8 |
| infer_repair | 3 |
| policy.bind_inputs | 4 |
| policy.judge_slot | 2 |
| policy.slot_extract | 23 |
| policy.slot_extract.summary | 1 |
| verify_conflict | 2 |
| verify_entailment | 264 |
| verify_entailment_batch | 1 |
| verify_relevance | 15 |

| Stage | Seconds |
| --- | --- |
| ingest | 111.9 |
| index | 128.8 |
| extract | 717.0 |
| verify | 257.2 |
| scores | 241.8 |
| infer | 113.6 |
| adversary | 597.5 |
| compose | 184.6 |
| render | 0.2 |
