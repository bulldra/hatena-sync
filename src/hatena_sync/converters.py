import re


def hatena_to_markdown(text: str) -> str:

    def convert_heading(line: str) -> str:
        # *見出し → ##, **見出し → ###, ...
        match = re.match(r"^(\*+)(.+)", line)
        if match:
            level = len(match.group(1))
            content = match.group(2).strip()
            return f"{'#' * (level + 1)} {content}"
        return line

    def convert_list(line: str) -> str:
        # -リスト（-の後にスペースがなくてもOK）
        match = re.match(r"^-(.*)", line)
        if match:
            content = match.group(1).lstrip()
            return f"- {content}"
        return line

    def convert_quote(line: str) -> str:
        # >引用（>の後にスペースがなくてもOK）
        match = re.match(r"^(>+)(.*)", line)
        if match:
            level = len(match.group(1))
            content = match.group(2).lstrip()
            return f"{'>' * level} {content}"
        return line

    def convert_bold_italic(line: str) -> str:
        # '''''斜体''''' → *斜体*
        line = re.sub(r"'''''(.*?)'''''", r"*\1*", line)
        # ''太字'' → **太字**
        line = re.sub(r"''(.*?)''", r"**\1**", line)
        return line

    def convert_link(line: str) -> str:
        # [url:title=テキスト] → [テキスト](url)
        line = re.sub(
            r"\[(https?://[^\]:]+):title=([^\]]+)\]",
            r"[\2](\1)",
            line,
        )
        return line

    def convert_url_embed(line: str) -> str:
        # [url:embed] → url
        line = re.sub(r"\[(https?://[^\]:]+):embed\]", r"\1", line)
        return line

    def convert_image(line: str) -> str:
        # :画像URL → ![](画像URL)
        line = re.sub(r":(https?://\S+)", r"![](\1)", line)
        return line

    def convert_codeblock(lines: list[str]) -> list[str]:
        # >|| ... ||< → ``` ... ```
        in_code = False
        result = []
        for line in lines:
            if line.strip().startswith(">||"):
                in_code = True
                result.append("```")
                continue
            if line.strip().endswith("||<") and in_code:
                in_code = False
                result.append("```")
                continue
            if in_code:
                result.append(line)
            else:
                result.append(line)
        return result

    def convert_definition_list(line: str) -> str:
        match = re.match(r"^:(.+?):(.+)", line)
        if match:
            term = match.group(1).strip()
            definition = match.group(2).strip()
            return f"<dl><dt>{term}</dt><dd>{definition}</dd></dl>"
        return line

    def convert_table(line: str) -> str:
        if re.match(r"^\|.*\|$", line):
            return line
        return line

    def convert_blockquote(line: str) -> str:
        match = re.match(r"^>>(.+?)<<$", line)
        if match:
            content = match.group(1).strip()
            return f"> {content}"
        return line

    def convert_blockquote_multiline(lines: list[str]) -> list[str]:
        result = []
        in_quote = False
        for line in lines:
            if line.strip().startswith(">>"):
                in_quote = True
                content = line.strip()[2:].lstrip()
                if content:
                    result.append(f"> {content}")
                continue
            if line.strip().endswith("<<") and in_quote:
                content = line.strip()[:-2].rstrip()
                if content:
                    result.append(f"> {content}")
                in_quote = False
                continue
            if in_quote:
                result.append(f"> {line}")
            else:
                result.append(line)
        return result

    def convert_pre(line: str) -> str:
        # >| ... |< → ``` ... ```
        if line.strip().startswith(">|") and line.strip().endswith("|<"):
            content = line.strip()[2:-2].strip()
            return f"```\n{content}\n```"
        return line

    def convert_footnote(line: str) -> str:
        # (( ... )) → [^1]: ...
        match = re.match(r"^\(\((.+)\)\)$", line)
        if match:
            content = match.group(1).strip()
            return f"[^1]: {content}"
        return line

    def convert_readmore(line: str) -> str:
        # ==== または ===== → <!-- more -->
        if re.match(r"^={4,}$", line):
            return "<!-- more -->"
        return line

    def convert_tex(line: str) -> str:
        # [tex: ... ] → $...$
        match = re.match(r"\[tex:(.+)\]", line)
        if match:
            content = match.group(1).strip()
            return f"${content}$"
        return line

    def convert_category(line: str) -> str:
        # [カテゴリ] → <!-- category: カテゴリ -->
        match = re.match(r"^\[([^\]]+)\]$", line)
        if match:
            category = match.group(1).strip()
            return f"<!-- category: {category} -->"
        return line

    def convert_toc(line: str) -> str:
        # [:contents] → <!-- TOC -->
        if line.strip() == "[:contents]":
            return "<!-- TOC -->"
        return line

    # 1行変換
    lines = text.splitlines()
    converted = []
    for line in lines:
        line = convert_heading(line)
        line = convert_list(line)
        line = convert_quote(line)
        line = convert_bold_italic(line)
        line = convert_link(line)
        line = convert_url_embed(line)
        line = convert_image(line)
        line = convert_definition_list(line)
        line = convert_table(line)
        line = convert_blockquote(line)
        line = convert_pre(line)
        line = convert_footnote(line)
        line = convert_readmore(line)
        line = convert_tex(line)
        line = convert_category(line)
        line = convert_toc(line)
        converted.append(line)
    # 複数行引用変換
    converted = convert_blockquote_multiline(converted)
    # コードブロック変換
    converted = convert_codeblock(converted)
    return "\n".join(converted)
