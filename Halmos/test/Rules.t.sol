// SPDX-License-Identifier: MIT
pragma solidity ^0.8.35;

import {ProofBase} from "./ProofBase.sol";

contract ERC20Rules is ProofBase {
    function check_successfulTransferArithmetic(address caller, address recipient, uint256 amount) public {
        prepareCaller(caller);
        vm.assume(caller != recipient);
        uint256 beforeSender = token.balanceOf(caller);
        uint256 beforeRecipient = token.balanceOf(recipient);
        vm.assume(step(0, caller, caller, recipient, amount));

        assert(beforeSender >= amount);
        assert(beforeRecipient <= type(uint256).max - amount);
        unchecked {
            assert(token.balanceOf(caller) == beforeSender - amount);
            assert(token.balanceOf(recipient) == beforeRecipient + amount);
        }
    }

    function check_successfulTransferPreservesSupplyAndETHReserves(address caller, address recipient, uint256 amount)
        public
    {
        prepareCaller(caller);
        uint256 supply = token.totalSupply();
        uint256 reserves = address(token).balance;
        vm.assume(step(0, caller, caller, recipient, amount));
        assert(token.totalSupply() == supply);
        assert(address(token).balance == reserves);
    }

    function check_transferFromArithmetic(address caller, address from, address recipient, uint256 amount) public {
        prepareCaller(caller);
        uint256 allowance = token.allowance(from, caller);
        uint256 beforeFrom = token.balanceOf(from);
        uint256 beforeRecipient = token.balanceOf(recipient);
        vm.assume(step(1, caller, from, recipient, amount));
        assert(allowance >= amount);
        unchecked {
            assert(token.allowance(from, caller) == allowance - amount);
        }
        if (from == recipient) {
            assert(token.balanceOf(from) == beforeFrom);
        } else {
            assert(beforeFrom >= amount);
            assert(beforeRecipient <= type(uint256).max - amount);
            unchecked {
                assert(token.balanceOf(from) == beforeFrom - amount);
                assert(token.balanceOf(recipient) == beforeRecipient + amount);
            }
        }
    }

    function check_spendingMoreThanAllowanceIsImpossible(
        address caller,
        address from,
        address recipient,
        uint256 amount
    ) public {
        prepareCaller(caller);
        vm.assume(amount > token.allowance(from, caller));
        // translate CVL's revert handling into solidity
        assert(!step(1, caller, from, recipient, amount)); // assert that transferFrom call fails
    }

    function check_depositArithmetic(address caller, uint256 amount) public {
        prepareCaller(caller);
        uint256 reserves = address(token).balance;
        uint256 balance = token.balanceOf(caller);
        vm.assume(step(3, caller, caller, caller, amount));
        assert(reserves <= type(uint256).max - amount);
        assert(balance <= type(uint256).max - amount);
        unchecked {
            assert(address(token).balance == reserves + amount);
            assert(token.balanceOf(caller) == balance + amount);
        }
    }

    function check_eoaWithdrawalArithmetic(address caller, uint256 amount) public {
        prepareCaller(caller);
        assumeEOA(caller);
        uint256 reserves = address(token).balance;
        uint256 eth = caller.balance;
        uint256 balance = token.balanceOf(caller);
        uint256 supply = token.totalSupply();
        vm.assume(step(4, caller, caller, caller, amount));
        assert(reserves >= amount && balance >= amount && supply >= amount);
        assert(eth <= type(uint256).max - amount);
        unchecked {
            assert(address(token).balance == reserves - amount);
            assert(caller.balance == eth + amount);
            assert(token.balanceOf(caller) == balance - amount);
            assert(token.totalSupply() == supply - amount);
        }
    }

    function check_withdrawalIsAlwaysPossible(address caller, uint256 amount) public {
        prepareCaller(caller);
        assumeEOA(caller);
        vm.assume(amount > 0);
        vm.assume(amount <= token.balanceOf(caller));
        vm.assume(amount <= token.totalSupply());
        vm.assume(amount <= address(token).balance);
        vm.assume(amount <= type(uint256).max - caller.balance);

        assert(step(4, caller, caller, caller, amount));
    }
}
