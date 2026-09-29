// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

import {ERC20} from "../ERC20.sol";

// proof-only receivers, not actually part of the token implementation
contract RejectingReceiver {
    ERC20 public token;

    constructor(ERC20 target) {
        token = target;
    }

    function withdraw(uint256 amount) external {
        token.withdraw(amount);
    }

    receive() external payable {
        revert("rejected");
    }
}

contract ReentrantReceiver {
    ERC20 public token;
    bool public armed;
    uint8 public action;
    address public from;
    address public to;
    uint256 public amount;
    bool public nestedSuccess;
    uint256 public entrySupply;
    uint256 public entryReserves;
    uint256 public entryTokens;
    uint256 public callbacks;

    constructor(ERC20 target) {
        token = target;
    }

    function configure(uint8 action_, address from_, address to_, uint256 amount_) external {
        action = action_;
        from = from_;
        to = to_;
        amount = amount_;
        armed = true;
        callbacks = 0;
        nestedSuccess = false;
    }

    function withdraw(uint256 value) external {
        token.withdraw(value);
    }

    receive() external payable {
        // one arbitrary nested operation; a nested payout is accepted passively
        if (!armed) return;
        armed = false;
        callbacks += 1;
        entrySupply = token.totalSupply();
        entryReserves = address(token).balance;
        entryTokens = token.balanceOf(address(this));
        // catch nested reverts, so the outer withdrawal can still finish
        if (action == 0) {
            try token.transfer(to, amount) returns (bool ok) {
                nestedSuccess = ok;
            }
                catch {}
        } else if (action == 1) {
            try token.transferFrom(from, to, amount) returns (bool ok) {
                nestedSuccess = ok;
            }
                catch {}
        } else if (action == 2) {
            try token.approve(to, amount) returns (bool ok) {
                nestedSuccess = ok;
            }
                catch {}
        } else if (action == 3) {
            try token.deposit{value: amount}() {
                nestedSuccess = true;
            }
                catch {}
        } else {
            try token.withdraw(amount) {
                nestedSuccess = true;
            }
                catch {}
        }
    }
}
