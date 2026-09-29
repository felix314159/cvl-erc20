#!/usr/bin/env python3
"""Run the local CVL suites in an isolated copy, preserving reports under results."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import tempfile

from check_mutations import DEFAULT_PROVER, ROOT, outcomes, run

SUITES = {"main": "ERC20", "callbacks": "Callbacks", "receivers": "Receivers"}


def verify(prover, session, suite, rules=None, source=None):
    dest = session / suite
    dest.mkdir()
    (dest / "ERC20.sol").write_text(source if source is not None else (ROOT / "ERC20.sol").read_text())
    shutil.copytree(ROOT / "verification", dest / "verification")
    (dest / "CVL").mkdir()
    for spec in (ROOT / "CVL").glob("*.spec"):
        shutil.copy2(spec, dest / "CVL" / spec.name)
    conf = json.loads((ROOT / "CVL" / f"{SUITES[suite]}.conf").read_text())
    conf.update(tool_output="output.json", rule_sanity="basic", max_concurrent_rules=2,
                java_args=["-Xmx4g -XX:ActiveProcessorCount=4"])
    if rules:
        conf["rule"] = rules
    (dest / "run.conf").write_text(json.dumps(conf, indent=2) + "\n")
    env = os.environ.copy()
    env["CERTORA"] = str(prover / ".local-build")
    env["CERTORA_DISABLE_POPUP"] = "1"
    bins = [prover / ".local-build", *sorted((prover / ".local-tools").glob("cvc5-*/cvc5-*/bin"))]
    env["PATH"] = os.pathsep.join(map(str, bins)) + os.pathsep + env.get("PATH", "")
    command = [str(prover / ".local-venv/bin/python"), str(prover / ".local-build/certoraRun.py"),
               "run.conf", "--jar", str(prover / ".local-build/emv.jar")]
    print(f"{suite}: RUNNING ({dest})", flush=True)
    code, timeout = run(command, dest, env, 600)
    record = {"suite": suite, "directory": str(dest), "exit_code": code, "timeout": timeout, "command": command}
    try:
        data = json.loads((dest / "output.json").read_text())["rules"]
        record["outcomes"] = outcomes(data)
        record["passed"] = code == 0 and not timeout and all(o["status"] == "SUCCESS" for o in record["outcomes"])
    except (OSError, ValueError, KeyError) as error:
        record.update(passed=False, error=str(error))
    print(f'{suite}: {"PASS" if record["passed"] else "FAIL / ERROR"}', flush=True)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prover-root", type=Path, default=Path(os.environ.get("CERTORA_PROVER_ROOT", DEFAULT_PROVER)))
    parser.add_argument("--suite", choices=[*SUITES, "all"], default="all")
    parser.add_argument("--rule", nargs="+")
    args = parser.parse_args()
    base = ROOT / "CVL/results"
    base.mkdir(exist_ok=True)
    session = Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime("verify-%Y%m%dT%H%M%SZ-"), dir=base))
    results = []
    for suite in SUITES if args.suite == "all" else [args.suite]:
        results.append(verify(args.prover_root.resolve(), session, suite, args.rule))
        (session / "summary.json").write_text(json.dumps(results, indent=2) + "\n")
    print(f"Summary: {session / 'summary.json'}")
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
