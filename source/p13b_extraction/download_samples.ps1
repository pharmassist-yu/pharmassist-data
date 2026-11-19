# P-13b: download the KÜB/KT sample PDFs listed in samples/sample_documents.csv.
# PowerShell alternative to download_samples.py: uses the Windows TLS stack (like the
# browser), so it avoids Python's CERTIFICATE_VERIFY_FAILED with titck.gov.tr.
# Polite: one request every 5 seconds, project User-Agent, existing files skipped.
#
# Usage (from the repository root):
#   powershell -ExecutionPolicy Bypass -File source\p13b_extraction\download_samples.ps1

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$manifest = Join-Path $root "samples\sample_documents.csv"
$out = Join-Path $root "samples\pdf"
New-Item -ItemType Directory -Force -Path $out | Out-Null
$ua = "PharmAssist-SeniorProject/0.1 (academic, non-commercial; P-13b sample download)"

foreach ($row in (Import-Csv -Path $manifest -Encoding UTF8)) {
    foreach ($pair in @(@("KUB", $row.kub_url), @("KT", $row.kt_url))) {
        $dest = Join-Path $out ("{0}_{1}.pdf" -f $row.sample_id, $pair[0])
        if (Test-Path $dest) { Write-Host "skip  $(Split-Path $dest -Leaf)"; continue }
        $url = $pair[1].Replace(" ", "%20")
        try {
            Invoke-WebRequest -Uri $url -OutFile $dest -UserAgent $ua -UseBasicParsing -TimeoutSec 60
            $head = [System.Text.Encoding]::ASCII.GetString([System.IO.File]::ReadAllBytes($dest)[0..3])
            if ($head -ne "%PDF") { Remove-Item $dest; throw "response is not a PDF (blocked or moved?)" }
            Write-Host ("ok    {0}  {1} KB" -f (Split-Path $dest -Leaf), [int]((Get-Item $dest).Length / 1KB))
        } catch {
            Write-Host "FAIL  $(Split-Path $dest -Leaf): $($_.Exception.Message)"
        }
        Start-Sleep -Seconds 5
    }
}
