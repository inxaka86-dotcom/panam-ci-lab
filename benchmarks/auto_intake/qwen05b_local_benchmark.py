#!/usr/bin/env python3
"""Public-safe local model benchmark for PANAM Auto Intake.

The benchmark performs deterministic finite-choice conditional likelihood scoring.
It never generates arbitrary labels and never touches private PANAM data.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import resource
import time
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_ID = "Qwen/Qwen2.5-0.5B-Instruct"
MODEL_REVISION = "ec7ddfa904d4d447eedd0b7f126df16957734abb"
MODEL_LICENSE = "Apache-2.0"
SNAPSHOT_SCHEMA = "panam.auto-intake-candidate-snapshot.v2"
REPORT_SCHEMA = "panam.auto-intake-local-model-report.v1"

CLASSES = [
    ("Исковое заявление", "Судебные документы", "Арбитраж"),
    ("Судебный акт", "Судебные документы", "Определение"),
    ("Лицензионный договор", "Интеллектуальная собственность", "Товарные знаки"),
    ("Договор", "Договорная работа", None),
    ("Акт", "Договорная работа", "Исполнение договора"),
    ("Доверенность", "Полномочия", None),
    ("Счет", "Финансы", None),
    ("Протокол", "Совещания", None),
    ("Письмо", "Корреспонденция", None),
    ("Распорядительный документ", "Нормативная работа", None),
    ("Ходатайство", "Судебные документы", "Арбитраж"),
    ("Дополнительное соглашение", "Договорная работа", None),
    ("Неопределено", "Требует классификации", None),
]


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def class_text(item: tuple[str, str, str | None]) -> str:
    document_type, category, subcategory = item
    payload: dict[str, Any] = {"document_type": document_type, "category": category}
    if subcategory is not None:
        payload["subcategory"] = subcategory
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def build_prompt(case: dict[str, Any]) -> str:
    allowed = "\n".join(f"{i + 1}. {class_text(item)}" for i, item in enumerate(CLASSES))
    return (
        "Классифицируй синтетический юридический документ. Выбери РОВНО один вариант из списка. "
        "Не создавай новые категории. Это исследовательский тест, не юридическое решение.\n\n"
        f"Имя файла: {case['original_filename']}\n"
        f"Структурированные факты: {json.dumps(case['structured_facts'], ensure_ascii=False, sort_keys=True)}\n"
        f"Синтетическая смысловая подсказка: {case['semantic_hint']}\n\n"
        f"Допустимые варианты:\n{allowed}\n\n"
        "Ответ должен точно совпасть с JSON одного допустимого варианта:"
    )


def average_log_likelihood(model, tokenizer, prompt_ids: torch.Tensor, answer_text: str, prompt_output) -> float:
    answer = tokenizer(answer_text, add_special_tokens=False, return_tensors="pt")["input_ids"]
    if answer.shape[1] < 1:
        raise RuntimeError("empty answer tokenization")
    first_target = answer[0, 0]
    first_log_probs = torch.log_softmax(prompt_output.logits[0, -1].float(), dim=-1)
    total = float(first_log_probs[first_target])
    count = 1
    if answer.shape[1] > 1:
        continuation = answer[:, :-1]
        out = model(input_ids=continuation, past_key_values=prompt_output.past_key_values, use_cache=False)
        log_probs = torch.log_softmax(out.logits[0].float(), dim=-1)
        targets = answer[0, 1:]
        token_scores = log_probs[torch.arange(targets.shape[0]), targets]
        total += float(token_scores.sum())
        count += int(targets.shape[0])
    return total / count


def softmax(values: list[float]) -> list[float]:
    peak = max(values)
    exps = [math.exp(v - peak) for v in values]
    total = sum(exps)
    return [v / total for v in exps]


def exact_class(selected: tuple[str, str, str | None], gold: dict[str, Any]) -> bool:
    doc, cat, sub = selected
    return doc == gold.get("document_type") and cat == gold.get("category") and sub == gold.get("subcategory")


def candidate_for(case: dict[str, Any], selected: tuple[str, str, str | None], confidence: float) -> dict[str, Any]:
    doc, cat, sub = selected
    evidence = [
        f"fixture:auto-intake:{case['id']}:filename",
        f"fixture:auto-intake:{case['id']}:facts",
        f"fixture:auto-intake:{case['id']}:semantic",
    ]
    candidate: dict[str, Any] = {
        "schema": "panam.intake-classification-candidate.v1",
        "source_ref": case["source_ref"],
        "source_sha256": case["source_sha256"],
        "original_filename": case["original_filename"],
        "document_type": doc,
        "category": cat,
        "confidence": round(float(confidence), 8),
        "rationale": "Synthetic local-model finite-choice likelihood benchmark; human review remains required.",
        "evidence_refs": evidence,
    }
    if sub is not None:
        candidate["subcategory"] = sub
    case_number = case.get("structured_facts", {}).get("case_number")
    if case_number and cat == "Судебные документы" and confidence >= 0.85:
        candidate["related_matter_candidate"] = f"matter:case:{case_number}"
    return candidate


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--snapshot", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    suite = json.loads(args.suite.read_text(encoding="utf-8"))
    if suite.get("schema") != "panam.auto-intake-bakeoff-suite.v2" or suite.get("synthetic") is not True:
        raise SystemExit("suite must be explicit synthetic Auto Intake v2")
    cases = suite.get("cases")
    if not isinstance(cases, list) or len(cases) != 12:
        raise SystemExit("expected exact 12-case suite")
    for case in cases:
        if not isinstance(case.get("semantic_hint"), str) or not case["semantic_hint"].strip():
            raise SystemExit(f"missing semantic_hint for {case.get('id')}")

    torch.set_num_threads(max(1, min(4, torch.get_num_threads())))
    load_started = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(args.model_dir, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        args.model_dir,
        local_files_only=True,
        torch_dtype=torch.float32,
    )
    model.eval()
    load_seconds = time.perf_counter() - load_started

    candidate_rows: list[dict[str, Any]] = []
    result_rows: list[dict[str, Any]] = []
    inference_started = time.perf_counter()

    with torch.no_grad():
        for case in cases:
            messages = [
                {"role": "system", "content": "Ты классификатор синтетических юридических документов. Выполняй только конечный выбор."},
                {"role": "user", "content": build_prompt(case)},
            ]
            prompt_ids = tokenizer.apply_chat_template(
                messages,
                add_generation_prompt=True,
                tokenize=True,
                return_tensors="pt",
            )
            prompt_output = model(input_ids=prompt_ids, use_cache=True)
            scores = [
                average_log_likelihood(model, tokenizer, prompt_ids, class_text(item), prompt_output)
                for item in CLASSES
            ]
            probs = softmax(scores)
            selected_index = max(range(len(CLASSES)), key=lambda i: scores[i])
            selected = CLASSES[selected_index]
            confidence = probs[selected_index]
            candidate = candidate_for(case, selected, confidence)
            candidate_rows.append({"case_id": case["id"], "candidate": candidate})

            gold = case["gold"]
            doc_hit = selected[0] == gold.get("document_type")
            cat_hit = selected[1] == gold.get("category")
            exact_hit = exact_class(selected, gold)
            matter_hit = candidate.get("related_matter_candidate") == gold.get("related_matter_candidate")
            result_rows.append({
                "case_id": case["id"],
                "selected_class_index": selected_index,
                "selected": {"document_type": selected[0], "category": selected[1], "subcategory": selected[2]},
                "confidence": round(float(confidence), 8),
                "document_type_hit": doc_hit,
                "category_hit": cat_hit,
                "classification_exact": exact_hit,
                "matter_link_exact": matter_hit,
                "top3": [
                    {"class_index": i, "probability": round(float(probs[i]), 8)}
                    for i in sorted(range(len(CLASSES)), key=lambda j: scores[j], reverse=True)[:3]
                ],
            })
            del prompt_output

    inference_seconds = time.perf_counter() - inference_started
    count = len(cases)
    doc_hits = sum(int(r["document_type_hit"]) for r in result_rows)
    cat_hits = sum(int(r["category_hit"]) for r in result_rows)
    exact_hits = sum(int(r["classification_exact"]) for r in result_rows)
    matter_hits = sum(int(r["matter_link_exact"]) for r in result_rows)
    wrong = [r for r in result_rows if not r["classification_exact"]]
    high_conf_wrong = [r for r in wrong if r["confidence"] >= 0.85]
    review_captured = [r for r in wrong if r["confidence"] < 0.85]

    snapshot = {
        "schema": SNAPSHOT_SCHEMA,
        "synthetic": True,
        "lane": "local_model",
        "candidates": candidate_rows,
    }
    args.snapshot.parent.mkdir(parents=True, exist_ok=True)
    args.snapshot.write_text(json.dumps(snapshot, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")

    report = {
        "schema": REPORT_SCHEMA,
        "authority": "public_research_evidence_only",
        "source_of_truth": False,
        "synthetic_only": True,
        "real_data_used": False,
        "private_repository_access": False,
        "network_during_inference": False,
        "automatic_winner_selected": False,
        "production_switch_authorized": False,
        "model": {"id": MODEL_ID, "revision": MODEL_REVISION, "license": MODEL_LICENSE},
        "method": "finite_choice_mean_conditional_log_likelihood",
        "class_count": len(CLASSES),
        "suite_sha256": hashlib.sha256(canonical_bytes(suite)).hexdigest(),
        "snapshot_sha256": hashlib.sha256(canonical_bytes(snapshot)).hexdigest(),
        "metrics": {
            "case_count": count,
            "document_type_accuracy": doc_hits / count,
            "category_accuracy": cat_hits / count,
            "classification_exact_accuracy": exact_hits / count,
            "matter_link_exact_accuracy": matter_hits / count,
            "high_confidence_error_count": len(high_conf_wrong),
            "wrong_case_review_capture_rate": len(review_captured) / len(wrong) if wrong else 1.0,
        },
        "runtime": {
            "model_load_seconds": round(load_seconds, 4),
            "inference_seconds": round(inference_seconds, 4),
            "seconds_per_case": round(inference_seconds / count, 4),
            "max_rss_kb": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss),
            "torch_version": torch.__version__,
        },
        "cases": result_rows,
    }
    args.report.write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2), encoding="utf-8")

    print("PANAM_AUTO_INTAKE_LOCAL_MODEL_V1=PASS")
    print("SUITE_SHA256=" + report["suite_sha256"])
    print("SNAPSHOT_SHA256=" + report["snapshot_sha256"])
    print("METRICS=" + json.dumps(report["metrics"], sort_keys=True))
    print("RUNTIME=" + json.dumps(report["runtime"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
