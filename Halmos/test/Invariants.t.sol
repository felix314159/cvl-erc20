// SPDX-License-Identifier: MIT
pragma solidity ^0.8.35;

import {ERC20, ProofBase} from "./ProofBase.sol";

contract ERC20InitialState is ProofBase {
    function setUp() public override {
        token = new ERC20();
    }

    // symbolic account proves every initial mapping entry is zero
    function check_initialState(address account) public view {
        assert(token.balanceOf(account) == 0);
        assert(token.totalSupply() == 0);
        assert(token.balanceOf(address(0)) == 0);
        assert(address(token).balance >= token.totalSupply());
        assert(token.totalSupply() <= token.MAX_SUPPLY());
    }
}

contract ERC20Induction is ProofBase {
    // each of the next three scalar checks assumes ONLY its own invariant in
    // the pre-state, then checks all five mutating entrypoints, including reverts
    function check_noBalanceAddressZero(uint8 action, address caller, address from, address to, uint256 amount) public {
        prepareCaller(caller);
        vm.assume(token.balanceOf(address(0)) == 0);
        step(action, caller, from, to, amount);
        assert(token.balanceOf(address(0)) == 0);
    }

    function check_tokenSolvency(uint8 action, address caller, address from, address to, uint256 amount) public {
        prepareCaller(caller);
        vm.assume(address(token).balance >= token.totalSupply());
        step(action, caller, from, to, amount);
        assert(address(token).balance >= token.totalSupply());
    }

    function check_tokenSupplyCantExceedUpperCap(uint8 action, address caller, address from, address to, uint256 amount)
        public
    {
        prepareCaller(caller);
        vm.assume(token.totalSupply() <= token.MAX_SUPPLY());
        step(action, caller, from, to, amount);
        assert(token.totalSupply() <= token.MAX_SUPPLY());
    }

    // CVL tracks the total balance sum with an unbounded ghost integer, updated whenever any balance changes..
    // but here, each operation affects at most two accounts. we prove that all other balances stay unchanged, 
    // and that totalSupply changes by exactly the change in the affected balances. the remaining sum is called "rest"
    function check_totalSupplyEqualsAggregateBalances(
        uint8 action,
        address caller,
        address from,
        address to,
        uint256 amount,
        address other
    ) public {
        prepareCaller(caller);
        vm.assume(action < 5);
        address first = action == 1 ? from : caller;
        address second = (action == 0 || action == 1) ? to : first;
        uint256 a = token.balanceOf(first);
        // count aliased addresses only once
        uint256 b = first == second ? 0 : token.balanceOf(second);
        uint256 supply = token.totalSupply();
        // strengthen induction with the independently proved supply cap
        vm.assume(supply <= token.MAX_SUPPLY());
        // sum(all balances) == supply
        vm.assume(a <= supply);
        vm.assume(b <= supply - a);
        uint256 rest = supply - a - b;

        // prove that every untouched entry stays unchanged
        vm.assume(other != first && other != second);
        uint256 otherBefore = token.balanceOf(other);

        step(action, caller, from, to, amount);

        a = token.balanceOf(first);
        b = first == second ? 0 : token.balanceOf(second);
        supply = token.totalSupply();
        assert(a <= supply);
        assert(b <= supply - a);
        assert(supply - a - b == rest);
        assert(token.balanceOf(other) == otherBefore);
    }
}
