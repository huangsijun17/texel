"""texel_compiler —— PXL 的第二个 compiler(独立 Python 实现,3.8+,仅标准库)。

对外的面尽量小:

    render_document(data)            PXL 字节 -> RGBA8(按 version 分派)
    compile_target(entry, resolver, bindings)  一个 target -> 位图 + 依赖清单
    encode_png(width, height, rgba)  RGBA8 -> PNG 字节
    capabilities_json()              PRD §6.3 的能力档案文本
    PxlError                         带 PXL001..PXL012 的语义错误
"""

from .api import Compiled, Rendered, compile_target, encode_png, render_document
from .capabilities import json_text as capabilities_json
from .errors import PxlError

__all__ = [
    "Compiled",
    "PxlError",
    "Rendered",
    "capabilities_json",
    "compile_target",
    "encode_png",
    "render_document",
]

__version__ = "0.999.4"