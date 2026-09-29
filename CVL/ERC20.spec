methods {
    // Note: even though a variable might be 'public' in solidity we have to use 'external' here
    function balanceOf(address) external returns (uint256) envfree;
    function allowance(address, address) external returns (uint256) envfree;
    function totalSupply() external returns (uint256) envfree;
    function MAX_SUPPLY() external returns (uint256) envfree;
}

/// @notice Sum of every entry in the unbounded balanceOf mapping
ghost mathint aggregateTokenBalances {
    init_state axiom aggregateTokenBalances == 0;
}

/// @notice Keep the aggregate in sync whenever any account balance is written
hook Sstore balanceOf[KEY address account] uint256 newBalance (uint256 oldBalance) {
    aggregateTokenBalances = aggregateTokenBalances + newBalance - oldBalance;
}

/// @title totalSupply is exactly the sum of all account token balances
invariant totalSupplyEqualsAggregateBalances()
    totalSupply() == aggregateTokenBalances;

/// @title Address zero has no balance
invariant noBalanceAddressZero()
    balanceOf(0) == 0;

/// @title Total supply not greater than ETH balance
// Exact equality is intentionally not required (selfdestruct can force ETH into the contract without minting tokens
invariant tokenSolvency()
    nativeBalances[currentContract] >= totalSupply();

/// @title Successful transfers subtract and add correct amounts
rule successfulTransferArithmetic(env e) {
    // sender is e.msg.sender
    address recipient;
    uint256 amount;

    require e.msg.sender != recipient;

    // pre-state
    uint256 senderBalanceBefore = balanceOf(e.msg.sender);
    uint256 recipientBalanceBefore = balanceOf(recipient);

    // cmon do sth
    transfer(e, recipient, amount);

    // post-state assertions
    assert (
        balanceOf(e.msg.sender) == senderBalanceBefore - amount,
        "Balance was not correctly subtracted from sender"
    );

    assert (
        balanceOf(recipient) == recipientBalanceBefore + amount,
        "Balance was not correctly added to recipient"
    );

}

/// @title Successful transfers preserve totalSupply and the ETH reserve
// Why not use invariant that those two are equal? because u can externally force eth reserve increase (e.g. via selfdestruct) without minting
rule successfulTransferPreservesSupplyAndETHReserves(env e) {
    address recipient;
    uint256 amount;

    uint256 totalSupplyBefore = totalSupply();
    uint256 ethReservesBefore = nativeBalances[currentContract];

    transfer(e, recipient, amount);

    // sending someone tokens does not affect total token supply
    assert totalSupply() == totalSupplyBefore,
        "Transfer unexpectedly changed totalSupply";

    // sending someone tokens does not affect ETH reserves of contract
    assert nativeBalances[currentContract] == ethReservesBefore,
        "Transfer unexpectedly changed the contract's ETH reserve";
}

/// @title Total token supply can never exceed MAX_SUPPLY
invariant tokenSupplyCantExceedUpperCap()
    totalSupply() <= MAX_SUPPLY();

/// @title transferFrom arithmetic is sane
rule transferFromArithmetic(env e) {
    address from;
    address recipient;
    uint256 amount;

    uint256 fromAllowanceBefore = allowance(from, e.msg.sender);
    uint256 fromBalanceBefore = balanceOf(from);
    uint256 recipientBalanceBefore = balanceOf(recipient);

    transferFrom(e, from, recipient, amount);

    assert (
        allowance(from, e.msg.sender) == fromAllowanceBefore - amount,
        "Allowance did not decrease by expected amount"
    );

    // since self-approvals are allowed we have to handle the case where the balance does not change
    if (from == recipient) {
        assert (
            balanceOf(from) == fromBalanceBefore,
            "Self-transfer unexpectedly changed the balance"
        );
    } else {
        assert (
            balanceOf(from) == fromBalanceBefore - amount,
            "'from' balance did not decrease by expected amount"
        );

        assert (
            balanceOf(recipient) == recipientBalanceBefore + amount,
            "Recipient balance did not increase by expected amount"
        );
    }
}

/// @title Spending more than cleared allowance is impossible
rule spendingMoreThanAllowanceIsImpossible(env e) {
    address from;
    address recipient;
    uint256 amount;

    uint256 fromAllowance = allowance(from, e.msg.sender);

    // only consider impossible actions and ensure they revert
    require amount > fromAllowance;
    transferFrom@withrevert(e, from, recipient, amount);
    assert lastReverted, "Spending exceeded allowance";
}

