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
// Note: This function requires enabling `optimistic_fallback` in the conf file (it is fine to disable havoc because the calldata of transfers is empty)
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
