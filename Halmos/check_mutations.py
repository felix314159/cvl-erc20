#!/usr/bin/env python3
"""Check that deliberate ERC20 bugs produce Halmos assertion counterexamples.

Each experiment uses an isolated copy under ignored Halmos/results/mutations.
"""
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
MUTATIONS = [
    ("free_self_mint", '        require(msg.sender != address(this), "Depositing to self");', "",
     "ERC20Rules", "check_depositArithmetic"),
    ("zero_recipient", '        require(recipient != address(0), "Transfer to zero address");', "",
     "ERC20Induction", "check_noBalanceAddressZero"),
    ("missing_supply_mint", "        totalSupply += amount;", "",
     "ERC20Induction", "check_totalSupplyEqualsAggregateBalances"),
    ("unchanged_allowance", "currentAllowance - amount", "currentAllowance",
     "ERC20Rules", "check_transferFromArithmetic"),
    ("wrong_recipient_credit", "        balanceOf[recipient] += amount;", "        balanceOf[recipient] += 0;",
     "ERC20Rules", "check_successfulTransferArithmetic"),
    ("missing_supply_cap", "            amount <= MAX_SUPPLY - totalSupply,", "            true,",
     "ERC20Induction", "check_tokenSupplyCantExceedUpperCap"),
    ("withdraw_disabled", '        require(amount > 0, "Amount must be positive");', '        require(false, "disabled");',
     "ERC20Rules", "check_withdrawalIsAlwaysPossible"),
]


def main():
    original = (ROOT / "ERC20.sol").read_text()
    summary = []
    for name, old, new, contract, function in MUTATIONS:
        assert original.count(old) == 1, f"Mutation no longer matches: {name}"
        dest = ROOT / "Halmos/results/mutations" / name
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copytree(ROOT / "Halmos/test", dest / "Halmos/test", dirs_exist_ok=True)
        (dest / "Halmos/src").mkdir(exist_ok=True)
        for config in ("foundry.toml", "halmos.toml"):
            shutil.copy2(ROOT / config, dest / config)
        (dest / "ERC20.sol").write_text(original.replace(old, new))
        output = dest / "result.json"
        output.unlink(missing_ok=True)
        command = ["halmos", "--root", str(dest), "--contract", contract,
                   "--function", function, "--no-status", "--json-output", str(output)]
        with (dest / "run.log").open("w") as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=300)
        log = (dest / "run.log").read_text()
        detected = result.returncode != 0 and "Counterexample" in log and "[FAIL]" in log
        summary.append({"mutation": name, "detected": detected, "exit_code": result.returncode})
        print(f'{name}: {"DETECTED" if detected else "NOT DETECTED"}', flush=True)
        if not detected:
            print(log, flush=True)
    assert (ROOT / "ERC20.sol").read_text() == original
    (ROOT / "Halmos/results/mutations/summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    if not all(item["detected"] for item in summary):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
