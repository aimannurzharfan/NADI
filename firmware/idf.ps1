# Runs ESP-IDF v5.4.1 in Docker on the project folder you are in (firmware\csi_send or firmware\csi_recv).
# Nothing to install on Windows except Docker Desktop. Docker cannot reach COM ports, so flashing is done
# with esptool on Windows (see firmware\README.md).
#
#   ..\idf.ps1 menuconfig    settings: Wi-Fi, device ID, room, local or huawei mode (saved in sdkconfig, git-ignored)
#   ..\idf.ps1 build         compile, then write build\merged.bin (one file to flash at address 0x0)
#   ..\idf.ps1 fullclean     delete the build folder
$image = "espressif/idf:v5.4.1"
$here = (Get-Location).Path
if (-not (Test-Path (Join-Path $here "sdkconfig.defaults"))) {
    Write-Host "Run this from firmware\csi_send or firmware\csi_recv."
    exit 1
}
# The whole firmware folder is mounted, because both boards use firmware\common
$firmware = Split-Path -Parent $here
$project = Split-Path -Leaf $here
if ($args.Count -eq 0) { $args = @("build") }

if ($args[0] -eq "menuconfig") {
    docker run --rm -it -v "${firmware}:/fw" -w "/fw/$project" $image idf.py menuconfig
} else {
    docker run --rm -v "${firmware}:/fw" -w "/fw/$project" $image idf.py @args
}
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

if ($args[0] -eq "build") {
    docker run --rm -v "${firmware}:/fw" -w "/fw/$project/build" $image esptool.py --chip esp32s3 merge_bin -o merged.bin "@flash_args"
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    Write-Host ""
    Write-Host "Ready to flash: $here\build\merged.bin"
    Write-Host "  python -m esptool --chip esp32s3 -p COM5 -b 460800 write_flash 0x0 build\merged.bin"
    Write-Host "(replace COM5 with the board's port)"
}
