# Reproduce a voice from its recipe — PowerShell helper (wraps reproduce_voice.py)
param(
  [string]$VoiceId,
  [string]$Language = "German",
  [string]$Text = "",
  [switch]$DryRun,
  [switch]$Reproduce,
  [switch]$List,
  [switch]$Validate
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
# repo root is parent of project
$script = Join-Path $root "project/tools/reproduce_voice.py"
if ($List) { python $script --list; exit $LASTEXITCODE }
if ($Validate) { python $script --validate; exit $LASTEXITCODE }
if (-not $VoiceId) { Write-Host "Usage: .\reproduce_voice.ps1 -VoiceId <id> [-Language German|English] [-DryRun|-Reproduce]"; exit 1 }
$args = @("--voice-id", $VoiceId, "--language", $Language)
if ($Text) { $args += @("--text", $Text) }
if ($Reproduce) { $args += "--reproduce" } else { $args += "--dry-run" }
python $script @args
exit $LASTEXITCODE
