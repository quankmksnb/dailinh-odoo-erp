<#
.SYNOPSIS
    Xóa DB cũ, tạo lại DB sạch và nạp đầy đủ dữ liệu demo (module dl_demo).

.DESCRIPTION
    Một lệnh để có lại "DB sạch + data test liên kết chuẩn":
      1. Drop + create lại database (mặc định dlm_dev) — dùng psycopg2 trong venv.
      2. Chạy Odoo cài toàn bộ module + dl_demo (--stop-after-init -i dl_demo).
         dl_demo phụ thuộc 7 module nên Odoo tự cài kèm, rồi post_init_hook seed
         RFQ / BOM / báo giá / đơn / phê duyệt phủ mọi trạng thái.

    ⚠️  QUAN TRỌNG: Server Odoo của dự án chạy qua trình debug VS Code (debugpy)
        và TỰ respawn. Trước khi chạy script này hãy STOP phiên debug trong VS Code
        (nếu không, debugpy đang giữ kết nối tới DB → không drop được, hoặc respawn
        chèn vào giữa chừng). Seed xong thì Start lại debug như bình thường.

.PARAMETER Database
    Tên DB cần tạo lại. Mặc định đọc db_name trong odoo.conf (dlm_dev).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts\reset_demo_db.ps1
#>

param(
    [string]$Database
)

$ErrorActionPreference = "Stop"

# ── Đường dẫn ────────────────────────────────────────────────────────────────
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Conf     = Join-Path $RepoRoot "odoo.conf"
$Python   = Join-Path $RepoRoot "venv\Scripts\python.exe"
$OdooBin  = Join-Path $RepoRoot "odoo-17.0\odoo-bin"
$Recreate = Join-Path $PSScriptRoot "_recreate_db.py"

foreach ($p in @($Conf, $Python, $OdooBin, $Recreate)) {
    if (-not (Test-Path $p)) {
        throw "Không tìm thấy: $p"
    }
}

# ── Đọc thông số DB từ odoo.conf ─────────────────────────────────────────────
function Get-ConfValue([string]$key, [string]$default) {
    $line = Select-String -Path $Conf -Pattern "^\s*$key\s*=" | Select-Object -First 1
    if ($null -eq $line) { return $default }
    $val = ($line.Line -split "=", 2)[1].Trim()
    if ([string]::IsNullOrWhiteSpace($val)) { return $default }
    return $val
}

$DbName = if ($Database) { $Database } else { Get-ConfValue "db_name" "dlm_dev" }
$DbHost = Get-ConfValue "db_host" "localhost"
$DbPort = Get-ConfValue "db_port" "5432"
$DbUser = Get-ConfValue "db_user" "odoo"
$DbPass = Get-ConfValue "db_password" "odoo"

Write-Host ""
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "  RESET DB DEMO — Dai Linh ERP" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host ("  DB     : {0}  ({1}@{2}:{3})" -f $DbName, $DbUser, $DbHost, $DbPort)
Write-Host "  Repo   : $RepoRoot"
Write-Host ""
Write-Host "  ⚠️  Hãy STOP phiên debug VS Code trước khi tiếp tục." -ForegroundColor Yellow
Write-Host ""
$answer = Read-Host "  Gõ 'yes' để XÓA và tạo lại DB '$DbName'"
if ($answer -ne "yes") {
    Write-Host "  Đã hủy." -ForegroundColor Yellow
    return
}

# ── Bước 1: drop + create DB sạch ────────────────────────────────────────────
Write-Host ""
Write-Host "[1/2] Tạo lại database sạch..." -ForegroundColor Green
& $Python $Recreate $DbHost $DbPort $DbUser $DbPass $DbName
if ($LASTEXITCODE -ne 0) { throw "Tạo lại DB thất bại (exit $LASTEXITCODE)." }

# ── Bước 2: cài module + seed dl_demo ────────────────────────────────────────
Write-Host ""
Write-Host "[2/2] Cài module + nạp dữ liệu demo (có thể mất vài phút)..." -ForegroundColor Green
# dl_purchase KHÔNG nằm trong depends của dl_demo (dl_demo không seed dữ liệu mua
# hàng) nên phải liệt kê tay — thiếu nó thì DB dựng ra không có màn Mua hàng.
& $Python $OdooBin -c $Conf -d $DbName --stop-after-init -i dl_demo,dl_purchase --without-demo=all
if ($LASTEXITCODE -ne 0) { throw "Cài đặt/seed thất bại (exit $LASTEXITCODE)." }

Write-Host ""
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "  ✅ XONG. DB '$DbName' đã sạch + có dữ liệu demo." -ForegroundColor Green
Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "  → Start lại phiên debug VS Code rồi mở http://127.0.0.1:8069"
Write-Host "  → Tài khoản demo (mật khẩu chung: 123456):"
Write-Host "      CEO           ceo@gmail.com"
Write-Host "      Admin IT      admin.it@gmail.com"
Write-Host "      Trưởng KD     truongkd@gmail.com"
Write-Host "      BA / Sales    ba@gmail.com"
Write-Host "      Kỹ thuật      kythuat@gmail.com"
Write-Host "      Kế toán       ketoan@gmail.com"
Write-Host "      Mua hàng      muahang@gmail.com"
Write-Host ""
