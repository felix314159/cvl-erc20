# ERC20 Formal Verification

The properties of [`ERC20.sol`](ERC20.sol) are checked with [CVL](CVL/ERC20.spec) (Certora) and [Halmos](Halmos/test).

| Area | Cases covered |
| --- | --- |
| Accounting | Initial state, total supply equals the sum of balances, ETH solvency, supply cap, zero-address balance stays zero |
| Transfers | Exact balance changes, self-transfers, zero amounts, allowance consumption, rejection of overspending, unchanged supply and reserves |
| Approvals | Exact overwrite and zero-value revocation, preservation of unrelated allowances, no balance/supply/ETH effects |
| Deposits and withdrawals | Token/ETH arithmetic, valid deposits and EOA withdrawals succeed, valid transfers and approvals succeed |
| Rollback | Rejected `transferFrom` restores balances and allowances; rejected ETH delivery restores token claims, supply, and ETH |
| Callbacks | Accounting before ETH callbacks. Nested operations preserve accounting and cannot spend an unapproved victim's tokens. Successful nested-withdrawal witness |
| Return values and events | Successful ERC20 calls return `true`. Transfer/Approval payloads, counts, and order, including mint/burn and zero-value events |

CVL's [strong invariants](CVL/Callbacks.spec) check accounting across arbitrary callbacks. Both tools also execute a concrete receiver with **one nested operation**, chosen from all five entrypoints:

* `transfer(address recipient, uint256 amount)`
* `transferFrom(address sender, address recipient, uint256 amount)`
* `approve(address spender, uint256 amount)`
* `deposit()`
* `withdraw(uint256 amount)`
