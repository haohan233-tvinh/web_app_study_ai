$ErrorActionPreference = 'Stop'
$project = [System.IO.Path]::GetFullPath($PSScriptRoot)
$python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Python 3.12 is missing at the expected path.' }
foreach ($name in @('build', 'dist')) {
    $path = [System.IO.Path]::GetFullPath((Join-Path $project $name))
    if (-not $path.StartsWith($project + [System.IO.Path]::DirectorySeparatorChar,
                              [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe build path: $path"
    }
}

Push-Location $project
try {
    & $python -m PyInstaller --noconfirm --clean --onedir --windowed `
        --name 'Web MCQ Fast' --distpath dist --workpath build --specpath . `
        --collect-data rapidocr_onnxruntime --collect-binaries onnxruntime `
        --hidden-import win32com.client --exclude-module torch `
        --exclude-module transformers --exclude-module onnxruntime.quantization tray_app.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed: $LASTEXITCODE" }

    $built = [System.IO.Path]::GetFullPath((Join-Path $project 'dist\Web MCQ Fast'))
    $target = [System.IO.Path]::GetFullPath($project)
    if (-not $built.StartsWith($target + [System.IO.Path]::DirectorySeparatorChar,
                             [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Build path is outside Fast V2.'
    }
    $exeSource = Join-Path $built 'Web MCQ Fast.exe'
    $internalSource = Join-Path $built '_internal'
    if (-not (Test-Path -LiteralPath $exeSource) -or -not (Test-Path -LiteralPath $internalSource)) {
        throw 'Bundled executable or dependencies missing.'
    }
    $exeTarget = Join-Path $target 'Web MCQ Fast.exe'
    $internalTarget = Join-Path $target '_internal'
    $resolvedInternal = [System.IO.Path]::GetFullPath($internalTarget)
    if (-not $resolvedInternal.StartsWith($target + [System.IO.Path]::DirectorySeparatorChar,
                                         [System.StringComparison]::OrdinalIgnoreCase)) {
        throw 'Dependency target is outside Fast V2.'
    }
    if (Test-Path -LiteralPath $exeTarget) { Remove-Item -LiteralPath $exeTarget -Force }
    if (Test-Path -LiteralPath $internalTarget) { Remove-Item -LiteralPath $internalTarget -Recurse -Force }
    Move-Item -LiteralPath $exeSource -Destination $exeTarget
    Move-Item -LiteralPath $internalSource -Destination $internalTarget
    # PyInstaller may collect Poppler's versioned ICU from the host PATH.
    # Qt6Core needs Windows' unversioned icuuc exports instead.
    $incompatible = Join-Path $internalTarget 'icuuc.dll'
    if (Test-Path -LiteralPath $incompatible) {
        Rename-Item -LiteralPath $incompatible -NewName 'icuuc.dll.unused'
    }
    Write-Host "Built $exeTarget"
} finally {
    Pop-Location
}
