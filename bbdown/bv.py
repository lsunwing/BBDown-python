"""BV 号 / av 号互转。

移植自 BBDown.Core/Util/BilibiliBvConverter.cs，原始算法来自
https://github.com/Colerar/abv/blob/main/src/lib.rs
"""

from __future__ import annotations

__all__ = ["encode", "decode", "is_valid_bvid"]

XOR_CODE = 23442827791579
MASK_CODE = (1 << 51) - 1
MAX_AID = MASK_CODE + 1
MIN_AID = 1
BASE = 58
BV_LEN = 9

ALPHABET = "FcwAPNKTMug3GV5Lj7EJnHpWsx4tb8haYeviqBz6rkCy12mUSDQX9RdoZf"
REV_ALPHABET = {ch: i for i, ch in enumerate(ALPHABET)}


def encode(avid: int) -> str:
    """av 号 -> BV 号（带 ``BV1`` 前缀）。"""
    avid = int(avid)
    if avid < MIN_AID:
        raise ValueError(f"Av {avid} is smaller than {MIN_AID}")
    if avid >= MAX_AID:
        raise ValueError(f"Av {avid} is bigger than {MAX_AID}")

    bvid = [""] * BV_LEN
    tmp = (MAX_AID | avid) ^ XOR_CODE

    i = BV_LEN - 1
    while tmp != 0 and i >= 0:
        bvid[i] = ALPHABET[tmp % BASE]
        tmp //= BASE
        i -= 1

    bvid[0], bvid[6] = bvid[6], bvid[0]
    bvid[1], bvid[4] = bvid[4], bvid[1]

    return "BV1" + "".join(bvid)


def decode(bvid_str: str) -> int:
    """BV 号（不含 ``BV1`` 前缀的 9 位部分）-> av 号。"""
    if len(bvid_str) != BV_LEN:
        raise ValueError(f"Bv BV1{bvid_str} must to be 12 char")

    bvid = list(bvid_str)
    bvid[0], bvid[6] = bvid[6], bvid[0]
    bvid[1], bvid[4] = bvid[4], bvid[1]

    avid = 0
    for ch in bvid:
        avid = avid * BASE + REV_ALPHABET[ch]

    return (avid & MASK_CODE) ^ XOR_CODE


def is_valid_bvid(bvid_str: str) -> bool:
    """判断 9 位主体是否只含字母表内字符。"""
    return len(bvid_str) == BV_LEN and all(ch in REV_ALPHABET for ch in bvid_str)
