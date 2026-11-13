# Stop any NADI server, simulator or stress script left running and free the server port (default 8000).
#   powershell -ExecutionPolicy Bypass -File scripts\stop.ps1 [-Port 8000]
param([int]$Port = 8000)

$procs = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe' OR Name='uvicorn.exe'" |
    Where-Object { $_.CommandLine -match 'server\.main|fake_sensor|fake_board|scripts.stress' }
foreach ($p in $procs) {
    Write-Output "stopping $($p.ProcessId): $($p.CommandLine)"
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}

$owners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique)
foreach ($id in $owners) {
    $name = (Get-Process -Id $id -ErrorAction SilentlyContinue).ProcessName
    Write-Output "port $Port held by $id ($name): stopping"
    Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Milliseconds 500
if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) {
    Write-Output "port $Port is STILL in use"
    exit 1
}
Write-Output "no NADI processes running, port $Port free"
