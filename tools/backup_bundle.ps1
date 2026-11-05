#Requires -Version 5.1
<#
.SYNOPSIS
    把 skills 仓库整体打包成 git bundle，并做完整性校验，用于异地容灾。

.DESCRIPTION
    bundle 是"带全部历史的单文件仓库"，可以像普通文件一样拷到网盘/U 盘。
    恢复方式：git clone <bundle 文件> <目标目录>

    本脚本会：
      1. git bundle create    —— 打包所有分支与 tag
      2. git bundle verify    —— 校验包内对象完整、依赖前置提交齐备
      3. git bundle list-heads—— 列出包内引用
      4. 打印体积、SHA-256、当前 HEAD，便于存档登记

    注意：函数参数刻意避开 PowerShell 保留/自动变量名
    （$Args / $Input / $Error / $Host 等），否则绑定会被内置变量抢走。

.EXAMPLE
    .\backup_bundle.ps1
    .\backup_bundle.ps1 -OutDir '<你的云盘>\skills' -Tag 'before-p4'
#>
[CmdletBinding()]
param(
    [string]$OutDir = '<你的备份目录>\skills-bundles',
    [string]$Tag    = '',
    [string]$RepoPath = ''
)

$ErrorActionPreference = 'Stop'

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)][string[]]$GitArgs,
        [string]$WorkingDirectory
    )
    $prev = (Get-Location).Path
    if ($WorkingDirectory) { Set-Location -LiteralPath $WorkingDirectory }
    try {
        $ErrorActionPreference = 'Continue'
        $out = & git @GitArgs 2>&1
        $code = $LASTEXITCODE
    }
    finally {
        Set-Location -LiteralPath $prev
    }
    return [pscustomobject]@{
        Output = (($out | ForEach-Object { "$_" }) -join "`n").Trim()
        Code   = $code
    }
}

# ---- 定位仓库 ----
if (-not $RepoPath) { $RepoPath = (Get-Location).Path }
Write-Host "探测起点  : $RepoPath"

$probe = Invoke-Git -GitArgs @('rev-parse', '--show-toplevel') -WorkingDirectory $RepoPath
if ($probe.Code -ne 0 -or -not $probe.Output) {
    Write-Host "✗ 当前目录不在 git 仓库内（git exit=$($probe.Code)）" -ForegroundColor Red
    Write-Host "  git 输出: $($probe.Output)" -ForegroundColor DarkGray
    exit 2
}
$root = $probe.Output
if (-not (Test-Path -LiteralPath $root)) {
    Write-Host "✗ 解析出的仓库路径不可访问: $root" -ForegroundColor Red
    exit 2
}
Write-Host "仓库      : $root"

$head   = (Invoke-Git -GitArgs @('rev-parse', '--short', 'HEAD') -WorkingDirectory $root).Output
$branch = (Invoke-Git -GitArgs @('rev-parse', '--abbrev-ref', 'HEAD') -WorkingDirectory $root).Output
$dirty  = (Invoke-Git -GitArgs @('status', '--porcelain') -WorkingDirectory $root).Output
Write-Host "分支/HEAD : $branch / $head"
if ($dirty) {
    Write-Host "⚠ 工作树有未提交改动，bundle 只包含已提交内容：" -ForegroundColor Yellow
    ($dirty -split "`n") | ForEach-Object { Write-Host "    $_" -ForegroundColor Yellow }
}

# ---- 准备输出目录 ----
if (-not (Test-Path -LiteralPath $OutDir)) {
    New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
    Write-Host "已创建输出目录: $OutDir"
}

$stamp  = Get-Date -Format 'yyyyMMdd'
$suffix = if ($Tag) { "_$Tag" } else { '' }
$file   = Join-Path $OutDir "skills_backup_$stamp$suffix.bundle"

if (Test-Path -LiteralPath $file) {
    $file = Join-Path $OutDir ("skills_backup_{0}_{1}{2}.bundle" -f $stamp, (Get-Date -Format 'HHmmss'), $suffix)
    Write-Host "同名已存在，改用: $file" -ForegroundColor Yellow
}

# ---- 1) 打包 ----
Write-Host ""
Write-Host "[1/4] git bundle create ..." -ForegroundColor Cyan
$r = Invoke-Git -GitArgs @('bundle', 'create', $file, '--all') -WorkingDirectory $root
if ($r.Code -ne 0 -or -not (Test-Path -LiteralPath $file)) {
    Write-Host "✗ 打包失败（exit=$($r.Code)）：" -ForegroundColor Red
    Write-Host $r.Output -ForegroundColor Red
    exit 3
}
Write-Host "  OK  $file"

# ---- 2) 校验 ----
Write-Host "[2/4] git bundle verify ..." -ForegroundColor Cyan
$r = Invoke-Git -GitArgs @('bundle', 'verify', $file) -WorkingDirectory $root
if ($r.Code -ne 0) {
    Write-Host "✗ 校验失败，bundle 不可信，已删除：" -ForegroundColor Red
    Write-Host $r.Output -ForegroundColor Red
    Remove-Item -LiteralPath $file -Force
    exit 4
}
($r.Output -split "`n") | ForEach-Object { Write-Host "    $_" }

# ---- 3) 列出引用 ----
Write-Host "[3/4] git bundle list-heads ..." -ForegroundColor Cyan
$r = Invoke-Git -GitArgs @('bundle', 'list-heads', $file) -WorkingDirectory $root
($r.Output -split "`n") | ForEach-Object { Write-Host "    $_" }

# ---- 4) 指纹 ----
Write-Host "[4/4] 指纹 ..." -ForegroundColor Cyan
$item = Get-Item -LiteralPath $file
$sha  = (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash
$count = (Invoke-Git -GitArgs @('rev-list', '--count', 'HEAD') -WorkingDirectory $root).Output

Write-Host ""
Write-Host "================ 备份完成 ================" -ForegroundColor Green
Write-Host ("文件      : {0}" -f $item.FullName)
Write-Host ("体积      : {0:N2} MB ({1:N0} B)" -f ($item.Length / 1MB), $item.Length)
Write-Host ("SHA-256   : {0}" -f $sha)
Write-Host ("分支/HEAD : {0} / {1}" -f $branch, $head)
Write-Host ("提交总数  : {0}" -f $count)
Write-Host ("校验      : git bundle verify 通过")
Write-Host ""
Write-Host "恢复到新目录：" -ForegroundColor Cyan
Write-Host ("    git clone `"{0}`" `"<目标目录>`"" -f $item.FullName)
Write-Host ""
Write-Host "容灾建议：" -ForegroundColor Cyan
Write-Host "    把 .bundle 文件拷到网盘（OneDrive / 坚果云 / 百度网盘皆可）。"
Write-Host "    体积小、自包含全部历史，恢复时不需要任何前置提交。"
Write-Host "    建议每月一次 + 重大改动前一次。"
