# Compile launcher\Local3D.cs into build\Local3D.exe using the C# compiler that ships with Windows (no SDK needed).
#   powershell -ExecutionPolicy Bypass -File scripts\build_launcher.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$csc  = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path $csc)) { throw "csc.exe not found at $csc (the .NET Framework 4.x compiler is part of Windows)." }
$out  = Join-Path $root 'build'
New-Item -ItemType Directory -Force $out | Out-Null
$exe  = Join-Path $out 'Local3D.exe'
$icon = Join-Path $root 'assets\branding\icon.ico'
& $csc /nologo /target:winexe /optimize+ /platform:x64 "/out:$exe" "/win32icon:$icon" `
    /reference:System.Windows.Forms.dll /reference:System.Drawing.dll /reference:System.Web.Extensions.dll `
    (Join-Path $root 'launcher\Local3D.cs')
if ($LASTEXITCODE -ne 0) { throw "csc failed with exit code $LASTEXITCODE" }
Write-Host "Built $exe ($([math]::Round((Get-Item $exe).Length/1KB)) KB)"
