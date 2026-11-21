package io.github.texel.cli;

/**
 * 统一能力档案的 JSON 输出（PRD §6.3 / `spec/PXL.md` §13.2）。
 *
 * <p>为什么不用 JSON 库：schema 极小，而**字节确定性**是契约的一部分（同一实现两次输出必须相同）。
 * 手写常量字符串是唯一能保证成员顺序与空白稳定的写法，也避免为此引入依赖（`AGENTS.md` 契约 7）。
 *
 * <p>The response describes the current {@code pxl-v1} profile and wire version 1.
 */
final class Capabilities {

    private Capabilities() {
    }

    /** 规范形式的能力档案；末尾恰好一个 LF（PRD §6.3）。 */
    static String json() {
        return "{\n"
                + "  \"capabilities_version\": 1,\n"
                + "  \"compiler_id\": \"io.github.texel.compiler\",\n"
                + "  \"compiler_version\": \"0.999.2\",\n"
                + "  \"conformance_profile\": \"" + io.github.texel.core.PxlParser.conformanceProfile()
                + "\",\n"
                + "  \"language_versions\": [\n"
                + "    1\n"
                + "  ],\n"
                + "  \"error_code_ranges\": {\n"
                + "    \"1\": {\n"
                + "      \"min\": \"PXL001\",\n"
                + "      \"max\": \"PXL012\"\n"
                + "    }\n"
                + "  },\n"
                + "  \"png_input_profile\": \"pxl-png\"\n"
                + "}\n";
    }
}
