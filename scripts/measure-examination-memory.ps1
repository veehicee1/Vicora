param(
    [ValidateRange(1, 60)]
    [int]$IntervalSeconds = 5,
    [ValidateRange(1, 240)]
    [int]$DurationMinutes = 30,
    [string]$OutputPath = ".\gtmc-examination-memory.csv"
)

$ErrorActionPreference = "Stop"
$rows = [System.Collections.Generic.List[object]]::new()
$endTime = (Get-Date).AddMinutes($DurationMinutes)

Write-Host "Monitoring GTMC CBT Examination processes..."
Write-Host "Interval: $IntervalSeconds seconds; duration: $DurationMinutes minutes"
Write-Host "CSV output: $OutputPath"
Write-Host "Do not run this during a live examination."

while ((Get-Date) -lt $endTime) {
    $sampleTime = Get-Date
    $os = Get-CimInstance Win32_OperatingSystem
    $availableMemoryMB = [math]::Round($os.FreePhysicalMemory / 1024, 1)
    # Packaged Electron and Chromium child processes use CBTExamination.exe.
    # Collect all matching processes across every RDP session.
    $processes = @(Get-Process -Name "CBTExamination" -ErrorAction SilentlyContinue)

    foreach ($group in ($processes | Group-Object SessionId)) {
        $items = @($group.Group)
        $rows.Add([pscustomobject]@{
            Timestamp = $sampleTime.ToString("o")
            SessionId = [int]$group.Name
            ProcessCount = $items.Count
            WorkingSetMB = [math]::Round((($items | Measure-Object WorkingSet64 -Sum).Sum / 1MB), 1)
            PrivateMemoryMB = [math]::Round((($items | Measure-Object PrivateMemorySize64 -Sum).Sum / 1MB), 1)
            CpuSeconds = [math]::Round((($items | Measure-Object CPU -Sum).Sum), 1)
            ServerAvailableMemoryMB = $availableMemoryMB
        })
    }

    $rows.Add([pscustomobject]@{
        Timestamp = $sampleTime.ToString("o")
        SessionId = "ALL"
        ProcessCount = $processes.Count
        WorkingSetMB = [math]::Round((($processes | Measure-Object WorkingSet64 -Sum).Sum / 1MB), 1)
        PrivateMemoryMB = [math]::Round((($processes | Measure-Object PrivateMemorySize64 -Sum).Sum / 1MB), 1)
        CpuSeconds = [math]::Round((($processes | Measure-Object CPU -Sum).Sum), 1)
        ServerAvailableMemoryMB = $availableMemoryMB
    })

    $sessionCount = @($processes | Select-Object -ExpandProperty SessionId -Unique).Count
    $privateMB = [math]::Round((($processes | Measure-Object PrivateMemorySize64 -Sum).Sum / 1MB), 1)
    Write-Host ("{0} | sessions: {1} | processes: {2} | private memory: {3} MB | server available: {4} MB" -f $sampleTime.ToString("HH:mm:ss"), $sessionCount, $processes.Count, $privateMB, $availableMemoryMB)
    Start-Sleep -Seconds $IntervalSeconds
}

$rows | Export-Csv -Path $OutputPath -NoTypeInformation -Encoding UTF8
Write-Host "Finished. Results saved to $OutputPath"