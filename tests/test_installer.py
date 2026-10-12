from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows installer")
INSTALLER = Path(__file__).resolve().parents[1] / "install.ps1"


def ps_literal(value: str | Path) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def powershell(tmp_path: Path, content: str):
    path = tmp_path / "test.ps1"
    path.write_text(content, encoding="utf-8-sig")
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_installer_quotes_native_arguments_without_shell_interpretation(tmp_path):
    probe = tmp_path / "capture.py"
    target = tmp_path / "arguments.json"
    probe.write_text(
        "import json,sys\nfrom pathlib import Path\n"
        "Path(sys.argv[1]).write_text(json.dumps(sys.argv[2:]),encoding='utf-8')\n"
    )
    values = [
        "a b",
        'a"b',
        "trailing\\",
        "C:\\one two\\",
        "single'quote",
        "$(Write-Output evil)",
        "`backticks`",
        "日本語 [abc]",
    ]
    native_arguments = ",".join(ps_literal(v) for v in [probe, target, *values])
    content = f"""
. {ps_literal(INSTALLER)} -NoPause
$script:InstallLog = {ps_literal(tmp_path / "install.log")}
$result = Invoke-InstallNative {ps_literal(sys.executable)} @({native_arguments})
if ($result.Code -ne 0) {{ throw $result.Error }}
"""
    powershell(tmp_path, content)
    assert json.loads(target.read_text(encoding="utf-8")) == values


def test_installer_native_failure_is_logged_and_has_specific_remedy(tmp_path):
    probe = tmp_path / "fail.py"
    probe.write_text("import sys\nprint('permission denied',file=sys.stderr)\nsys.exit(7)\n")
    content = f"""
. {ps_literal(INSTALLER)} -NoPause
$script:InstallLog = {ps_literal(tmp_path / "install.log")}
$result = Invoke-InstallNative {ps_literal(sys.executable)} @({ps_literal(probe)})
if ($result.Code -ne 7) {{ throw 'Lost exit code' }}
Get-InstallFix $result.Error
"""
    output = powershell(tmp_path, content)
    assert "Close other Trainime windows" in output
    assert "permission denied" in (tmp_path / "install.log").read_text()
    assert "Exit: 7" in (tmp_path / "install.log").read_text()


def test_installer_json_is_atomic_utf8_and_readable_by_python(tmp_path):
    target = tmp_path / "receipt.json"
    powershell(
        tmp_path,
        f"""
. {ps_literal(INSTALLER)} -NoPause
Write-JsonFile {ps_literal(target)} @{{ status='first'; path='日本語' }}
Write-JsonFile {ps_literal(target)} @{{ status='second'; path='日本語' }}
""",
    )
    assert json.loads(target.read_text(encoding="utf-8")) == {"status": "second", "path": "日本語"}
    assert not list(tmp_path.glob("*.tmp"))


def test_installer_bootstrap_offline_failure_has_recovery(tmp_path):
    output = powershell(
        tmp_path,
        f"""
. {ps_literal(INSTALLER)} -NoPause -Offline
$script:InstallLog = {ps_literal(tmp_path / "install.log")}
$script:InstallerRoot = {ps_literal(tmp_path / "installer")}
try {{ Get-TrainimeUv -ForceBootstrap; throw 'Unexpected success' }}
catch {{
    if ($_.Exception.Message -notmatch 'Reconnect and run install.cmd once') {{ throw }}
    Write-Output $_.Exception.Message
}}
""",
    )
    assert "Reconnect and run install.cmd once" in output


def test_installer_recovers_builtin_modules_when_invoked_from_python(tmp_path):
    target = tmp_path / "check.txt"
    target.write_bytes(b"hash me")
    output = powershell(
        tmp_path,
        f"""
. {ps_literal(INSTALLER)} -NoPause
(Get-FileHash -LiteralPath {ps_literal(target)} -Algorithm SHA256).Hash
""",
    )
    import hashlib

    assert hashlib.sha256(b"hash me").hexdigest() in output.lower()


def test_installer_lock_conflict_retains_failure_receipt(tmp_path):
    home = tmp_path / "app"
    installer_root = home / "installer"
    installer_root.mkdir(parents=True)
    output = powershell(
        tmp_path,
        f"""
. {ps_literal(INSTALLER)} -NoPause -NoPath
$env:TRAINIME_HOME = {ps_literal(home)}
$lockPath = {ps_literal(installer_root / "install.lock")}
$lock = [IO.File]::Open($lockPath, 'OpenOrCreate','ReadWrite','None')
try {{
    $code = Invoke-TrainimeInstall
    if ($code -ne 1) {{ throw 'Installer ignored existing lock' }}
}} finally {{ $lock.Dispose() }}
""",
    )
    assert "Let it finish or close that installer window" in output
    report = next((home / "logs").glob("install-*.json"))
    assert json.loads(report.read_text(encoding="utf-8"))["status"] == "failed"
