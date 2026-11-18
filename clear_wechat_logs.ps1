$ErrorActionPreference = 'Stop'
# The sole log directory explicitly requested by the user. Never touch db_storage,
# chat attachments, Windows event logs, or other applications' logs.
$logTarget = [IO.Path]::GetFullPath((Join-Path $env:APPDATA 'Tencent\WeChat\xlog'))
$allowedTarget = [IO.Path]::GetFullPath((Join-Path ([Environment]::GetFolderPath('ApplicationData')) 'Tencent\WeChat\xlog'))
if ($logTarget -ne $allowedTarget -or [IO.Path]::GetFileName($logTarget) -ne 'xlog') { throw 'Log path verification failed' }
if (-not (Test-Path -LiteralPath $logTarget)) {
    Write-Output 'NOT_PRESENT: The specified WeChat xlog directory does not exist.'
    exit 0
}
$resolvedTarget = (Resolve-Path -LiteralPath $logTarget).Path
if ($resolvedTarget -ne $allowedTarget) { throw 'Resolved log target is outside the allowed directory' }
if ((Get-Item -LiteralPath $resolvedTarget).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw 'Refusing a reparse point log directory' }
$linkedItems = Get-ChildItem -LiteralPath $resolvedTarget -Force -Recurse | Where-Object { $_.Attributes -band [IO.FileAttributes]::ReparsePoint }
if ($linkedItems) { throw 'Refusing log tree containing reparse points' }
$children = @(Get-ChildItem -LiteralPath $resolvedTarget -Force)
foreach ($child in $children) {
    $absoluteChild = [IO.Path]::GetFullPath($child.FullName)
    if (-not $absoluteChild.StartsWith($allowedTarget + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Child outside allowed log directory' }
    Remove-Item -LiteralPath $absoluteChild -Recurse -Force
}
if (@(Get-ChildItem -LiteralPath $resolvedTarget -Force).Count -ne 0) { throw 'Some log entries remain' }
Write-Output ('CLEARED: Removed {0} log entries from the requested xlog directory.' -f $children.Count)
