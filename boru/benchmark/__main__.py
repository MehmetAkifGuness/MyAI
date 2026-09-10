import argparse
import json
from pathlib import Path
from uuid import uuid4

from boru.benchmark.cases import catalog
from boru.benchmark.runner import CodingBenchmark
from boru.ollama_model import OllamaChatModel
from boru.sandbox import DockerSandboxExecutor


def main():
    parser = argparse.ArgumentParser(description="Börü bağımsız kodlama/model karşılaştırması")
    parser.add_argument("--list", action="store_true")
    parser.add_argument('--suite', choices=('basic', 'repo'), default='basic')
    parser.add_argument("--model", action="append", help="Ollama model adı; karşılaştırma için tekrarlayın")
    parser.add_argument("--fallback-model", help="Başarısız ana model sonucunda kullanılacak Ollama modeli")
    parser.add_argument("--case", action="append", help="Yalnızca belirtilen görev kimliği")
    parser.add_argument("--limit", type=int, default=3)
    parser.add_argument("--repeats", type=int, choices=range(1, 4), default=1)
    parser.add_argument("--budget-seconds", type=int, default=1800)
    parser.add_argument("--repair-attempts", type=int, choices=(0, 1), default=1)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    cases = catalog(args.suite)
    if args.list:
        for case in cases:
            print(f"{case.identifier}: [{case.category}] {case.prompt}")
        return
    if not args.model or not 1 <= args.limit <= 30 or not 0 < args.budget_seconds <= 7200:
        parser.error("--model gerekli; limit 1-30, süre 1-7200 olmalı.")
    if args.case:
        if set(args.case) - {case.identifier for case in cases}:
            parser.error("Bilinmeyen görev kimliği.")
        cases = tuple(case for case in cases if case.identifier in args.case)
    cases = cases[:args.limit]
    if args.output and args.output.exists():
        parser.error("Rapor dosyası zaten var; farklı bir yol seçin.")
    models = {name: OllamaChatModel(name, structured_timeout_seconds=180, structured_num_predict=2048,
                                  structured_thinking=False if name.startswith('qwen3') else None)
              for name in dict.fromkeys(args.model)}
    fallback_model = (
        (args.fallback_model, OllamaChatModel(
            args.fallback_model, structured_timeout_seconds=180, structured_num_predict=2048,
            structured_thinking=False if args.fallback_model.startswith('qwen3') else None,
        ))
        if args.fallback_model else None
    )
    report = CodingBenchmark(DockerSandboxExecutor, repair_attempts=args.repair_attempts).run(
        models, cases, repeats=args.repeats, budget_seconds=args.budget_seconds,
        fallback_model=fallback_model)
    output = args.output or Path("data/benchmarks") / (uuid4().hex + ".json")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Durum: {report['state']}; rapor: {output}")


if __name__ == "__main__":
    main()
