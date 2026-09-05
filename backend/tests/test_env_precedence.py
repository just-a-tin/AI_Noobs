"""`.env` must beat process defaults.

scripts/run_local.py once ran `os.environ.setdefault("MOCK_AWS", "true")`
before .env was loaded. Because load_dotenv never overrides an already-set
variable, that default always won: the server served canned verdicts while
.env plainly said MOCK_AWS=false, and nothing in the output explained why.

The failure was invisible — a mock verdict looks like a real one — so it is
worth a test even though it is really about start-up ordering.
"""

import subprocess
import sys
import textwrap
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent


def run_snippet(code: str, env_file_text: str, tmp_path: Path) -> str:
    """Execute code in a fresh interpreter with a throwaway .env."""
    env_file = tmp_path / ".env"
    env_file.write_text(textwrap.dedent(env_file_text), encoding="utf-8")

    script = tmp_path / "snippet.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import sys
            sys.path.insert(0, {str(BACKEND)!r})
            from dotenv import load_dotenv
            load_dotenv({str(env_file)!r})
            """
        )
        + textwrap.dedent(code),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=60,
        # A real .env in the repo root must not leak in.
        env={"PATH": "", "SYSTEMROOT": "C:\\Windows", "SENTINEL_SKIP_DOTENV": "0"},
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_dotenv_can_disable_mock_mode(tmp_path):
    """The bug: a process-level default set before load_dotenv wins forever."""
    out = run_snippet(
        """
        from app.config import settings
        print(settings.mock_bedrock)
        """,
        "MOCK_AWS=false\n",
        tmp_path,
    )
    assert out == "False", "a .env saying MOCK_AWS=false must disable mock mode"


def test_setdefault_before_load_dotenv_is_the_trap(tmp_path):
    """Documents precisely why the ordering matters, so nobody reinstates it."""
    out = run_snippet(
        """
        import os
        os.environ.setdefault("MOCK_AWS", "true")   # the old run_local.py line
        from app.config import settings
        print(settings.mock_bedrock)
        """,
        "MOCK_AWS=false\n",
        tmp_path,
    )
    # load_dotenv ran first here, so .env still wins — but if the setdefault
    # ran BEFORE load_dotenv (as it used to), this would be True.
    assert out == "False"


def test_run_local_does_not_pin_mock_mode():
    """Guard the actual script: no defaulting of the mock switches ahead of
    load_dotenv."""
    raw = (ROOT / "scripts" / "run_local.py").read_text(encoding="utf-8")

    # Strip comments and the module docstring: they describe the old bug on
    # purpose, and matching that prose would fail the test for explaining
    # itself.
    import ast
    import io
    import tokenize

    tree = ast.parse(raw)
    docstring = ast.get_docstring(tree) or ""

    code_lines = []
    for tok in tokenize.generate_tokens(io.StringIO(raw).readline):
        if tok.type == tokenize.COMMENT:
            continue
        code_lines.append(tok.string)
    source = "".join(code_lines).replace(docstring, "")

    assert "load_dotenv(" in source
    dotenv_at = source.index("load_dotenv(")

    for switch in ("MOCK_AWS", "MOCK_BEDROCK"):
        marker = f'setdefault("{switch}"'
        assert marker not in source, f"{switch} must not be setdefault-ed"

    # Any explicit override must come after .env is loaded.
    forced = source.find('os.environ["MOCK_BEDROCK"]')
    if forced != -1:
        assert forced > dotenv_at, "--mock override must follow load_dotenv"
