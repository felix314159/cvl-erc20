// SPDX-License-Identifier: MIT
pragma solidity ^0.8.35;

import {ProofBase, Vm} from "./ProofBase.sol";

contract ERC20ExtendedRules is ProofBase {
    function check_approvalCorrectAndIsolated(
        address caller,
        address spender,
        uint256 amount,
        address owner,
        address otherSpender,
        address holder
    ) public {
        prepareCaller(caller);
        uint256 approval = token.allowance(owner, otherSpender);
        uint256 balance = token.balanceOf(holder);
        uint256 supply = token.totalSupply();
        uint256 reserves = address(token).balance;
        (bool success, bytes memory result) = stepResult(2, caller, caller, spender, amount);
        assert(success);
        assertTrueResult(result);
        assert(token.allowance(caller, spender) == amount);
        if (owner != caller || otherSpender != spender) {
            assert(token.allowance(owner, otherSpender) == approval);
        }
        assert(token.balanceOf(holder) == balance);
        assert(token.totalSupply() == supply && address(token).balance == reserves);
    }

    function check_unrelatedAllowancesUnchanged(
        uint8 action,
        address caller,
        address from,
        address to,
        uint256 amount,
        address owner,
        address spender
    ) public {
        prepareCaller(caller);
        if (action == 1) vm.assume(owner != from || spender != caller);
        if (action == 2) vm.assume(owner != caller || spender != to);
        if (action == 4) assumeEOA(caller);
        uint256 approval = token.allowance(owner, spender);
        vm.assume(step(action, caller, from, to, amount));
        assert(token.allowance(owner, spender) == approval);
    }

    function check_validTransferSucceeds(address caller, address to, uint256 amount) public {
        prepareCaller(caller);
        vm.assume(to != address(0));
        vm.assume(amount <= token.balanceOf(caller));
        vm.assume(to == caller || token.balanceOf(to) <= type(uint256).max - amount);
        (bool success, bytes memory result) = stepResult(0, caller, caller, to, amount);
        assert(success);
        assertTrueResult(result);
    }

    function check_validTransferFromSucceeds(address caller, address from, address to, uint256 amount) public {
        prepareCaller(caller);
        vm.assume(to != address(0));
        vm.assume(amount <= token.balanceOf(from));
        vm.assume(amount <= token.allowance(from, caller));
        vm.assume(to == from || token.balanceOf(to) <= type(uint256).max - amount);
        (bool success, bytes memory result) = stepResult(1, caller, from, to, amount);
        assert(success);
        assertTrueResult(result);
    }

    function check_validDepositSucceeds(address caller, uint256 amount) public {
        prepareCaller(caller);
        vm.assume(caller != address(0) && caller != address(token));
        vm.assume(amount > 0);
        vm.assume(token.totalSupply() <= token.MAX_SUPPLY());
        vm.assume(amount <= token.MAX_SUPPLY() - token.totalSupply());
        vm.assume(token.balanceOf(caller) <= type(uint256).max - amount);
        vm.assume(caller.balance >= amount);
        vm.assume(address(token).balance <= type(uint128).max - amount);
        assert(step(3, caller, caller, caller, amount));
    }

    function check_successfulCallsReturnTrue(uint8 action, address caller, address from, address to, uint256 amount)
        public
    {
        vm.assume(action < 3);
        prepareCaller(caller);
        (bool success, bytes memory result) = stepResult(action, caller, from, to, amount);
        vm.assume(success);
        assertTrueResult(result);
    }

    function check_failedTransferFromRollsBack(
        address caller,
        address from,
        address to,
        uint256 amount,
        address owner,
        address spender,
        address holder
    ) public {
        prepareCaller(caller);
        vm.assume(to == address(0) || amount > token.balanceOf(from) || amount > token.allowance(from, caller));
        uint256 approval = token.allowance(owner, spender);
        uint256 balance = token.balanceOf(holder);
        uint256 supply = token.totalSupply();
        uint256 reserves = address(token).balance;
        assert(!step(1, caller, from, to, amount));
        assert(token.allowance(owner, spender) == approval && token.balanceOf(holder) == balance);
        assert(token.totalSupply() == supply && address(token).balance == reserves);
    }

    function check_selfTransferPreservesBalance(address caller, uint256 amount) public {
        prepareCaller(caller);
        uint256 balance = token.balanceOf(caller);
        vm.assume(step(0, caller, caller, caller, amount));
        assert(token.balanceOf(caller) == balance);
    }

    function assertTrueResult(bytes memory result) internal pure {
        assert(result.length == 32);
        assert(abi.decode(result, (uint256)) == 1);
    }

    function assertEvent(Vm.Log memory entry, bytes32 signature, address from, address to, uint256 amount)
        internal
        view
    {
        assert(entry.emitter == address(token));
        assert(entry.topics.length == 3 && entry.data.length == 32);
        assert(entry.topics[0] == signature);
        assert(entry.topics[1] == bytes32(uint256(uint160(from))));
        assert(entry.topics[2] == bytes32(uint256(uint160(to))));
        assert(abi.decode(entry.data, (uint256)) == amount);
    }

    function check_operationEvents(uint8 action, address caller, address from, address to, uint256 amount) public {
        prepareCaller(caller);
        if (action == 4) assumeEOA(caller);
        uint256 approval = token.allowance(from, caller);
        // the local adapter reads actual LOG instructions from successful calls
        vm.recordLogs();
        vm.assume(step(action, caller, from, to, amount));
        Vm.Log[] memory entries = vm.getRecordedLogs();
        assert(entries.length == (action == 1 ? 2 : 1));
        if (action == 1 || action == 2) {
            assertEvent(
                entries[0],
                keccak256("Approval(address,address,uint256)"),
                action == 1 ? from : caller,
                action == 1 ? caller : to,
                action == 1 ? approval - amount : amount
            );
        }
        if (action != 2) {
            assertEvent(
                entries[action == 1 ? 1 : 0],
                keccak256("Transfer(address,address,uint256)"),
                action == 3 ? address(0) : (action == 1 ? from : caller),
                action == 4 ? address(0) : (action == 3 ? caller : to),
                amount
            );
        }
    }
}
