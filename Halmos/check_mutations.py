#!/usr/bin/env python3
"""Verify the baseline, then require a Halmos counterexample for each shared mutant."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cvl_mutations", ROOT / "CVL/check_mutations.py")
cvl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cvl)

CONTRACTS = {
    "noBalanceAddressZero": "ERC20Induction",
    "totalSupplyEqualsAggregateBalances": "ERC20Induction",
    "tokenSupplyCantExceedUpperCap": "ERC20Induction",
    "depositArithmetic": "ERC20Rules",
    "transferFromArithmetic": "ERC20Rules",
    "successfulTransferArithmetic": "ERC20Rules",
    "withdrawalIsAlwaysPossible": "ERC20Rules",
    "rejectingWithdrawalRollsBack": "ERC20ReceiverRules",
    "reentrantWithdrawal": "ERC20ReceiverRules",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="+", choices=[m[0] for m in cvl.MUTATIONS])
    args = parser.parse_args()
    names = ["ERC20.sol", "foundry.toml", "halmos.toml", "verification/Receivers.sol",
             "Halmos/verify.py", "Halmos/log_adapter.py",
             *[str(p.relative_to(ROOT)) for p in (ROOT / "Halmos/test").glob("*.sol")]]
    inputs = {name: (ROOT / name).read_bytes() for name in names}
    original = inputs["ERC20.sol"].decode()
    selected = [m for m in cvl.MUTATIONS if args.only is None or m[0] in args.only]
    base = ROOT / "Halmos/results/mutations"
    base.mkdir(parents=True, exist_ok=True)
    session = Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-"), dir=base))
    summary = {"input_sha256": {n: hashlib.sha256(v).hexdigest() for n, v in inputs.items()}, "mutations": []}

    def save():
        (session / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    def verify(name, source, rule=None):
        dest = session / name
        dest.mkdir()
        for filename, content in inputs.items():
            target = dest / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        (dest / "Halmos/src").mkdir()
        (dest / "ERC20.sol").write_text(source)
        command = [sys.executable, str(dest / "Halmos/verify.py"), "--root", str(dest),
                   "--no-status", "--json-output", str(dest / "result.json")]
        if rule:
            command += ["--contract", CONTRACTS.get(rule, "ERC20ExtendedRules"), "--function", f"check_{rule}\\("]
        print(f"{name}: RUNNING", flush=True)
        code, timeout = cvl.run(command, dest, os.environ.copy(), 300)
        record = {"name": name, "directory": str(dest), "exit_code": code, "timeout": timeout}
        try:
            result = json.loads((dest / "result.json").read_text())
            cases = [case for contract in result["test_results"].values() for case in contract]
            if not cases:
                raise ValueError("No checks executed")
            if rule and (len(cases) != 1 or not cases[0]["name"].startswith(f"check_{rule}(")):
                raise ValueError("Selected check did not execute exactly once")
            record["cases"] = cases
            record["passed"] = code == 0 and not timeout and all(
                c["exitcode"] == 0 and c["num_bounded_loops"] == 0 and c["num_paths"][1] > 0 for c in cases)
            record["detected"] = code == 1 and not timeout and all(
                c["exitcode"] == 1 and c["num_models"] > 0 and c["num_bounded_loops"] == 0 for c in cases)
        except (OSError, ValueError, KeyError, TypeError) as error:
            record.update(passed=False, detected=False, error=str(error))
        return record

    print(f"Results: {session}", flush=True)
    try:
        summary["baseline"] = verify("baseline", original)
        save()
        if not summary["baseline"]["passed"]:
            raise SystemExit(f"Baseline failed; inspect {session / 'baseline/run.log'}")
        print(f"baseline: PASS ({len(summary['baseline']['cases'])} checks)", flush=True)
        for name, old, new, rule in selected:
            if original.count(old) != 1:
                raise ValueError(f"Mutation no longer matches: {name}")
            record = verify(name, cvl.mutated_source(original, name, old, new), rule)
            summary["mutations"].append(record)
            save()
            print(f'{name}: {"DETECTED" if record["detected"] else "NOT DETECTED / ERROR"}', flush=True)
    finally:
        summary["original_inputs_unchanged"] = all((ROOT / n).read_bytes() == v for n, v in inputs.items())
        save()
        if not summary["original_inputs_unchanged"]:
            raise RuntimeError("Proof inputs changed during the experiment; do not reuse these results")
    detected = sum(r["detected"] for r in summary["mutations"])
    print(f"Detected {detected}/{len(selected)} mutations. Summary: {session / 'summary.json'}")
    return 0 if detected == len(selected) else 1


if __name__ == "__main__":
    raise SystemExit(main())
