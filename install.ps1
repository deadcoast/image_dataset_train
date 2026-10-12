# Trainime's Windows installer. Works with Windows PowerShell 5.1 and PowerShell 7.
[CmdletBinding()]
param(
    [switch]$Repair,
    [switch]$RuntimeOnly,
    [switch]$Offline,
    [switch]$NoPause,
    [switch]$NoPath,
    [switch]$FromLauncher
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
# Python launched from PowerShell 7 can inherit its module paths into Windows
# PowerShell 5.1. Prefer this host's built-ins before any inherited modules.
if ($PSVersionTable.PSVersion.Major -lt 6) {
    $env:PSModulePath = (Join-Path $PSHOME 'Modules') + ';' + $env:PSModulePath
}

function ConvertTo-NativeArgument([string]$Value) {
    # Windows CommandLineToArgvW quoting, including trailing backslashes.
    $escaped = [regex]::Replace($Value, '(\\*)"', {
        param($match)
        return ('\' * ($match.Groups[1].Length * 2 + 1)) + '"'
    })
    $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
    return '"' + $escaped + '"'
}

function Protect-LogText([string]$Text) {
    $Text = $Text -replace '(?i)(https?://)[^/\s:@]+:[^/\s@]+@', '$1[REDACTED]@'
    $Text = $Text -replace '(?i)(bearer\s+)[^\s"&,;]+', '$1[REDACTED]'
    return $Text -replace '(?i)((?:token|api[_-]?key|password|secret|signature)[=:])[^\s"&,;]+', '$1[REDACTED]'
}

function Write-InstallLog([string]$Text) {
    $entry = '[' + [DateTime]::UtcNow.ToString('o') + '] ' + (Protect-LogText $Text) + "`r`n"
    [IO.File]::AppendAllText($script:InstallLog, $entry, [Text.UTF8Encoding]::new($false))
}

function Write-InstallStep([string]$Text) {
    $script:InstallStep = $Text
    Write-Host $Text
    Write-InstallLog $Text
}

function Invoke-InstallNative([string]$File, [string[]]$Arguments, [int]$TimeoutSeconds = 900) {
    Write-InstallLog ('Run: ' + $File + ' ' + (($Arguments | ForEach-Object { ConvertTo-NativeArgument $_ }) -join ' '))
    $start = [Diagnostics.ProcessStartInfo]::new()
    $start.FileName = $File
    $start.Arguments = ($Arguments | ForEach-Object { ConvertTo-NativeArgument $_ }) -join ' '
    $start.UseShellExecute = $false
    $start.CreateNoWindow = $true
    $start.WindowStyle = [Diagnostics.ProcessWindowStyle]::Hidden
    $start.RedirectStandardOutput = $true
    $start.RedirectStandardError = $true
    $start.StandardOutputEncoding = [Text.Encoding]::UTF8
    $start.StandardErrorEncoding = [Text.Encoding]::UTF8
    $process = [Diagnostics.Process]::new()
    $process.StartInfo = $start
    try {
        [void]$process.Start()
        $stdout = $process.StandardOutput.ReadToEndAsync()
        $stderr = $process.StandardError.ReadToEndAsync()
        if (-not $process.WaitForExit($TimeoutSeconds * 1000)) {
            $process.Kill()
            throw "The installer step timed out. Reconnect and rerun install.cmd; cached downloads are retained."
        }
        $out = $stdout.GetAwaiter().GetResult()
        $err = $stderr.GetAwaiter().GetResult()
        Write-InstallLog ($out + "`n" + $err + "`nExit: " + $process.ExitCode)
        return [pscustomobject]@{ Code = $process.ExitCode; Output = $out.Trim(); Error = $err.Trim() }
    } finally {
        $process.Dispose()
    }
}

function Invoke-UV([string[]]$Arguments) {
    if ($Offline) { $Arguments += '--offline' }
    $result = Invoke-InstallNative $script:Uv $Arguments
    if ($result.Code -ne 0) {
        # A failed cache/archive gets a fresh cache; the original is retained.
        if (($result.Error + $result.Output) -match '(?i)corrupt|extract|invalid.*(zip|archive)|cache.*(denied|error)') {
            $env:UV_CACHE_DIR = Join-Path $script:InstallerRoot ('cache-recovery-' + [Guid]::NewGuid().ToString('N'))
            Write-Host 'The package cache failed verification. Retrying with a fresh cache.'
            Write-InstallLog ('Retry cache: ' + $env:UV_CACHE_DIR)
        } else {
            Write-Host 'That step did not finish. Retrying once with the available downloads.'
        }
        $result = Invoke-InstallNative $script:Uv $Arguments
    }
    if ($result.Code -ne 0) { throw ($result.Error + "`n" + $result.Output) }
    return $result.Output
}

function Get-TrainimeUv([switch]$ForceBootstrap) {
    $private = Join-Path $script:InstallerRoot 'tools\uv.exe'
    if (-not $ForceBootstrap) {
        $candidates = @($private)
        $command = Get-Command uv -ErrorAction SilentlyContinue
        if ($command) { $candidates += $command.Source }
        $candidates += (Join-Path $env:USERPROFILE '.local\bin\uv.exe')
        foreach ($candidate in $candidates) {
            if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                try {
                    $probe = Invoke-InstallNative $candidate @('--version') 20
                    if ($probe.Code -eq 0 -and $probe.Output -match '^uv (\d+\.\d+\.\d+)' -and
                        [version]$Matches[1] -ge [version]'0.9.5') { return $candidate }
                } catch { Write-InstallLog $_.Exception.ToString() }
            }
        }
    }
    if ($Offline) { throw 'The package manager is not cached. Reconnect and run install.cmd once; later repairs can use -Offline.' }
    $architecture = $env:PROCESSOR_ARCHITEW6432
    if (-not $architecture) { $architecture = $env:PROCESSOR_ARCHITECTURE }
    if ($architecture -eq 'ARM64') {
        $asset = 'uv-aarch64-pc-windows-msvc.zip'
        $digest = '4c615aa19e37b2ec7da3370a25a562bb0061ab005081e4539702c059715dc2b0'
    } elseif ($architecture -eq 'AMD64') {
        $asset = 'uv-x86_64-pc-windows-msvc.zip'
        $digest = '515dc53d7553f1357d0abc1f70acd921fbb9e30230b1d9a08737236daa6ee920'
    } else {
        throw 'The local tagger requires 64-bit Windows. Run this installer on x64 or ARM64 Windows; 32-bit Windows cannot load its native runtime.'
    }
    Write-Host 'Preparing the package manager automatically...'
    $download = Join-Path $script:InstallerRoot ('bootstrap-' + [Guid]::NewGuid().ToString('N'))
    [void](New-Item -ItemType Directory -Path $download -Force)
    $archive = Join-Path $download $asset
    $uri = 'https://github.com/astral-sh/uv/releases/download/0.9.5/' + $asset
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    for ($attempt = 1; $attempt -le 2; $attempt++) {
        try {
            Invoke-WebRequest -UseBasicParsing -Uri $uri -OutFile $archive -TimeoutSec 120
            if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $digest) {
                throw 'Package manager download checksum mismatch. The download was retained; retry on a reliable connection.'
            }
            break
        } catch {
            Write-InstallLog $_.Exception.ToString()
            if ($attempt -eq 2) { throw }
        }
    }
    Expand-Archive -LiteralPath $archive -DestinationPath (Join-Path $download 'expanded')
    $binary = Get-ChildItem -LiteralPath (Join-Path $download 'expanded') -Recurse -File -Filter uv.exe | Select-Object -First 1
    if (-not $binary) { throw 'Verified package manager archive contained no uv.exe. Keep the installer log and run install.cmd again.' }
    [void](New-Item -ItemType Directory -Path (Split-Path $private) -Force)
    if (Test-Path -LiteralPath $private) {
        # The checked absolute file is inside this installer root; retain it as evidence.
        if (-not [IO.Path]::GetFullPath($private).StartsWith([IO.Path]::GetFullPath($script:InstallerRoot) + '\', [StringComparison]::OrdinalIgnoreCase)) {
            throw 'Unsafe package manager repair path. Use an ordinary TRAINIME_HOME directory and retry.'
        }
        Move-Item -LiteralPath $private -Destination ($private + '.previous-' + [Guid]::NewGuid().ToString('N'))
    }
    Copy-Item -LiteralPath $binary.FullName -Destination $private
    $probe = Invoke-InstallNative $private @('--version') 20
    if ($probe.Code -ne 0) { throw 'The verified package manager could not start. Check antivirus quarantine for uv.exe and rerun install.cmd.' }
    return $private
}

function Get-InstallFix([string]$Message) {
    switch -Regex ($Message) {
        '(?i)no space|disk.*full' { return 'Free space on the drive named in the log, then rerun install.cmd. No image or model data is deleted by this installer.' }
        '(?i)denied|permission|being used|winerror 32' { return 'Close other Trainime windows and retry install.cmd. If the folder is read-only, set TRAINIME_HOME to a folder you own and retry. Administrator access is not required.' }
        '(?i)certificate|TLS|SSL' { return 'Correct the system clock and proxy/certificate configuration, then rerun install.cmd. Certificate checks remain enabled.' }
        '(?i)network|connect|resolve|download|timed out|offline' { return 'Reconnect and check your proxy, then rerun install.cmd. If all downloads were previously cached, run install.cmd -Offline.' }
        '(?i)lock.*(outdated|update)|lockfile.*(change|update)' { return 'The source files and dependency lock do not match. Extract a complete current Trainime checkout, then run its install.cmd. The existing installation is retained until the new runtime is verified.' }
        default { return 'Rerun install.cmd to repair the installation. If it fails again, keep the error log printed below; it includes the failed command and native error output.' }
    }
}

function Write-JsonFile([string]$Path, $Value) {
    $temporary = $Path + '.' + [Guid]::NewGuid().ToString('N') + '.tmp'
    [IO.File]::WriteAllText($temporary, ($Value | ConvertTo-Json -Depth 8), [Text.UTF8Encoding]::new($false))
    if (Test-Path -LiteralPath $Path) {
        [IO.File]::Replace($temporary, $Path, ($Path + '.previous-' + [Guid]::NewGuid().ToString('N')))
    } else {
        [IO.File]::Move($temporary, $Path)
    }
}

function Invoke-TrainimeInstall {
    $script:InstallStep = 'Preparing installation'
    $homePath = $env:TRAINIME_HOME
    if (-not $homePath) { $homePath = Join-Path $env:LOCALAPPDATA 'trainime' }
    $homePath = [IO.Path]::GetFullPath($homePath)
    $script:InstallerRoot = Join-Path $homePath 'installer'
    $logRoot = Join-Path $homePath 'logs'
    $identifier = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffZ') + '-' + [Guid]::NewGuid().ToString('N').Substring(0,8)
    try { [void](New-Item -ItemType Directory -Path $logRoot -Force) }
    catch {
        $logRoot = Join-Path ([IO.Path]::GetTempPath()) 'trainime\logs'
        [void](New-Item -ItemType Directory -Path $logRoot -Force)
        Write-Host ('Application log folder unavailable; using ' + $logRoot)
    }
    $script:InstallLog = Join-Path $logRoot ('install-' + $identifier + '.log')
    Write-InstallLog ('Trainime installer started. Repair=' + $Repair + '; Offline=' + $Offline)
    $installLock = $null
    $savedEnvironment = @{}
    foreach ($name in @('UV_CACHE_DIR','UV_PYTHON_DOWNLOADS','PYTHONUTF8','TRAINIME_HOME','UV_TOOL_DIR','UV_TOOL_BIN_DIR')) {
        $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
    }
    try {
        [void](New-Item -ItemType Directory -Path $script:InstallerRoot -Force)
        try {
            $installLock = [IO.File]::Open((Join-Path $script:InstallerRoot 'install.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
        } catch { throw 'Another installer is using install.lock. Let it finish or close that installer window, then rerun install.cmd.' }
        $work = Join-Path $script:InstallerRoot ('builds\' + $identifier)
        [void](New-Item -ItemType Directory -Path $work -Force)
        $env:TRAINIME_HOME = $homePath
        $env:PYTHONUTF8 = '1'
        $env:UV_PYTHON_DOWNLOADS = 'automatic'
        $env:UV_CACHE_DIR = Join-Path $script:InstallerRoot 'cache'
        if (Test-Path -LiteralPath (Join-Path $PSScriptRoot '.cache\uv')) { $env:UV_CACHE_DIR = Join-Path $PSScriptRoot '.cache\uv' }
        $receiptPath = Join-Path $homePath 'install.json'
        $receipt = $null
        if (Test-Path -LiteralPath $receiptPath) {
            try { $receipt = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json }
            catch { Write-InstallLog ('Previous install receipt unreadable: ' + $_.Exception.Message) }
        }
        Write-InstallStep '[1/5] Preparing installation tools...'
        $script:Uv = Get-TrainimeUv

        if ($Repair -and $receipt -and (Test-Path -LiteralPath $receipt.wheel)) {
            if ((Get-FileHash -LiteralPath $receipt.wheel -Algorithm SHA256).Hash.ToLowerInvariant() -ne $receipt.wheel_sha256) {
                throw 'The retained installer wheel failed its checksum. Run install.cmd from a fresh Trainime checkout to replace the damaged repair package.'
            }
            $wheel = $receipt.wheel
            $constraints = $receipt.constraints
            if ($receipt.constraints_sha256 -and
                (Get-FileHash -LiteralPath $constraints -Algorithm SHA256).Hash.ToLowerInvariant() -ne $receipt.constraints_sha256) {
                throw 'The retained dependency pins changed. Run install.cmd from the Trainime checkout to rebuild the verified repair package.'
            }
            if ($receipt.cache -and (Test-Path -LiteralPath $receipt.cache)) { $env:UV_CACHE_DIR = $receipt.cache }
            if ($receipt.tools) { $env:UV_TOOL_DIR = $receipt.tools }
            if ($receipt.bin) { $env:UV_TOOL_BIN_DIR = $receipt.bin }
            Write-InstallStep '[2/5] Using the verified local repair package...'
        } else {
            if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'pyproject.toml'))) {
                throw 'The source package is incomplete. Extract the entire Trainime download, keeping install.cmd, install.ps1, pyproject.toml, and src together, then run install.cmd.'
            }
            Write-InstallStep '[2/5] Preparing the application package...'
            $dist = Join-Path $work 'dist'
            [void](Invoke-UV @('build', $PSScriptRoot, '--out-dir', $dist))
            $wheel = (Get-ChildItem -LiteralPath $dist -Filter '*.whl' | Select-Object -First 1).FullName
            $constraints = Join-Path $work 'constraints.txt'
            $exportArgs = @('export','--project',$PSScriptRoot,'--locked','--extra','tag-cpu','--no-dev','--no-emit-project','--no-hashes','--format','requirements-txt','--output-file',$constraints)
            if ($Offline) { $exportArgs += '--offline' }
            $export = Invoke-InstallNative $script:Uv $exportArgs
            if ($export.Code -ne 0) {
                # Resolve changed/missing locks in an isolated copy, never rewrite the checkout.
                Write-Host 'Refreshing installation dependency pins in a temporary copy...'
                $resolveProject = Join-Path $work 'resolve-project'
                [void](New-Item -ItemType Directory -Path $resolveProject -Force)
                foreach ($name in @('pyproject.toml','uv.lock','README.md','.python-version')) {
                    $candidate = Join-Path $PSScriptRoot $name
                    if (Test-Path -LiteralPath $candidate) { Copy-Item -LiteralPath $candidate -Destination $resolveProject }
                }
                [void](Invoke-UV @('export','--project',$resolveProject,'--extra','tag-cpu','--no-dev','--no-emit-project','--no-hashes','--format','requirements-txt','--output-file',$constraints))
            }
        }
        $requirement = 'image-dataset-train[tag-cpu] @ ' + ([Uri]$wheel).AbsoluteUri
        # uv 0.9.x splits spaces in raw constraint paths; a file URI preserves them.
        $constraintUri = ([Uri]$constraints).AbsoluteUri
        Write-InstallStep '[3/5] Preparing Python and checking the new runtime...'
        $verification = Join-Path $work 'verified-runtime'
        [void](Invoke-UV @('venv','--python','3.12',$verification))
        $verifyPython = Join-Path $verification 'Scripts\python.exe'
        [void](Invoke-UV @('pip','install','--python',$verifyPython,'--constraint',$constraintUri,$requirement))
        $probe = Invoke-InstallNative $verifyPython @('-m','image_dataset_train.bootstrap','doctor','--runtime-only','--dryrun','--json')
        if ($probe.Code -ne 0) { throw ('Runtime verification failed before installation: ' + $probe.Output + $probe.Error) }

        Write-InstallStep '[4/5] Installing the trainime command...'
        if ($RuntimeOnly -and $receipt -and (Test-Path -LiteralPath $receipt.python)) {
            # The doctor's running .exe cannot be replaced on Windows. Repair its
            # dependencies and exact package files without touching that launcher.
            $bin = $receipt.bin
            $tools = $receipt.tools
            [void](Invoke-UV @('pip','install','--python',$receipt.python,'--reinstall','--requirement',$constraintUri))
            $packageTarget = Join-Path $tools 'image-dataset-train\Lib\site-packages'
            $restore = Invoke-InstallNative $verifyPython @('-m','image_dataset_train.repair_package',$wheel,$packageTarget)
            if ($restore.Code -ne 0) { throw ('Application-file repair failed: ' + $restore.Error) }
        } else {
            $arguments = @('tool','install','--python','3.12','--constraints',$constraintUri,$requirement)
            if ($Repair) { $arguments += '--reinstall' } else { $arguments += @('--reinstall-package','image-dataset-train') }
            [void](Invoke-UV $arguments)
            $bin = (Invoke-UV @('tool','dir','--bin')).Trim()
            $tools = (Invoke-UV @('tool','dir')).Trim()
        }
        $python = Join-Path $tools 'image-dataset-train\Scripts\python.exe'
        $exe = Join-Path $bin 'trainime.exe'
        $probe = Invoke-InstallNative $python @('-m','image_dataset_train.bootstrap','doctor','--runtime-only','--dryrun','--json')
        if ($probe.Code -ne 0) { throw ('Installed runtime check failed: ' + $probe.Output + $probe.Error) }
        $version = Invoke-InstallNative $exe @('--version') 30
        if ($version.Code -ne 0) { throw ('Command startup failed: ' + $version.Error) }

        Write-InstallStep '[5/5] Registering the command and keeping recovery tools...'
        foreach ($filename in @('install.ps1','install.cmd')) {
            $original = Join-Path $PSScriptRoot $filename
            $target = Join-Path $script:InstallerRoot $filename
            if ([IO.Path]::GetFullPath($original) -ne [IO.Path]::GetFullPath($target)) {
                if (Test-Path -LiteralPath $target) { Copy-Item -LiteralPath $target -Destination (Join-Path $work ($filename + '.previous')) }
                Copy-Item -LiteralPath $original -Destination $target -Force
            }
        }
        if (-not $NoPath) {
            $userPath = [Environment]::GetEnvironmentVariable('Path','User')
            Write-JsonFile (Join-Path $work 'path-before.json') @{ path = $userPath }
            $env:PATH = $bin + ';' + $env:PATH
            # Broadcast through the dependency-free application helper.
            $pathScript = Join-Path $work 'register_path.py'
            [IO.File]::WriteAllText($pathScript, "import sys`nfrom pathlib import Path`nfrom image_dataset_train.doctor import register_user_path`nregister_user_path(Path(sys.argv[1]))`n")
            $pathResult = Invoke-InstallNative $python @($pathScript,$bin) 30
            if ($pathResult.Code -ne 0) { throw ('PATH registration failed: ' + $pathResult.Error) }
        }
        if (Test-Path -LiteralPath $receiptPath) { Copy-Item -LiteralPath $receiptPath -Destination (Join-Path $work 'install.previous.json') }
        $newReceipt = @{
            schema_version = 1; version = $version.Output; bin = $bin; tools = $tools;
            path_registered = (-not $NoPath);
            python = $python; uv = $script:Uv; wheel = $wheel; constraints = $constraints;
            cache = $env:UV_CACHE_DIR; source = $PSScriptRoot;
            installed_at = [DateTime]::UtcNow.ToString('o'); log = $script:InstallLog;
            wheel_sha256 = (Get-FileHash -LiteralPath $wheel -Algorithm SHA256).Hash.ToLowerInvariant();
            constraints_sha256 = (Get-FileHash -LiteralPath $constraints -Algorithm SHA256).Hash.ToLowerInvariant();
            installer_sha256 = (Get-FileHash -LiteralPath (Join-Path $script:InstallerRoot 'install.ps1') -Algorithm SHA256).Hash.ToLowerInvariant()
        }
        Write-JsonFile $receiptPath $newReceipt
        Write-JsonFile (Join-Path $logRoot ('install-' + $identifier + '.json')) @{ status = 'completed'; version = $version.Output; command = $exe; log = $script:InstallLog }
        Write-Host ''
        if ($NoPath) { Write-Host ($version.Output + ' installed. PATH registration was skipped.') }
        else { Write-Host ($version.Output + ' installed. Open a new terminal and type: trainime') }
        Write-Host ('Launch now: & "' + $exe + '"')
        Write-Host 'Repair problems: trainime doctor --fix'
        Write-Host ('Install log: ' + $script:InstallLog)
        return 0
    } catch {
        $message = $_.Exception.ToString()
        $fix = Get-InstallFix $message
        Write-InstallLog ('FAILED: ' + $script:InstallStep + "`n" + $message + "`n" + $_.ScriptStackTrace)
        Write-JsonFile (Join-Path $logRoot ('install-' + $identifier + '.json')) @{ status = 'failed'; stage = $script:InstallStep; error = (Protect-LogText $message); fix = $fix; log = $script:InstallLog }
        Write-Host ''
        Write-Host ('Could not complete: ' + $script:InstallStep) -ForegroundColor Red
        Write-Host (Protect-LogText $_.Exception.Message)
        Write-Host ('Fix: ' + $fix)
        Write-Host ('Error log: ' + $script:InstallLog)
        return 1
    } finally {
        if ($installLock) { $installLock.Dispose() }
        foreach ($name in $savedEnvironment.Keys) { [Environment]::SetEnvironmentVariable($name,$savedEnvironment[$name],'Process') }
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    try { $result = Invoke-TrainimeInstall }
    catch {
        Write-Host ('Installer setup failed: ' + $_.Exception.Message) -ForegroundColor Red
        Write-Host 'Fix: set TRAINIME_HOME to a writable folder you own and rerun install.cmd. If even the temporary folder cannot be written, free disk space or unlock that folder first.'
        $result = 1
    }
    if ($FromLauncher -and -not $NoPause) { [void](Read-Host 'Press Enter to close') }
    exit $result
}
