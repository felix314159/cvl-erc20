// SPDX-License-Identifier: MIT
pragma solidity ^0.8.35;

import {ERC20} from "../../ERC20.sol";

interface Vm {
    struct Log {
        bytes32[] topics;
        bytes data;
        address emitter;
    }
    function recordLogs() external;
    function getRecordedLogs() external returns (Log[] memory);
    function assume(bool condition) external;
    function prank(address sender) external;
    function deal(address account, uint256 balance) external;
}

interface SVM {
    function enableSymbolicStorage(address target) external;
    function createUint256(string calldata name) external returns (uint256);
}

// representative of CVL's optimistic, non-reentrant fallback
contract PassiveReceiver {
    receive() external payable {}
}

contract RejectingReceiver {
    receive() external payable {
        revert("ETH rejected");
    }
}

abstract contract ProofBase {
    Vm internal constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code"))))); // 0x7109709ECfa91a80626fF3989D68f67F5b1DD12D
    SVM internal constant svm = SVM(address(uint160(uint256(keccak256("svm cheat code"))))); // 0xF3993A62377BCd56AE39D773740A5390411E8BC9
    ERC20 internal token;
    PassiveReceiver internal receiver;
    RejectingReceiver internal rejectingReceiver;

    function setUp() public virtual {
        token = new ERC20();
        receiver = new PassiveReceiver();
        rejectingReceiver = new RejectingReceiver();
        // symbolic storage models arbitrary pre-state balances, allowances and supply
        svm.enableSymbolicStorage(address(token));
        vm.deal(address(token), svm.createUint256("initialReserves"));
    }

    function prepareCaller(address caller) internal {
        // exclude verifier infrastructure
        vm.assume(caller != address(vm));
        vm.assume(caller != address(svm));
        vm.assume(caller != address(this));
        vm.assume(caller != address(0x636F6e736F6c652e6c6f67)); // ASCII encoding of "console.log", testing tools recognize this as logging
        // precompiles also aren't ordinary ETH receivers
        vm.assume(caller == address(0) || uint160(caller) > 10);

        if (caller != address(token)) {
            vm.deal(caller, svm.createUint256("callerETH"));
        }
    }

    function assumeEOA(address caller) internal {
        vm.assume(caller.code.length == 0);
    }

    // five mutating entrypoints
    // construct calldata BEFORE prank: a getter called after prank consumes it
    function step(uint8 action, address caller, address from, address to, uint256 amount)
        internal
        returns (bool success)
    {
        (success,) = stepResult(action, caller, from, to, amount);
    }

    function stepResult(uint8 action, address caller, address from, address to, uint256 amount)
        internal
        returns (bool success, bytes memory result)
    {
        vm.assume(action < 5);
        bytes memory data;
        uint256 value;
        if (action == 0) {
            data = abi.encodeCall(token.transfer, (to, amount));
        } else if (action == 1) {
            data = abi.encodeCall(token.transferFrom, (from, to, amount));
        } else if (action == 2) {
            data = abi.encodeCall(token.approve, (to, amount));
        } else if (action == 3) {
            data = abi.encodeCall(token.deposit, ());
            value = amount;
        } else {
            data = abi.encodeCall(token.withdraw, (amount));
        }
        vm.prank(caller);
        (success, result) = address(token).call{value: value}(data);
    }
}