/// @title Deposited ETH increases total ETH locked into contract by exact expected amount, and also sender token balance by exact intended amount
rule depositArithmetic(env e) {
    uint256 contractNativeBalanceBefore = nativeBalances[currentContract];  // native eth locked in contract
    uint256 senderTokenBalanceBefore = balanceOf(e.msg.sender);             // owned user tokens

    deposit(e);

    assert (
        contractNativeBalanceBefore + e.msg.value == nativeBalances[currentContract],
        "Locked ETH did not increase by expected amount"
    );

    assert (
        senderTokenBalanceBefore + e.msg.value == balanceOf(e.msg.sender),
        "Tokens owned by sender did not increase by expected amount"
    );
}

/// @title Sender ETH balance increases correctly, native eth locked in contract decreases correctly, sender token balance is decreased correctly
// Note: this rule models EOAs with optimistic_fallback; callback safety is checked separately in Callbacks.spec
// TODO: can you construct an adversarial 7702 receiver that creates issues?
rule eoaWithdrawalArithmetic(env e) {
    // sender is not using 7702 account abstraction (this allows us to check for resulting eth balance of sender)
    require nativeCodesize[e.msg.sender] == 0;

    uint256 contractNativeBalanceBefore = nativeBalances[currentContract];
    uint256 senderNativeBalanceBefore = nativeBalances[e.msg.sender];
    uint256 senderTokenBalanceBefore = balanceOf(e.msg.sender);
    uint256 totalSupplyBefore = totalSupply();
    uint256 amount;

    withdraw(e, amount);

    assert (
        contractNativeBalanceBefore - amount == nativeBalances[currentContract],
        "Locked ETH decreased by unexpected amount"
    );

    assert (
        senderNativeBalanceBefore + amount == nativeBalances[e.msg.sender],
        "Sender ETH balance increased by unexpected amount"
    );

    assert (
        senderTokenBalanceBefore - amount == balanceOf(e.msg.sender),
        "Sender token balance decreased by unexpected amount"
    );

    assert (
        totalSupplyBefore - amount == totalSupply(),
        "Total token supply decreased by unexpected amount"
    );

}

/// @title Any non-zero token balance can be withdrawn
rule withdrawalIsAlwaysPossible(env e) {
    uint256 amount;

    // surprising amount of require statements required to make this work
    require e.msg.value == 0; // withdraw() is not payable
    require amount > 0;
    require amount <= balanceOf(e.msg.sender);
    require amount <= totalSupply();
    require amount <= nativeBalances[currentContract];
    require nativeCodesize[e.msg.sender] == 0;
    require amount <= max_uint256 - nativeBalances[e.msg.sender]; // avoid eth balance overflow, edge-case where v tries to withdraw

    withdraw@withrevert(e, amount);

    assert !lastReverted, "Withdrawal unexpectedly reverted";
}

// approval is an overwrite, including zero revocation, not an increment
/// @title Approval overwrites exactly one allowance and leaves other state unchanged
rule approvalCorrectAndIsolated(env e, address spender, uint256 amount, address owner, address otherSpender, address holder) {
    require e.msg.value == 0;
    uint256 unrelated = allowance(owner, otherSpender);
    uint256 balance = balanceOf(holder);
    uint256 supply = totalSupply();
    uint256 reserves = nativeBalances[currentContract];
    bool result = approve@withrevert(e, spender, amount);
    assert !lastReverted && result;
    assert allowance(e.msg.sender, spender) == amount;
    assert (owner != e.msg.sender || otherSpender != spender) => allowance(owner, otherSpender) == unrelated;
    assert balanceOf(holder) == balance;
    assert totalSupply() == supply && nativeBalances[currentContract] == reserves;
}

// only approve(owner, spender) and spending that exact pair may change it
/// @title Operations preserve every unrelated allowance
rule unrelatedAllowancesUnchanged(env e, uint8 action, address from, address to, uint256 amount, address owner, address spender) {
    require action < 5;
    uint256 before = allowance(owner, spender);
    if (action == 0) {
        transfer(e, to, amount);
    } else if (action == 1) {
        require owner != from || spender != e.msg.sender;
        transferFrom(e, from, to, amount);
    } else if (action == 2) {
        require owner != e.msg.sender || spender != to;
        approve(e, to, amount);
    } else if (action == 3) {
        deposit(e);
    } else {
        require nativeCodesize[e.msg.sender] == 0;
        withdraw(e, amount);
    }
    assert allowance(owner, spender) == before;
}

/// @title A valid transfer succeeds, including zero amounts and self-transfers
rule validTransferSucceeds(env e, address to, uint256 amount) {
    require e.msg.value == 0;
    require to != 0;
    require amount <= balanceOf(e.msg.sender);
    require to == e.msg.sender || balanceOf(to) <= max_uint256 - amount;
    bool result = transfer@withrevert(e, to, amount);
    assert !lastReverted && result;
}

