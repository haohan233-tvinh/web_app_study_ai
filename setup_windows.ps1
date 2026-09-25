param(
    [ValidateSet('auto', 'cuda', 'cpu')][string]$Backend = 'auto',
    [switch]$VerifyOnly,
    [switch]$KeepArchives
)

$ErrorActionPreference = 'Stop'
$project = [System.IO.Path]::GetFullPath($PSScriptRoot)
if (-not [Environment]::Is64BitOperatingSystem -or $env:OS -ne 'Windows_NT') {
    throw 'Bộ cài này chỉ hỗ trợ Windows x64.'
}

function Find-Python312 {
    $preferred = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
    if (Test-Path -LiteralPath $preferred) { return $preferred }
    $launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($launcher) {
        $found = & $launcher.Source -3.12 -c 'import sys; print(sys.executable)' 2>$null
        if ($LASTEXITCODE -eq 0 -and $found -and (Test-Path -LiteralPath $found)) {
            return $found.Trim()
        }
    }
    return $null
}

function Find-Tesseract {
    $binary = Get-Command tesseract.exe -ErrorAction SilentlyContinue
    if ($binary) { return $binary.Source }
    $installed = Join-Path $env:ProgramFiles 'Tesseract-OCR\tesseract.exe'
    if (Test-Path -LiteralPath $installed) { return $installed }
    return $null
}

$python = Find-Python312
if (-not $python -and -not $VerifyOnly) {
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) {
        throw 'Thiếu Python 3.12 và winget. Cài Python 3.12 x64 từ python.org rồi chạy lại.'
    }
    Write-Host '[Cài] Python 3.12 x64 qua winget...'
    & $winget.Source install --id Python.Python.3.12 --exact --scope user --silent `
        --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { throw "winget cài Python thất bại (mã $LASTEXITCODE)." }
    $python = Find-Python312
}
if (-not $python) { throw 'Không tìm thấy Python 3.12 x64; cài Python rồi chạy lại.' }

$tesseract = Find-Tesseract
if (-not $tesseract -and -not $VerifyOnly) {
    $winget = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $winget) { throw 'Thiếu Tesseract OCR và winget; cài Tesseract OCR rồi chạy lại.' }
    Write-Host '[Cài] Tesseract OCR cho tiếng Việt...'
    & $winget.Source install --id UB-Mannheim.TesseractOCR --exact --silent `
        --accept-source-agreements --accept-package-agreements
    if ($LASTEXITCODE -ne 0) { throw "winget cài Tesseract thất bại (mã $LASTEXITCODE)." }
    $tesseract = Find-Tesseract
}
if (-not $tesseract) { throw 'Không tìm thấy Tesseract OCR; cài rồi chạy lại.' }
$tessdata = Join-Path (Split-Path $tesseract) 'tessdata\eng.traineddata'
if (-not (Test-Path -LiteralPath $tessdata)) { throw 'Tesseract OCR thiếu gói ngôn ngữ eng.traineddata.' }
Write-Host "[OK] Tesseract: $tesseract"

$venvPython = Join-Path $project '.venv\Scripts\python.exe'
if (-not $VerifyOnly -and -not (Test-Path -LiteralPath $venvPython)) {
    Write-Host '[Cài] Tạo môi trường Python riêng tại .venv...'
    & $python -m venv (Join-Path $project '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Không tạo được .venv.' }
}
if (Test-Path -LiteralPath $venvPython) { $python = $venvPython }

if ($Backend -eq 'auto') {
    $configured = $null
    if ($VerifyOnly) {
        $configured = (& $python -c "import json; print(json.load(open(r'$project\settings.json', encoding='utf-8')).get('device', ''))").Trim()
    }
    if ($configured -eq 'CPU') {
        $Backend = 'cpu'
    } else {
        $nvidia = Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue
        if ($nvidia) {
            $gpu = & $nvidia.Source --query-gpu=name --format=csv,noheader 2>$null
            $Backend = if ($LASTEXITCODE -eq 0 -and $gpu) { 'cuda' } else { 'cpu' }
        } else {
            $Backend = 'cpu'
        }
    }
}
Write-Host "[Thông tin] Backend: $Backend"

Push-Location $project
try {
    if (-not $VerifyOnly) {
        Write-Host '[Cài] Thư viện Python (OCR, giao diện, clipboard)...'
        & $python -m pip install --prefer-binary -r (Join-Path $project 'requirements.txt')
        if ($LASTEXITCODE -ne 0) { throw 'Cài thư viện Python thất bại; chạy lại khi có Internet.' }
    }
    $assetArgs = @('setup_assets.py', '--backend', $Backend)
    if ($VerifyOnly) { $assetArgs += '--check' }
    if ($KeepArchives) { $assetArgs += '--keep-archives' }
    & $python @assetArgs
    if ($LASTEXITCODE -ne 0) { throw 'Kiểm tra hoặc tải model/llama.cpp thất bại.' }

    & $python -c 'import PyQt6, keyboard, win32com.client, rapidocr_onnxruntime'
    if ($LASTEXITCODE -ne 0) { throw 'Thiếu thư viện V2 trong Python đang dùng.' }
    Write-Host '[OK] Thư viện V2 sẵn sàng.'
    & $python doctor.py
    if ($LASTEXITCODE -ne 0) { throw 'Bộ kiểm tra doctor.py chưa đạt; xem kết quả phía trên.' }
    Write-Host '[OK] Sẵn sàng. Mở fast_v2\run_fast_solver_visible.bat để thử.' -ForegroundColor Green
} finally {
    Pop-Location
}
