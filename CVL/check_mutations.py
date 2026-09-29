#!/usr/bin/env python3
"""Run an unmodified CVL baseline, then the same seven bugs as the Halmos suite.

Source files are copied into a fresh results directory. Detection requires 
FAIL for the selected property in Certora's structured output.json.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PROVER = Path.home() / "Documents/Github/others/eth/certora/CertoraProver"
MUTATIONS = [
    ("free_self_mint", '        require(msg.sender != address(this), "Depositing to self");', "",
     "depositArithmetic"),
    ("zero_recipient", '        require(recipient != address(0), "Transfer to zero address");', "",
     "noBalanceAddressZero"),
    ("missing_supply_mint", "        totalSupply += amount;", "",
     "totalSupplyEqualsAggregateBalances"),
    ("unchanged_allowance", "currentAllowance - amount", "currentAllowance",
     "transferFromArithmetic"),
    ("wrong_recipient_credit", "        balanceOf[recipient] += amount;", "        balanceOf[recipient] += 0;",
     "successfulTransferArithmetic"),
    ("missing_supply_cap", "            amount <= MAX_SUPPLY - totalSupply,", "            true,",
     "tokenSupplyCantExceedUpperCap"),
    ("withdraw_disabled", '        require(amount > 0, "Amount must be positive");', '        require(false, "disabled");',
     "withdrawalIsAlwaysPossible"),
]


def outcomes(node, path=""):
    """Flatten both plain-rule and grouped invariant results, preserving names.

    Examples: "SUCCESS", {"Initial State": "SUCCESS", "Induction Step":
    {"FAIL": ["deposit()"], "SUCCESS": ["transfer(address,uint256)"]}}.
    Sanity subchecks are excluded from output.json by this Certora build.
    """
    if isinstance(node, str):
        return [{"case": path, "status": node}]
    if not isinstance(node, dict) or not node:
        raise ValueError(f"Missing or unsupported result at {path}: {node!r}")
    result = []
    for key, value in node.items():
        if isinstance(value, list):
            if not value or not all(isinstance(case, str) for case in value):
                raise ValueError(f"Invalid grouped results at {path}/{key}")
            result.extend({"case": f"{path}/{case}", "status": key} for case in value)
        else:
            result.extend(outcomes(value, f"{path}/{key}"))
    return result


def run(command, directory, env, timeout):
    """Keep the log and stop the entire prover/solver process group on timeout."""
    with (directory / "run.log").open("w") as log:
        proc = subprocess.Popen(command, cwd=directory, env=env, stdout=log,
                                stderr=subprocess.STDOUT, start_new_session=True)
        try:
            return proc.wait(timeout=timeout), False
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
            if isinstance(error, KeyboardInterrupt):
                raise
            return proc.returncode, True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prover-root", type=Path,
                        default=Path(os.environ.get("CERTORA_PROVER_ROOT", DEFAULT_PROVER)))
    parser.add_argument("--timeout", type=int, default=600, help="Seconds per prover invocation (default: 600)")
    parser.add_argument("--only", nargs="+", choices=[m[0] for m in MUTATIONS], help="Run selected mutations after the baseline")
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    prover = args.prover_root.expanduser().resolve()
    build = prover / ".local-build"
    python = prover / ".local-venv/bin/python"
    cli = build / "certoraRun.py"
    jar = build / "emv.jar"
    for file in (python, cli, jar):
        if not file.is_file():
            parser.error(f"Local Certora file is missing: {file}; use --prover-root")

    env = os.environ.copy()
    env["CERTORA"] = str(build)
    solver_dirs = sorted((prover / ".local-tools").glob("cvc5-*/cvc5-*/bin"))
    env["PATH"] = os.pathsep.join(map(str, [build, python.parent, *solver_dirs])) + os.pathsep + env.get("PATH", "")
    for tool in ("java", "solc", "z3", "cvc5"):
        if not shutil.which(tool, path=env["PATH"]):
            parser.error(f"Missing local dependency: {tool}")

    inputs = {name: (ROOT / name).read_bytes() for name in ("ERC20.sol", "CVL/ERC20.spec", "CVL/ERC20.conf")}
    original = inputs["ERC20.sol"].decode()
    spec = inputs["CVL/ERC20.spec"].decode()
    config = json.loads(inputs["CVL/ERC20.conf"])
    properties = re.findall(r"^\s*(?:rule|invariant)\s+(\w+)\s*\(", spec, re.MULTILINE)
    if not properties:
        parser.error("No rule/invariant declarations found in CVL/ERC20.spec")
    selected = [m for m in MUTATIONS if args.only is None or m[0] in args.only]
    for name, old, _, rule in selected:
        if original.count(old) != 1 or rule not in properties:
            parser.error(f"Mutation {name} no longer matches the contract/specification")

    results = ROOT / "CVL/results/mutations"
    results.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-")
    session = Path(tempfile.mkdtemp(prefix=timestamp, dir=results))
    summary = {
        "results_directory": str(session), "prover_root": str(prover),
        "jar_sha256": hashlib.sha256(jar.read_bytes()).hexdigest(),
        "input_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in inputs.items()},
        "baseline": None, "mutations": [],
    }

    def save():
        (session / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    def verify(name, source, rules):
        dest = session / name
        dest.mkdir()
        (dest / "ERC20.sol").write_text(source)
        (dest / "ERC20.spec").write_bytes(inputs["CVL/ERC20.spec"])
        conf = dict(config)
        conf.update(files=["ERC20.sol:ERC20"], verify="ERC20:ERC20.spec", rule=rules,
                    tool_output="output.json", rule_sanity="basic", max_concurrent_rules=2,
                    java_args=["-Xmx4g -XX:ActiveProcessorCount=4"], msg=f"CVL mutation test: {name}")
        (dest / "ERC20.conf").write_text(json.dumps(conf, indent=2) + "\n")
        command = [str(python), str(cli), "ERC20.conf", "--jar", str(jar)]
        record = {"name": name, "rules": rules, "directory": str(dest), "command": command}
        print(f"{name}: RUNNING", flush=True)
        started = time.monotonic()
        code, timed_out = run(command, dest, env, args.timeout)
        record.update(exit_code=code, timed_out=timed_out, seconds=round(time.monotonic() - started, 2))
        try:
            report = json.loads((dest / "output.json").read_text())["rules"]
            record["outcomes"] = {rule: outcomes(report[rule], rule) for rule in rules}
            record["all_outcomes"] = outcomes(report)
        except (OSError, ValueError, KeyError, TypeError) as error:
            record["error"] = str(error)
        return record

    print(f"Results: {session}", flush=True)
    try:
        baseline = verify("baseline", original, properties)
        baseline["passed"] = (baseline["exit_code"] == 0 and not baseline["timed_out"]
                              and "error" not in baseline
                              and all(o["status"] == "SUCCESS" for o in baseline["all_outcomes"]))
        summary["baseline"] = baseline
        save()
        print(f'baseline: {"PASS" if baseline["passed"] else "ERROR / NOT VERIFIED"}', flush=True)
        if not baseline["passed"]:
            raise SystemExit(f"Baseline must pass first; inspect {session / 'baseline/run.log'}")

        for name, old, new, rule in selected:
            record = verify(name, original.replace(old, new), [rule])
            statuses = {o["status"] for o in record.get("outcomes", {}).get(rule, [])}
            all_statuses = {o["status"] for o in record.get("all_outcomes", [])}
            resolved = (record["exit_code"] in (0, 1) and not record["timed_out"]
                        and "error" not in record and bool(statuses)
                        and all_statuses <= {"SUCCESS", "FAIL"})
            record["detected"] = resolved and "FAIL" in statuses
            record["verdict"] = "DETECTED" if record["detected"] else ("SURVIVED" if resolved else "ERROR / INCONCLUSIVE")
            summary["mutations"].append(record)
            save()
            print(f'{name}: {record["verdict"]} ({record["seconds"]}s)', flush=True)
    finally:
        summary["original_inputs_unchanged"] = all((ROOT / name).read_bytes() == data for name, data in inputs.items())
        save()
        if not summary["original_inputs_unchanged"]:
            raise RuntimeError("Original inputs changed during the experiment; do not reuse these results")

    detected = sum(m["detected"] for m in summary["mutations"])
    print(f"Detected {detected}/{len(selected)} mutations. Summary: {session / 'summary.json'}", flush=True)
    return 0 if detected == len(selected) else 1


if __name__ == "__main__":
    raise SystemExit(main())
