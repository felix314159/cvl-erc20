methods {
    function balanceOf(address) external returns (uint256) envfree;
    function totalSupply() external returns (uint256) envfree;
    function MAX_SUPPLY() external returns (uint256) envfree;
}

ghost mathint aggregateBalances {
    init_state axiom aggregateBalances == 0;
}
hook Sstore balanceOf[KEY address account] uint256 value (uint256 oldValue) {
    aggregateBalances = aggregateBalances + value - oldValue;
}

strong invariant callbackSupplyEqualsBalances() totalSupply() == aggregateBalances;
strong invariant callbackSolvency() nativeBalances[currentContract] >= totalSupply();
strong invariant callbackSupplyCap() totalSupply() <= MAX_SUPPLY();
strong invariant callbackZeroBalance() balanceOf(0) == 0;
