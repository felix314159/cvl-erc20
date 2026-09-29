// SPDX-License-Identifier: MIT
pragma solidity ^0.8.35;

import {ERC20, ProofBase} from "./ProofBase.sol";

// just a few reachable witnesses to complement the arbitrary-state proofs
contract ERC20Witnesses is ProofBase {
    function setUp() public override {
        token = new ERC20();
    }

    function check_reachableLifecycle() public {
        address alice = address(0xA11CE);
        address bob = address(0xB0B);
        address spender = address(0xCA11);
        vm.deal(alice, 100);
        assert(step(3, alice, alice, alice, 100));
        assert(step(0, alice, alice, bob, 20));
        assert(step(2, alice, alice, spender, 30));
        assert(step(1, spender, alice, bob, 10));
        assert(step(1, spender, alice, alice, 5)); // self-transfer uses allowance
        assert(step(0, alice, alice, alice, 7));
        assert(step(4, bob, bob, bob, 30));
        assert(token.balanceOf(alice) == 70);
        assert(token.balanceOf(bob) == 0);
        assert(token.allowance(alice, spender) == 15);
        assert(token.totalSupply() == 70);
        assert(address(token).balance == 70);
        assert(bob.balance == 30);
    }
}
