$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
$Root = $PSScriptRoot
$Binding = Get-Content -LiteralPath (Join-Path $Root 'buyer-package-binding.json') -Raw | ConvertFrom-Json
$Picker = New-Object System.Windows.Forms.OpenFileDialog
$Picker.Filter = 'PF07 buyer ZIP (*.zip)|*.zip'
$Picker.Title = 'Select the exact PF07 Windows buyer ZIP'
if ($Picker.ShowDialog() -ne 'OK') { exit 2 }
$Archive = Get-Item -LiteralPath $Picker.FileName
$Hash = (Get-FileHash -LiteralPath $Archive.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
$NamePass = $Archive.Name -eq $Binding.buyer_archive
$HashPass = $Hash -eq $Binding.buyer_sha256
$Extract = Join-Path $env:TEMP ('PF07 KVM 한글 경로 ' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $Extract | Out-Null
Expand-Archive -LiteralPath $Archive.FullName -DestinationPath $Extract
$Launcher = Get-ChildItem -LiteralPath $Extract -Filter 'PF07-Launcher.exe' -File -Recurse | Select-Object -First 1
$Result = [ordered]@{
    schema = 'pf07.windows-kvm-preflight.v1'
    buyer_archive = $Archive.Name
    expected_sha256 = $Binding.buyer_sha256
    observed_sha256 = $Hash
    archive_name_pass = $NamePass
    archive_hash_pass = $HashPass
    unicode_space_extraction_pass = Test-Path -LiteralPath $Extract
    launcher_present = $null -ne $Launcher
    launcher_version = if ($null -ne $Launcher) { $Launcher.VersionInfo.ProductVersion } else { $null }
    os = [Environment]::OSVersion.VersionString
    architecture = [Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
    actual_full_stack_executed = $false
    created_at_utc = [DateTime]::UtcNow.ToString('o')
}
$Output = Join-Path ([Environment]::GetFolderPath('Desktop')) 'PF07-WINDOWS-KVM-PREFLIGHT.json'
$Result | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Output -Encoding UTF8
[System.Windows.Forms.MessageBox]::Show(
    "Archive name: $NamePass`nArchive hash: $HashPass`nLauncher found: $($null -ne $Launcher)`n`nResult: $Output",
    'PF07 Windows KVM preflight',
    'OK',
    $(if ($NamePass -and $HashPass -and $null -ne $Launcher) { 'Information' } else { 'Error' })
) | Out-Null
