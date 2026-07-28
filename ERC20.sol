// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

/// @title A simple ERC-20 style token
contract ERC20 {
    // optional constants
    string public constant name = "Just Internet Money Only Theorems Hold YIPPEE";
    string public constant symbol = "JIMOTHY";
    uint8 public constant decimals = 0; // metadata for signaling that 1 wei = 1 token
    uint256 public constant MAX_SUPPLY = 1 ether; // arbitrary upper cap of 1 ETH worth of jimothy

    mapping(address => uint256) public balanceOf;
    mapping(address => mapping(address => uint256)) private _allowances; // allowances refer to token balance, not to deposited ETH
    uint256 public totalSupply; // refers to erc20 token supply, not to ETH stored by contract

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    function allowance(
        address owner,
        address spender
    ) public view returns (uint256) {
        return _allowances[owner][spender];
    }

    function transfer(address recipient, uint256 amount) public returns (bool) {
        _transfer(msg.sender, recipient, amount);
        return true;
    }

    function transferFrom( // used by others (who have an allowance from you) to spend your funds
        address sender,
        address recipient,
        uint256 amount
    ) public returns (bool) {
        uint256 currentAllowance = _allowances[sender][msg.sender];
        require(currentAllowance >= amount, "Transfer exceeds allowance");

        _approve(sender, msg.sender, currentAllowance - amount);
        _transfer(sender, recipient, amount);

        return true;
    }

    function _transfer(
        address sender,
        address recipient,
        uint256 amount
    ) internal {
        require(recipient != address(0), "Transfer to zero address");

        uint256 senderBalance = balanceOf[sender];
        require(senderBalance >= amount, "Transfer exceeds balance");

        balanceOf[sender] = senderBalance - amount;
        balanceOf[recipient] += amount;

        emit Transfer(sender, recipient, amount);
    }

    function approve(address spender, uint256 amount) public returns (bool) {
        // self-approval is allowed but there is no reason to do it, just call transfer()
        _approve(msg.sender, spender, amount);
        return true;
    }

    function _approve(
        address owner,
        address spender,
        uint256 amount
    ) internal {
        _allowances[owner][spender] = amount;
        emit Approval(owner, spender, amount);
    }

    function deposit() public payable {
        require(msg.sender != address(0), "Depositing to zero address");
        // BUG: Line below is important, otherwise such a contract itself could potentially mint tokens for free [the prover does not care whether it actually would be possible, it is a defensive guard]
        //      (ETH transfer from x to x, so total ETH supply has not increased but the mint would still have triggered)
        require(msg.sender != address(this), "Depositing to self");

        // mint new tokens
        uint256 amount = msg.value;
        require(
            amount > 0,
            "Zero deposits are not possible"
        );
        require(
            amount <= MAX_SUPPLY - totalSupply,
            "Maximum supply exceeded"
        );

        balanceOf[msg.sender] += amount;
        totalSupply += amount;

        emit Transfer(address(0), msg.sender, amount);
    }

    function withdraw(uint256 amount) public {
        require(amount > 0, "Amount must be positive");
        require(balanceOf[msg.sender] >= amount, "Insufficient token balance");
        require(address(this).balance >= amount, "Insufficient ETH reserves");

        // Burn tokens before making the external call
        balanceOf[msg.sender] -= amount;
        totalSupply -= amount;

        emit Transfer(msg.sender, address(0), amount);

        // Return ETH at the 1 token = 1 Wei exchange rate
        (bool success, ) = payable(msg.sender).call{value: amount}("");
        require(success, "ETH transfer failed");
  }

}
