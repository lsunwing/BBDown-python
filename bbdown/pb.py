"""极简 protobuf (proto2) 编解码器。

BBDown 走 APP 接口时需要发 gRPC 请求，原始项目由 ``Grpc.Tools`` 生成 C# 类。
为了避免 Python 侧引入 protoc 工具链，这里用几十行代码实现同样的功能：
按字段号读写 varint / length-delimited，足以覆盖项目用到的全部 message。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = ["Field", "Message", "encode_varint", "decode_varint", "read_varint"]

# wire types
WT_VARINT = 0
WT_64BIT = 1
WT_LEN = 2
WT_32BIT = 5


def encode_varint(value: int) -> bytes:
    """无符号 varint 编码（负数按 64 位补码处理）。"""
    if value < 0:
        value += 1 << 64
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def read_varint(data: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        if pos >= len(data):
            raise ValueError("truncated varint")
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7
        if shift > 70:
            raise ValueError("varint too long")


# 兼容别名
decode_varint = read_varint


@dataclass(frozen=True)
class Field:
    """一个 message 字段的描述。"""

    num: int
    name: str
    type: str = "int"  # int | bool | str | bytes | msg
    sub: type | None = None
    repeated: bool = False


class Message:
    """声明式 proto2 message。

    子类通过 ``FIELDS`` 声明字段；实例属性可直接读写。
    未设置的 optional 字段为 ``None``，repeated 字段为 ``[]``。
    """

    FIELDS: tuple[Field, ...] = ()
    _BY_NUM: dict[int, Field] | None = None

    def __init__(self, **kwargs: Any) -> None:
        if self.__class__._BY_NUM is None:
            self.__class__._BY_NUM = {f.num: f for f in self.FIELDS}
        for f in self.FIELDS:
            object.__setattr__(self, f.name, [] if f.repeated else None)
        for key, value in kwargs.items():
            if value is not None:
                setattr(self, key, value)

    # -- 解码 -------------------------------------------------------------
    @classmethod
    def parse(cls, data: bytes) -> "Message":
        obj = cls()
        obj.merge(data)
        return obj

    def merge(self, data: bytes) -> None:
        fields = self.__class__._BY_NUM or {}
        pos = 0
        total = len(data)
        while pos < total:
            key, pos = read_varint(data, pos)
            num, wire = key >> 3, key & 0x7
            field = fields.get(num)

            if wire == WT_VARINT:
                value, pos = read_varint(data, pos)
                if field is not None:
                    if field.type == "bool":
                        self._put(field, bool(value))
                    else:
                        self._put(field, value)
            elif wire == WT_64BIT:
                pos += 8
            elif wire == WT_32BIT:
                pos += 4
            elif wire == WT_LEN:
                length, pos = read_varint(data, pos)
                raw = data[pos : pos + length]
                pos += length
                if field is None:
                    continue
                if field.type == "str":
                    self._put(field, raw.decode("utf-8", "replace"))
                elif field.type == "bytes":
                    self._put(field, raw)
                elif field.type == "msg":
                    assert field.sub is not None
                    self._put(field, field.sub.parse(raw))
            else:
                raise ValueError(f"unsupported wire type {wire}")

    def _put(self, field: Field, value: Any) -> None:
        if field.repeated:
            getattr(self, field.name).append(value)
        else:
            setattr(self, field.name, value)

    # -- 编码 -------------------------------------------------------------
    def serialize(self) -> bytes:
        out = bytearray()
        for field in self.FIELDS:
            value = getattr(self, field.name)
            if value is None:
                continue
            items = value if field.repeated else [value]
            for item in items:
                key = encode_varint((field.num << 3) | self._wire(field))
                if field.type in ("int", "bool"):
                    out += key + encode_varint(int(item))
                elif field.type == "str":
                    raw = str(item).encode("utf-8")
                    out += key + encode_varint(len(raw)) + raw
                elif field.type == "bytes":
                    out += key + encode_varint(len(item)) + item
                elif field.type == "msg":
                    raw = item.serialize()
                    out += key + encode_varint(len(raw)) + raw
                else:  # pragma: no cover - 声明错误
                    raise ValueError(f"unsupported field type {field.type}")
        return bytes(out)

    @staticmethod
    def _wire(field: Field) -> int:
        if field.type in ("int", "bool"):
            return WT_VARINT
        return WT_LEN
