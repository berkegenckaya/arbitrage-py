// SPDX-License-Identifier: GPL-3.0-or-later
pragma solidity ^0.8.22;

/* ========== Inline Interface Definitions ========== */

// Minimal interface for the Uniswap V3-style swap callback.
interface IUniswapV3SwapCallback {
    function uniswapV3SwapCallback(
        int256 amount0Delta, 
        int256 amount1Delta, 
        bytes calldata data
    ) external;
}

// Minimal interface for a Uniswap V3-style pool (or RamsesV3Pool).
interface IUniswapV3Pool {
    function swap(
        address recipient,
        bool zeroForOne,
        int256 amountSpecified,
        uint160 sqrtPriceLimitX96,
        bytes calldata data
    ) external returns (int256 amount0, int256 amount1);
    
    function token0() external view returns (address);
    function token1() external view returns (address);
}

// Minimal ERC20 interface.
interface IERC20 {
    function transfer(address recipient, uint256 amount) external returns (bool);
    function transferFrom(address sender, address recipient, uint256 amount) external returns (bool);
}

/* ========== SwapExecutor Contract ========== */

contract SwapExecutor is IUniswapV3SwapCallback {
    address public owner;

    modifier onlyOwner() {
        require(msg.sender == owner, "Not owner");
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    /**
     * @notice Executes a swap on a target pool.
     * @param pool The address of the target pool.
     * @param zeroForOne If true, swaps token0 for token1 (i.e. selling base to get quote);
     *                   if false, swaps token1 for token0 (i.e. buying base using quote).
     * @param amountSpecified The swap amount in the smallest unit of the input token.
     *                        (For exact input swaps, use a positive amount.)
     * @param sqrtPriceLimitX96 The price limit in Q96 format. For a buy (zeroForOne=false),
     *                          set this above the current sqrtPrice; for a sell (zeroForOne=true),
     *                          set it below.
     */
    function executeSwap(
        address pool, 
        bool zeroForOne, 
        int256 amountSpecified, 
        uint160 sqrtPriceLimitX96
    ) external {
        IUniswapV3Pool(pool).swap(
            msg.sender, //change to msg.sender
            zeroForOne,
            amountSpecified,
            sqrtPriceLimitX96,
            ""
        );
    }

    /**
     * @notice Callback function required by the pool's swap().
     * Instead of using the contract's own balance, this implementation uses transferFrom
     * to pull tokens from the owner. The owner must pre-approve this contract to spend the required token amounts.
     * @param amount0Delta The amount of token0 owed (if positive).
     * @param amount1Delta The amount of token1 owed (if positive).
     * @param data Not used.
     */
    function uniswapV3SwapCallback(
        int256 amount0Delta, 
        int256 amount1Delta, 
        bytes calldata data
    ) external override {
        // Silence unused variable warning
        data;
        address pool = msg.sender; // The pool contract calling back.
        if (amount0Delta > 0) {
            address token0 = IUniswapV3Pool(pool).token0();
            require(
                IERC20(token0).transferFrom(owner, pool, uint256(amount0Delta)),
                "Transfer token0 failed"
            );
        }
        if (amount1Delta > 0) {
            address token1 = IUniswapV3Pool(pool).token1();
            require(
                IERC20(token1).transferFrom(owner, pool, uint256(amount1Delta)),
                "Transfer token1 failed"
            );
        }
    }

    /**
     * @notice Allows the owner to withdraw tokens from the contract (if any remain).
     * @param token The ERC20 token address.
     * @param amount The amount to withdraw.
     */
    function withdrawToken(address token, uint256 amount) external onlyOwner {
        require(IERC20(token).transfer(owner, amount), "Withdrawal failed");
    }

    /// @notice Allow the contract to receive ETH.
    receive() external payable {}
}
