"""机器可读能力档案(PRD §6.3 / v1 §13.2)。

schema version 1 只允许 PRD 列出的七个键。手写常量字符串而不是 json.dumps:成员顺序与空白
都必须确定(同一实现的输出字节必须相同),而且嵌套的 error_code_ranges 在 fixture 里是
单行写法,让序列化器决定排版就会和 PRD 的样例形状分叉。
"""

CAPABILITIES_VERSION = 1
COMPILER_ID = "io.github.texel.python"
COMPILER_VERSION = "0.999.5"
CONFORMANCE_PROFILE = "pxl-v1"
LANGUAGE_VERSIONS = (1,)
PNG_INPUT_PROFILE = "pxl-png"

_TEXT = (
    "{\n"
    '  "capabilities_version": ' + str(CAPABILITIES_VERSION) + ',\n'
    '  "compiler_id": "' + COMPILER_ID + '",\n'
    '  "compiler_version": "' + COMPILER_VERSION + '",\n'
    '  "conformance_profile": "' + CONFORMANCE_PROFILE + '",\n'
    '  "language_versions": [' + ", ".join(str(v) for v in LANGUAGE_VERSIONS) + '],\n'
    '  "error_code_ranges": {\n'
    '    "1": {"min": "PXL001", "max": "PXL012"}\n'
    "  },\n"
    '  "png_input_profile": "' + PNG_INPUT_PROFILE + '"\n'
    "}\n"
)


def json_text():
    """能力档案的规范字节:UTF-8、无 BOM、单个 JSON 对象、末尾恰好一个 LF。"""
    return "".join(_TEXT)