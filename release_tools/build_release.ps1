param([Parameter(Mandatory)][string]$Python, [Parameter(Mandatory)][string]$Models,
      [Parameter(Mandatory)][string]$Compiler, [Parameter(Mandatory)][string]$BuildDirectory,
      [string]$CondaPackages)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$prepareArgs = @('--output',$BuildDirectory,'--models',$Models)
if ($CondaPackages) { $prepareArgs += @('--conda-packages',$CondaPackages) }
& $Python "$PSScriptRoot\prepare_release.py" @prepareArgs
if ($LASTEXITCODE) { throw 'Payload preparation failed' }
$version = (& $Python -c "import sys;sys.path.insert(0,sys.argv[1]);from version import VERSION;print(VERSION)" $repo).Trim()
$runtimeVersion = (& $Python -c "import sys;sys.path.insert(0,sys.argv[1]);from version import RUNTIME_VERSION;print(RUNTIME_VERSION)" $repo).Trim()
foreach ($kind in 'setup','update','media') {
    & $Compiler "/DVersion=$version" "/DRuntimeVersion=$runtimeVersion" "/DKind=$kind" "/DPayload=$BuildDirectory\$kind" "/DOutput=$BuildDirectory\installers" "$PSScriptRoot\installer.iss"
    if ($LASTEXITCODE) { throw "Installer build failed: $kind" }
}
& $Python "$PSScriptRoot\make_manifest.py" "$BuildDirectory\installers"
if ($LASTEXITCODE) { throw 'Release manifest failed' }
