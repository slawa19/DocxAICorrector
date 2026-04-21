"""Analyze pyright JSON output and print summary."""
import json
import sys
from collections import Counter

r = json.load(sys.stdin)
diags = r.get("generalDiagnostics", [])
errors = [d for d in diags if d.get("severity") == "error"]

file_counts: Counter[str] = Counter()
for e in errors:
    f = e.get("file", "?").replace("/mnt/d/www/projects/2025/DocxAICorrector/", "")
    file_counts[f] += 1

print(f"Total errors: {len(errors)}")
print()
print("=== BY FILE ===")
for f, c in file_counts.most_common():
    print(f"  {c:4d}  {f}")

rule_counts: Counter[str] = Counter()
for e in errors:
    msg = e.get("message", "")
    ml = msg.lower()
    if "cannot be assigned to parameter" in ml:
        rule_counts["Type assignment incompatibility"] += 1
    elif "cannot access attribute" in ml or "is not a known attribute" in ml:
        rule_counts["Unknown attribute access"] += 1
    elif "is not iterable" in ml:
        rule_counts["Not iterable"] += 1
    elif "operator" in ml and "not supported" in ml:
        rule_counts["Unsupported operator"] += 1
    elif "is not assignable to" in ml:
        rule_counts["Type not assignable"] += 1
    elif "could be instantiated" in ml:
        rule_counts["Generic type instantiation"] += 1
    elif "missing" in ml:
        rule_counts["Missing import/module"] += 1
    elif "__getitem__" in msg or "__setitem__" in msg:
        rule_counts["Subscript/index error"] += 1
    else:
        rule_counts[msg[:80]] += 1

print()
print("=== BY CATEGORY ===")
for r2, c in rule_counts.most_common():
    print(f"  {c:4d}  {r2}")
