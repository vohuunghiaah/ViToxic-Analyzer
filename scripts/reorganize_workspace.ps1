# One-time migration of the pre-2026-10-11 layout. Refuses destination collisions.
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$migrationEntries = @(
    @('stage2', 'outputs/stage2'),
    @('outputs/stage2/segmentation_cache', 'data/cache/segmented'),
    @('outputs/stage2/vncorenlp', 'resources/vncorenlp'),
    @('outputs/stage2/colab_requirements_lock.txt', 'requirements/locks/colab-stage2.txt'),
    @('outputs/stage2/phobert_lr2e-5_len128_seed42.json', 'outputs/stage2/submitted_configs/phobert_lr2e-5_len128_seed42.json'),
    @('reports/stage1', 'outputs/stage1'),
    @('reports/stage2', 'outputs/archive/stage2_pretraining'),
    @('artifacts', 'outputs/archive/local_resources'),
    @('requirements.txt', 'requirements/stage1.txt'),
    @('requirements-stage2.txt', 'requirements/stage2.txt'),
    @('requirements-lock.txt', 'requirements/locks/windows-stage1.txt'),
    @('requirements-stage2-lock-windows-cpu.txt', 'requirements/locks/windows-stage2-cpu.txt'),
    @('data/ViHSD_train.csv', 'data/raw/ViHSD_train.csv'),
    @('data/ViHSD_validation.csv', 'data/raw/ViHSD_validation.csv'),
    @('data/ViHSD_test.csv', 'data/raw/ViHSD_test.csv'),
    @('scripts/package_colab.py', 'scripts/legacy/package_colab.py')
)
$log = @()
foreach ($entry in $migrationEntries) {
    $sourcePath = [IO.Path]::GetFullPath((Join-Path $projectRoot $entry[0]))
    $targetPath = [IO.Path]::GetFullPath((Join-Path $projectRoot $entry[1]))
    foreach ($candidate in @($sourcePath, $targetPath)) {
        if (-not $candidate.StartsWith($projectRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Outside workspace: $candidate"
        }
    }
    if (-not (Test-Path -LiteralPath $sourcePath)) {
        $log += [PSCustomObject]@{from=$entry[0]; to=$entry[1]}
        continue
    }
    $sourceItem = Get-Item -LiteralPath $sourcePath -Force
    if ($sourceItem.PSIsContainer) {
        # Move files individually: OneDrive's read-only directory attributes can
        # interrupt a directory move after some children have already moved.
        New-Item -ItemType Directory -Path $targetPath -Force | Out-Null
        foreach ($file in @(Get-ChildItem -LiteralPath $sourcePath -File -Recurse -Force)) {
            $relative = [IO.Path]::GetRelativePath($sourcePath, $file.FullName)
            $destination = [IO.Path]::GetFullPath((Join-Path $targetPath $relative))
            if (-not $destination.StartsWith($projectRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Outside workspace' }
            if (Test-Path -LiteralPath $destination) { throw "File collision: $destination" }
            New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($destination)) -Force | Out-Null
            Move-Item -LiteralPath $file.FullName -Destination $destination -Force
        }
        $emptyDirs = @(Get-ChildItem -LiteralPath $sourcePath -Directory -Recurse -Force | Sort-Object { $_.FullName.Length } -Descending)
        foreach ($directory in $emptyDirs) {
            if (@(Get-ChildItem -LiteralPath $directory.FullName -Force).Count -eq 0) { Remove-Item -LiteralPath $directory.FullName -Force }
        }
        if (@(Get-ChildItem -LiteralPath $sourcePath -Force).Count -eq 0) { Remove-Item -LiteralPath $sourcePath -Force }
    } else {
        if (Test-Path -LiteralPath $targetPath) { throw "Destination already exists: $targetPath" }
        New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($targetPath)) -Force | Out-Null
        Move-Item -LiteralPath $sourcePath -Destination $targetPath -Force
    }
    $log += [PSCustomObject]@{from=$entry[0]; to=$entry[1]}
}
$reportsPath = Join-Path $projectRoot 'reports'
if ((Test-Path -LiteralPath $reportsPath) -and @(Get-ChildItem -LiteralPath $reportsPath -Force).Count -eq 0) {
    Remove-Item -LiteralPath $reportsPath -Force # Empty directory only, no recursive removal.
}
$log | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $projectRoot 'outputs/migration-2026-10-11.json') -Encoding utf8
Write-Output "Moved $($log.Count) entries. Training artifacts and historical metadata preserved."
