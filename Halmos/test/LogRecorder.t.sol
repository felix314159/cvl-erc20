// SPDX-License-Identifier: MIT
pragma solidity ^0.8.35;

import {Vm} from "./ProofBase.sol";

contract LogEmitter {
    event Sample(address indexed account, uint256 amount);

    function emitLog(address account, uint256 amount, bool fail) external {
        emit Sample(account, amount);
        require(!fail, "rejected");
    }

    function nested(LogEmitter child, address account, uint256 amount, bool fail) external {
        emit Sample(account, 1);
        child.emitLog(account, amount, false);
        emit Sample(account, 2);
        require(!fail, "rejected parent");
    }
}

contract LogRecorderChecks {
    Vm internal constant vm = Vm(address(uint160(uint256(keccak256("hevm cheat code")))));
    LogEmitter internal parent;
    LogEmitter internal child;

    function setUp() public {
        parent = new LogEmitter();
        child = new LogEmitter();
    }

    function check_nestedLogsPreserveSymbolicPayload(address account, uint256 amount) public {
        vm.recordLogs();
        parent.nested(child, account, amount, false);
        Vm.Log[] memory entries = vm.getRecordedLogs();
        assert(entries.length == 3);
        assert(entries[0].emitter == address(parent) && entries[2].emitter == address(parent));
        assert(entries[1].emitter == address(child));
        assert(entries[1].topics.length == 2 && entries[1].data.length == 32);
        assert(entries[1].topics[0] == keccak256("Sample(address,uint256)"));
        assert(entries[1].topics[1] == bytes32(uint256(uint160(account))));
        assert(abi.decode(entries[0].data, (uint256)) == 1);
        assert(abi.decode(entries[1].data, (uint256)) == amount);
        assert(abi.decode(entries[2].data, (uint256)) == 2);
    }

    function check_revertedSubtreeHasNoCommittedLogs(address account, uint256 amount) public {
        vm.recordLogs();
        (bool success,) = address(parent).call(abi.encodeCall(parent.nested, (child, account, amount, true)));
        assert(!success);
        assert(vm.getRecordedLogs().length == 0);
    }

    function check_recordingResetsAndDrains(address account, uint256 amount) public {
        vm.recordLogs();
        parent.emitLog(account, 1, false);
        vm.recordLogs();
        child.emitLog(account, amount, false);
        Vm.Log[] memory entries = vm.getRecordedLogs();
        assert(entries.length == 1 && entries[0].emitter == address(child));
        assert(abi.decode(entries[0].data, (uint256)) == amount);
        assert(vm.getRecordedLogs().length == 0);
        parent.emitLog(account, 2, false);
        entries = vm.getRecordedLogs();
        assert(entries.length == 1 && entries[0].emitter == address(parent));
        assert(abi.decode(entries[0].data, (uint256)) == 2);
    }
}
