// SPDX-License-Identifier: MIT
pragma solidity ^0.8.35;

import {ProofBase} from "./ProofBase.sol";
import {RejectingReceiver, ReentrantReceiver} from "../../verification/Receivers.sol";

contract ERC20ReceiverRules is ProofBase {
    RejectingReceiver internal rejecting;
    ReentrantReceiver internal reentrant;

    function setUp() public override {
        super.setUp();
        rejecting = new RejectingReceiver(token);
        reentrant = new ReentrantReceiver(token);
        vm.deal(address(rejecting), svm.createUint256("rejectingETH"));
        vm.deal(address(reentrant), svm.createUint256("reentrantETH"));
    }

    function check_rejectingWithdrawalRollsBack(uint256 amount, address holder, address owner, address spender) public {
        vm.assume(amount > 0 && amount <= token.balanceOf(address(rejecting)));
        vm.assume(amount <= token.totalSupply() && amount <= address(token).balance);
        vm.assume(address(rejecting).balance <= type(uint128).max - amount);
        uint256 balance = token.balanceOf(holder);
        uint256 approval = token.allowance(owner, spender);
        uint256 supply = token.totalSupply();
        uint256 reserves = address(token).balance;
        uint256 receiverETH = address(rejecting).balance;
        (bool success,) = address(rejecting).call(abi.encodeCall(rejecting.withdraw, (amount)));
        assert(!success);
        assert(token.balanceOf(holder) == balance && token.allowance(owner, spender) == approval);
        assert(token.totalSupply() == supply && address(token).balance == reserves);
        assert(address(rejecting).balance == receiverETH);
    }

    function check_reentrantWithdrawal(
        uint8 action,
        address from,
        address to,
        uint256 nestedAmount,
        uint256 amount,
        address victim
    ) public {
        vm.assume(action < 5);
        vm.assume(victim != address(reentrant) && victim != address(token));
        vm.assume(token.allowance(victim, address(reentrant)) == 0);
        vm.assume(amount > 0 && amount <= token.balanceOf(address(reentrant)));
        vm.assume(amount <= token.totalSupply() && amount <= address(token).balance);
        vm.assume(token.totalSupply() <= token.MAX_SUPPLY());
        vm.assume(address(token).balance >= token.totalSupply());
        vm.assume(address(reentrant).balance <= type(uint128).max - amount);
        vm.assume(action != 3 || nestedAmount <= address(reentrant).balance + amount);
        uint256 victimBalance = token.balanceOf(victim);
        uint256 supply = token.totalSupply();
        uint256 reserves = address(token).balance;
        uint256 balance = token.balanceOf(address(reentrant));
        reentrant.configure(action, from, to, nestedAmount);
        (bool success,) = address(reentrant).call(abi.encodeCall(reentrant.withdraw, (amount)));
        assert(success);
        assert(reentrant.callbacks() == 1);
        assert(reentrant.entrySupply() == supply - amount);
        assert(reentrant.entryReserves() == reserves - amount);
        assert(reentrant.entryTokens() == balance - amount);
        assert(token.balanceOf(victim) >= victimBalance);
        assert(token.totalSupply() <= token.MAX_SUPPLY());
        assert(address(token).balance >= token.totalSupply());
    }

    function check_nestedWithdrawalWitness() public {
        vm.assume(token.balanceOf(address(reentrant)) >= 2 && token.totalSupply() >= 2);
        vm.assume(address(token).balance >= 2);
        vm.assume(address(reentrant).balance <= type(uint128).max - 2);
        reentrant.configure(4, address(reentrant), address(reentrant), 1);
        (bool success,) = address(reentrant).call(abi.encodeCall(reentrant.withdraw, (1)));
        assert(success && reentrant.nestedSuccess());
    }

    // the outer withdrawal and nested operation affect at most three accounts
    // count each distinct account once, "rest" is the sum of all other balances
    function check_reentrantAccounting(
        uint8 action,
        address from,
        address to,
        uint256 nestedAmount,
        uint256 amount,
        address other
    ) public {
        vm.assume(action < 5);
        address first = address(reentrant);
        address second = action == 1 ? from : first;
        address third = action < 2 ? to : first;
        uint256 supply = token.totalSupply();
        vm.assume(supply <= token.MAX_SUPPLY());
        uint256 a = token.balanceOf(first);
        uint256 b = second == first ? 0 : token.balanceOf(second);
        uint256 c = third == first || third == second ? 0 : token.balanceOf(third);
        vm.assume(a <= supply);
        vm.assume(b <= supply - a);
        vm.assume(c <= supply - a - b);
        uint256 rest = supply - a - b - c;
        vm.assume(token.balanceOf(address(0)) == 0);
        vm.assume(address(token).balance >= supply);
        vm.assume(amount > 0 && amount <= a);
        vm.assume(address(reentrant).balance <= type(uint128).max - amount);
        vm.assume(action != 3 || nestedAmount <= address(reentrant).balance + amount);
        vm.assume(other != first && other != second && other != third);
        uint256 otherBefore = token.balanceOf(other);

        reentrant.configure(action, from, to, nestedAmount);
        (bool success,) = address(reentrant).call(abi.encodeCall(reentrant.withdraw, (amount)));
        assert(success);
        a = token.balanceOf(first);
        b = second == first ? 0 : token.balanceOf(second);
        c = third == first || third == second ? 0 : token.balanceOf(third);
        supply = token.totalSupply();
        assert(a <= supply);
        assert(b <= supply - a);
        assert(c <= supply - a - b);
        assert(supply - a - b - c == rest);
        assert(token.balanceOf(other) == otherBefore);
        assert(token.balanceOf(address(0)) == 0);
        assert(supply <= token.MAX_SUPPLY() && address(token).balance >= supply);
    }
}
