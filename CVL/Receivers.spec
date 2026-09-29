using RejectingReceiver as rejecting;
using ReentrantReceiver as receiver;

methods {
    function balanceOf(address) external returns (uint256) envfree;
    function allowance(address, address) external returns (uint256) envfree;
    function totalSupply() external returns (uint256) envfree;
    function MAX_SUPPLY() external returns (uint256) envfree;
    function receiver.configure(uint8, address, address, uint256) external envfree;
    function receiver.entrySupply() external returns (uint256) envfree;
    function receiver.entryReserves() external returns (uint256) envfree;
    function receiver.entryTokens() external returns (uint256) envfree;
    function receiver.callbacks() external returns (uint256) envfree;
    function receiver.nestedSuccess() external returns (bool) envfree;
}

/// @title Failed ETH delivery preserves every token claim and allowance
rule rejectingWithdrawalRollsBack(env e, uint256 amount, address holder, address owner, address spender) {
    require e.msg.value == 0;
    require amount > 0 && amount <= balanceOf(rejecting);
    require amount <= totalSupply() && amount <= nativeBalances[currentContract];
    require amount <= max_uint256 - nativeBalances[rejecting];
    uint256 balance = balanceOf(holder);
    uint256 approval = allowance(owner, spender);
    uint256 supply = totalSupply();
    uint256 reserves = nativeBalances[currentContract];
    uint256 receiverETH = nativeBalances[rejecting];
    rejecting.withdraw@withrevert(e, amount);
    assert lastReverted;
    assert balanceOf(holder) == balance && allowance(owner, spender) == approval;
    assert totalSupply() == supply && nativeBalances[currentContract] == reserves;
    assert nativeBalances[rejecting] == receiverETH;
}

/// @title Effects precede the callback, which cannot spend an unapproved victim's tokens
rule reentrantWithdrawal(env e, uint8 action, address from, address to, uint256 nestedAmount, uint256 amount, address victim) {
    require e.msg.value == 0 && action < 5;
    require victim != receiver && victim != currentContract;
    require allowance(victim, receiver) == 0;
    require amount > 0 && amount <= balanceOf(receiver);
    require amount <= totalSupply() && amount <= nativeBalances[currentContract];
    require totalSupply() <= MAX_SUPPLY();
    require nativeBalances[currentContract] >= totalSupply();
    require amount <= max_uint256 - nativeBalances[receiver];
    // ensure even the nested deposit has sufficient native funds for the call
    require action != 3 || nestedAmount <= nativeBalances[receiver] + amount;
    uint256 victimBalance = balanceOf(victim);
    uint256 supply = totalSupply();
    uint256 reserves = nativeBalances[currentContract];
    uint256 balance = balanceOf(receiver);
    receiver.configure(action, from, to, nestedAmount);
    receiver.withdraw@withrevert(e, amount);
    assert !lastReverted;
    assert receiver.callbacks() == 1;
    assert receiver.entrySupply() == supply - amount;
    assert receiver.entryReserves() == reserves - amount;
    assert receiver.entryTokens() == balance - amount;
    assert balanceOf(victim) >= victimBalance;
    assert totalSupply() <= MAX_SUPPLY();
    assert nativeBalances[currentContract] >= totalSupply();
}

/// @title The receiver model actually reaches a successful nested withdrawal
rule nestedWithdrawalWitness(env e) {
    require e.msg.value == 0;
    require balanceOf(receiver) >= 2 && totalSupply() >= 2;
    require nativeBalances[currentContract] >= 2;
    require nativeBalances[receiver] <= max_uint256 - 2;
    receiver.configure(4, receiver, receiver, 1);
    receiver.withdraw@withrevert(e, 1);
    assert !lastReverted && receiver.nestedSuccess();
}