/// @title A funded and authorized transferFrom succeeds
rule validTransferFromSucceeds(env e, address from, address to, uint256 amount) {
    require e.msg.value == 0;
    require to != 0;
    require amount <= balanceOf(from);
    require amount <= allowance(from, e.msg.sender);
    require to == from || balanceOf(to) <= max_uint256 - amount;
    bool result = transferFrom@withrevert(e, from, to, amount);
    assert !lastReverted && result;
}

/// @title A funded deposit within the cap succeeds
rule validDepositSucceeds(env e) {
    require e.msg.sender != 0 && e.msg.sender != currentContract;
    require e.msg.value > 0;
    require totalSupply() <= MAX_SUPPLY();
    require e.msg.value <= MAX_SUPPLY() - totalSupply();
    require balanceOf(e.msg.sender) <= max_uint256 - e.msg.value;
    require nativeBalances[e.msg.sender] >= e.msg.value;
    require nativeBalances[currentContract] <= max_uint256 - e.msg.value;
    deposit@withrevert(e);
    assert !lastReverted;
}

/// @title Successful ERC20 calls return true
rule successfulCallsReturnTrue(env e, uint8 action, address from, address to, uint256 amount) {
    require action < 3;
    bool result;
    if (action == 0) result = transfer(e, to, amount);
    else if (action == 1) result = transferFrom(e, from, to, amount);
    else result = approve(e, to, amount);
    assert result;
}

/// @title Rejected transferFrom calls restore allowances and balances
rule failedTransferFromRollsBack(env e, address from, address to, uint256 amount, address owner, address spender, address holder) {
    require e.msg.value == 0;
    require to == 0 || amount > balanceOf(from) || amount > allowance(from, e.msg.sender);
    uint256 oldAllowance = allowance(owner, spender);
    uint256 oldBalance = balanceOf(holder);
    uint256 oldSupply = totalSupply();
    uint256 oldReserves = nativeBalances[currentContract];
    transferFrom@withrevert(e, from, to, amount);
    assert lastReverted;
    assert allowance(owner, spender) == oldAllowance && balanceOf(holder) == oldBalance;
    assert totalSupply() == oldSupply && nativeBalances[currentContract] == oldReserves;
}

// explicit self-transfer semantics
/// @title A successful self-transfer preserves its balance
rule selfTransferPreservesBalance(env e, uint256 amount) {
    uint256 before = balanceOf(e.msg.sender);
    bool result = transfer(e, e.msg.sender, amount);
    assert result && balanceOf(e.msg.sender) == before;
}

// typed event hooks inspect the actual emitted topics and data
ghost mathint transferEvents;
ghost mathint approvalEvents;
ghost address transferFromEvent;
ghost address transferToEvent;
ghost uint256 transferAmountEvent;
ghost address approvalOwnerEvent;
ghost address approvalSpenderEvent;
ghost uint256 approvalAmountEvent;
ghost mathint transferPosition;
ghost mathint approvalPosition;

hook event Transfer(address indexed from, address indexed to, uint256 amount) {
    transferEvents = transferEvents + 1;
    transferPosition = transferEvents + approvalEvents;
    transferFromEvent = from;
    transferToEvent = to;
    transferAmountEvent = amount;
}
hook event Approval(address indexed owner, address indexed spender, uint256 amount) {
    approvalEvents = approvalEvents + 1;
    approvalPosition = transferEvents + approvalEvents;
    approvalOwnerEvent = owner;
    approvalSpenderEvent = spender;
    approvalAmountEvent = amount;
}

/// @title Successful operations emit the expected event arguments, counts, and order
rule operationEvents(env e, uint8 action, address from, address to, uint256 amount) {
    require action < 5;
    transferEvents = 0;
    approvalEvents = 0;
    uint256 oldAllowance = allowance(from, e.msg.sender);
    if (action == 0) transfer(e, to, amount);
    else if (action == 1) transferFrom(e, from, to, amount);
    else if (action == 2) approve(e, to, amount);
    else if (action == 3) deposit(e);
    else {
        require nativeCodesize[e.msg.sender] == 0;
        withdraw(e, amount);
    }
    assert transferEvents == (action == 2 ? 0 : 1);
    if (action != 2) {
        assert transferFromEvent == (action == 3 ? 0 : (action == 1 ? from : e.msg.sender));
        assert transferToEvent == (action == 4 ? 0 : (action == 3 ? e.msg.sender : to));
        assert transferAmountEvent == (action == 3 ? e.msg.value : amount);
        assert transferPosition == (action == 1 ? 2 : 1);
    }
    if (action == 1 || action == 2) {
        assert approvalOwnerEvent == (action == 1 ? from : e.msg.sender);
        assert approvalSpenderEvent == (action == 1 ? e.msg.sender : to);
        assert approvalAmountEvent == (action == 1 ? oldAllowance - amount : amount);
        assert approvalPosition == 1;
    }
    assert approvalEvents == (action == 1 || action == 2 ? 1 : 0);
}
