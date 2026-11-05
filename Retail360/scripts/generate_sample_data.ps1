param([string]$Out = "data/raw", [int]$Seed = 42, [string]$Scale = "small", [int]$Days = 30)
$root = Split-Path -Parent $PSScriptRoot
& "$root\.venv\Scripts\python.exe" -m retail360.generators.generate_data --out $Out --seed $Seed --scale $Scale --days $Days
