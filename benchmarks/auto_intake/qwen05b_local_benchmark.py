#!/usr/bin/env python3
"""Public-safe local-model benchmark for PANAM Auto Intake.

Uses deterministic single-token multiple-choice scoring over a fixed class set.
No free-form category generation and no private PANAM data.
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
METHOD = "single_token_multiple_choice_log_probability"

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
LABELS = list("ABCDEFGHIJKLM")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def class_text(item: tuple[str, str, str | None]) -> str:
    doc, category, subcategory = item
    payload: dict[str, Any] = {"document_type": doc, "category": category}
    if subcategory is not None:
        payload["subcategory"] = subcategory
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def build_prompt(case: dict[str, Any]) -> str:
    allowed = "\n".join(f"{label}: {class_text(item)}" for label, item in zip(LABELS, CLASSES))
    return (
        "Классифицируй синтетический юридический документ. Выбери РОВНО одну метку A–M из списка ниже. "
        "Не создавай новый класс и не объясняй ответ.\n\n"
        f"Имя файла: {case['original_filename']}\n"
        f"Структурированные факты: {json.dumps(case['structured_facts'], ensure_ascii=False, sort_keys=True)}\n"
        f"Синтетическая смысловая подсказка: {case['semantic_hint']}\n\n"
        f"Классы:\n{allowed}\n\n"
        "Ответ: только одна латинская буква A–M.\nОтвет:"
    )


def softmax_logits(values: list[float]) -> list[float]:
    peak = max(values)
    exps = [math.exp(v - peak) for v in values]
    total = sum(exps)
    return [v / total for v in exps]


def exact_class(selected: tuple[str, str, str | None], gold: dict[str, Any]) -> bool:
    doc, cat, sub = selected
    return doc == gold.get("document_type") and cat == gold.get("category") and sub == gold.get("subcategory")


def candidate_for(case: dict[str, Any], selected: tuple[str, str, str | None], confidence: float) -> dict[str, Any]:
    doc, cat, sub = selected
    candidate: dict[str, Any] = {
        "schema": "panam.intake-classification-candidate.v1",
        "source_ref": case["source_ref"],
        "source_sha256": case["source_sha256"],
        "original_filename": case["original_filename"],
        "document_type": doc,
        "category": cat,
        "confidence": round(float(confidence), 8),
        "rationale": "Synthetic local-model fixed-class multiple-choice benchmark; human review remains required.",
        "evidence_refs": [
            f"fixture:auto-intake:{case['id']}:filename",
            f"fixture:auto-intake:{case['id']}:facts",
            f"fixture:auto-intake:{case['id']}:semantic",
        ],
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

    label_token_ids: list[int] = []
    for label in LABELS:
        ids = tokenizer(label, add_special_tokens=False)["input_ids"]
        if len(ids) != 1:
            raise SystemExit(f"label {label} is not a single tokenizer token: {ids}")
        label_token_ids.append(ids[0])
    if len(set(label_token_ids)) != len(label_token_ids):
        raise SystemExit("label token ids are not unique")

    candidate_rows: list[dict[str, Any]] = []
    result_rows: list[dict[str, Any]] = []
    inference_started = time.perf_counter()

    with torch.no_grad():
        for case in cases:
            messages = [
                {"role": "system", "content": "Ты классификатор синтетических юридических документов. Верни только метку допустимого класса."},
                {"role": "user", "content": build_prompt(case)},
            ]
            prompt_ids = tokenizer.apply_chat_template(
                messages,
                add_generation_prompt=True,
                tokenize=True,
                return_tensors="pt",
            )
            logits = model(input_ids=prompt_ids, use_cache=False).logits[0, -1].float()
            class_logits = [float(logits[token_id]) for token_id in label_token_ids]
            probs = softmax_logits(class_logits)
            selected_index = max(range(len(CLASSES)), key=lambda i: class_logits[i])
            selected = CLASSES[selected_index]
            confidence = probs[selected_index]
            candidate = candidate_for(case, selected, confidence)
            candidate_rows.append({"case_id": case["id"], "candidate": candidate})

            gold = case["gold"]
            doc_hit = selected[0] == gold.get("document_type")
            cat_hit = selected[1] == gold.get("category")
            exact_hit = exact_class(selected, gold)
            matter_hit = candidate.get("related_matter_candidate") == gold.get("related_matter_candidate")
            order = sorted(range(len(CLASSES)), key=lambda j: class_logits[j], reverse=True)
            result_rows.append({
                "case_id": case["id"],
                "selected_label": LABELS[selected_index],
                "selected_class_index": selected_index,
                "selected": {"document_type": selected[0], "category": selected[1], "subcategory": selected[2]},
                "confidence": round(float(confidence), 8),
                "document_type_hit": doc_hit,
                "category_hit": cat_hit,
                "classification_exact": exact_hit,
                "matter_link_exact": matter_hit,
                "top3": [
                    {"label": LABELS[i], "class_index": i, "probability": round(float(probs[i]), 8)}
                    for i in order[:3]
                ],
            })

    inference_seconds = time.perf_counter() - inference_started
    count = len(cases)
    doc_hits = sum(int(r["document_type_hit"]) for r in result_rows)
    cat_hits = sum(int(r["category_hit"]) for r in result_rows)
    exact_hits = sum(int(r["classification_exact"]) for r in result_rows)
    matter_hits = sum(int(r["matter_link_exact"]) for r in result_rows)
    wrong = [r for r in result_rows if not r["classification_exact"]]
    high_conf_wrong = [r for r in wrong if r["confidence"] >= 0.85]
    review_captured = [r for r in wrong if r["confidence"] < 0.85]

    snapshot = {"schema": SNAPSHOT_SCHEMA, "synthetic": True, "lane": "local_model", "candidates": candidate_rows}
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
        "method": METHOD,
        "class_count": len(CLASSES),
        "label_token_ids": dict(zip(LABELS, label_token_ids)),
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
    print("METHOD=" + METHOD)
    print("SUITE_SHA256=" + report["suite_sha256"])
    print("SNAPSHOT_SHA256=" + report["snapshot_sha256"])
    print("METRICS=" + json.dumps(report["metrics"], sort_keys=True))
    print("RUNTIME=" + json.dumps(report["runtime"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
