#!/usr/bin/env python3
"""Generate a local GUI override from the installed Victoria 3 game files."""

import argparse
import re
from pathlib import Path

CALLBACK = re.compile(
    r'^\s*ontextedited\s*=\s*"\[MilitaryFormationChangeNamePopup\.OnEditName\]"',
    re.MULTILINE,
)
TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|#[^\n]*|\w+|[{}=]')
NAME_TEXT = re.compile(
    r'^(?P<prefix>[ \t]*text[ \t]*=[ \t]*)'
    r'"(?P<original>\[MilitaryFormationChangeNamePopup\.[^"\n]+\])"',
    re.MULTILINE,
)
PROBE_FLAG = "dfn_rename_probe"
TEST_NAME = "DFN Rename Probe"


def patch_window(source: str) -> str:
    tokens = list(TOKEN.finditer(source))
    callbacks = list(CALLBACK.finditer(source))
    if len(callbacks) != 1:
        raise ValueError("Expected one original formation name edit callback")

    callback = callbacks[0]
    stack = []
    editbox = None
    for index, token in enumerate(tokens):
        if token.group() == "{":
            stack.append(index)
        elif token.group() == "}":
            opening = stack.pop()
            if opening == editbox:
                closing = token
                break
        elif callback.start() <= token.start() < callback.end() and token.group() == "ontextedited":
            editbox = stack[-1]
    else:
        raise ValueError("Could not find the formation name editbox")

    if tokens[editbox - 2].group() != "editbox":
        raise ValueError("The rename callback is not directly inside an editbox")

    block_start = tokens[editbox - 2].start()
    block_end = closing.end()
    block = source[block_start:block_end]
    matches = list(NAME_TEXT.finditer(block))
    if len(matches) != 1:
        raise ValueError("Expected one original formation name text binding")

    original = matches[0].group("original")[1:-1]
    flag_key = (
        f"Concatenate('{PROBE_FLAG}_', "
        "MilitaryFormationChangeNamePopup.GetFormation.GetIDString)"
    )
    text_binding = (
        f"[Select_CString(GetVariableSystem.Exists({flag_key}), "
        f"'{TEST_NAME}', {original})]"
    )
    block = NAME_TEXT.sub(
        lambda match: f'{match["prefix"]}"{text_binding}"', block, count=1
    )
    indent_start = source.rfind("\n", 0, block_start) + 1
    indent = source[indent_start:block_start]
    if indent.strip():
        raise ValueError("Unexpected inline editbox layout")

    button = [
        "button = {",
        f'\tname = "{PROBE_FLAG}"',
        "\tsize = { 154 36 }",
        f'\tonclick = "[GetVariableSystem.Toggle({flag_key})]"',
        "\ttextbox = {",
        '\t\ttext = "dfn_rename_probe_button"',
        "\t\tparentanchor = center",
        "\t\talwaystransparent = yes",
        "\t}",
        "}",
    ]
    block += "\n" + "\n".join(indent + line for line in button)
    return source[:block_start] + block + source[block_end:]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("game", type=Path, help="Victoria 3 game directory containing gui/")
    args = parser.parse_args()
    game_gui = args.game.resolve() / "gui"
    if not game_gui.is_dir():
        parser.error(f"Missing GUI directory: {game_gui}")

    mod_gui = Path(__file__).resolve().parent.parent / "gui"
    windows = []
    for path in sorted(game_gui.rglob("*.gui")):
        source = path.read_text(encoding="utf-8-sig")
        if CALLBACK.search(source):
            windows.append((path, source))
    if len(windows) != 1:
        parser.error(f"Expected one formation rename GUI file, found {len(windows)}")

    path, source = windows[0]
    target = mod_gui / path.relative_to(game_gui)
    try:
        patched = patch_window(source)
    except (ValueError, IndexError) as error:
        parser.error(str(error))
    if target.exists() and target.read_text(encoding="utf-8-sig") != patched:
        parser.error(f"Existing GUI override differs: {target}")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(patched, encoding="utf-8-sig")
    print(target)


if __name__ == "__main__":
    main()
