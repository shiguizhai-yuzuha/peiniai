param(
    [Parameter(Mandatory=$true)][string]$Version,
    [string]$Theme = "未命名"
)

$ErrorActionPreference = "Stop"
$Museum = "D:\项目备份\版本博物馆"
$Src    = "D:\Python学习\演示"
$Now    = Get-Date
$Stamp  = $Now.ToString("yyyyMMdd")
$Folder = Join-Path $Museum ("{0}_{1}_{2}" -f $Version, $Stamp, $Theme)

if (Test-Path $Folder) {
    Write-Host "已存在，未覆盖：" $Folder -ForegroundColor Yellow
    exit 1
}

$dst      = Join-Path $Folder "src"
$skipDir  = @('__pycache__', '.venv', '.git', '开发日志', 'exports', '.gradio', '.vscode')
$skipExt  = @('.db', '.bak', '.pyc', '.log', '.jpg', '.jpeg', '.png', '.webp', '.gif')

$count = 0
Get-ChildItem -Path $Src -Recurse -File | ForEach-Object {
    $rel   = $_.FullName.Substring($Src.Length).TrimStart('\')
    $parts = $rel -split '\\'
    $bad   = $false
    foreach ($p in $parts) { if ($skipDir -contains $p) { $bad = $true } }
    if ($bad) { return }
    if ($_.Name -eq '.env') { return }
    if ($skipExt -contains $_.Extension.ToLower()) { return }

    $target = Join-Path $dst $rel
    New-Item -ItemType Directory -Force -Path (Split-Path $target) | Out-Null
    Copy-Item -LiteralPath $_.FullName -Destination $target -Force
    $script:count++
}

# 说明.md
$tpl = Join-Path $Src "存档模板.md"
$readme = Join-Path $Folder "说明.md"
if (Test-Path $tpl) {
    $body = Get-Content $tpl -Raw -Encoding UTF8
} else {
    $body = "# {VERSION} · {DATE} · {THEME}`n`n## 这一版有什么`n`n- `n`n## 还没有什么`n`n- `n`n## 当时在想什么`n`n## 已知问题`n"
}
$body = $body.Replace("{VERSION}", $Version).Replace("{DATE}", $Now.ToString("yyyy-MM-dd")).Replace("{THEME}", $Theme).Replace("{DATETIME}", $Now.ToString("yyyy-MM-dd HH:mm"))
[IO.File]::WriteAllText($readme, $body, (New-Object Text.UTF8Encoding($true)))

# 追加 CHANGELOG
$log = Join-Path $Museum "CHANGELOG.md"
$line = "`n## $Version · $($Now.ToString('yyyy-MM-dd')) · $Theme`n`n- （在这里写这一版加了什么）`n"
Add-Content -Path $log -Value $line -Encoding UTF8

Write-Host ""
Write-Host "✅ 已存档" -ForegroundColor Green
Write-Host "   目录：$Folder"
Write-Host "   文件：$count 个"
Write-Host ""
Write-Host "接下来："
Write-Host "   1. 打开 $readme 填四段"
Write-Host "   2. CHANGELOG.md 已自动追加一行"
