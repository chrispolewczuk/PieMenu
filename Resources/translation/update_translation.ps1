# Requires Windows PowerShell 5.1 or PowerShell 7+.
# Place this script in Resources/translation, alongside the .ts files.
# Qt tools must be on PATH, or set their full executable paths below.
# Flags are case-sensitive: -U/-R act globally; -u/-r require a locale.

$ErrorActionPreference = 'Stop'
$LUPDATE = 'lupdate.exe'
$LRELEASE = 'lrelease.exe'
# Example: $LUPDATE = 'C:\Qt\6.10.1\msvc2022_64\bin\lupdate.exe'
# Example: $LRELEASE = 'C:\Qt\6.10.1\msvc2022_64\bin\lrelease.exe'
$WB = 'PieMenu'
$SupportedLocales = @(
    'en', 'af', 'ar', 'eu', 'be', 'bg', 'ca', 'zh-CN', 'zh-TW', 'hr',
    'cs', 'da', 'nl', 'fil', 'fi', 'fr', 'gl', 'ka', 'de', 'el',
    'hu', 'id', 'it', 'ja', 'kab', 'ko', 'lt', 'no', 'pl', 'pt-PT',
    'pt-BR', 'ro', 'ru', 'sr', 'sr-CS', 'sk', 'sl', 'es-ES', 'es-AR', 'sv-SE',
    'tr', 'uk', 'val-ES', 'vi'
)

function Show-Help {
    Write-Host @'

Create, update and release translation files.

Usage:
  .\update_translation.ps1 -U             Update the main translation file
  .\update_translation.ps1 -R             Release all locale files recursively
  .\update_translation.ps1 -u <locale>    Update main and specified locale
  .\update_translation.ps1 -r <locale>    Release the specified locale

Examples:
  .\update_translation.ps1 -u es-ES
  .\update_translation.ps1 -r es-ES

Translate the .ts file using Qt Linguist, then release it to generate a .qm file.
Flags and locale codes are case-sensitive.
'@
}

function Invoke-QtTool {
    param([string]$Tool, [string[]]$ToolArguments)
    & $Tool @ToolArguments
    if ($LASTEXITCODE -ne 0) {
        throw "Qt tool '$Tool' failed with exit code $LASTEXITCODE."
    }
}

function Update-Locale {
    param([string]$Locale = '')
    $FileName = if ($Locale) { "${WB}_${Locale}.ts" } else { "${WB}.ts" }
    $Action = if (Test-Path -LiteralPath $FileName) { 'Updating' } else { 'Creating' }
    Write-Host "`n`t<<< $Action '$FileName' file >>>`n" -ForegroundColor Blue

    $ToolArguments = @('../../InitGui.py')
    if ($Locale) {
        $ToolArguments += @('-source-language', 'en_US', '-target-language', $Locale.Replace('-', '_'))
    }
    $ToolArguments += @('-ts', $FileName)
    Invoke-QtTool -Tool $LUPDATE -ToolArguments $ToolArguments
}

function Normalize-TranslationLanguages {
    # Normalize language attributes rather than assuming the TS tag is on line 3.
    # Preserve all other text, line endings and any UTF-8 BOM.
    foreach ($File in Get-ChildItem -LiteralPath . -Filter "${WB}*.ts" -File) {
        $Bytes = [System.IO.File]::ReadAllBytes($File.FullName)
        $HasBom = $Bytes.Length -ge 3 -and $Bytes[0] -eq 0xEF -and $Bytes[1] -eq 0xBB -and $Bytes[2] -eq 0xBF
        $Encoding = [System.Text.UTF8Encoding]::new($HasBom, $true)
        $Offset = if ($HasBom) { 3 } else { 0 }
        $Text = $Encoding.GetString($Bytes, $Offset, $Bytes.Length - $Offset)
        $Updated = [regex]::Replace($Text, '<TS\b[^>]*>', [System.Text.RegularExpressions.MatchEvaluator]{
            param($Tag)
            [regex]::Replace($Tag.Value, '\b(?:language|sourcelanguage)="[^"]*"', [System.Text.RegularExpressions.MatchEvaluator]{
                param($Attribute)
                $Attribute.Value.Replace('-', '_')
            })
        })
        if ($Updated -cne $Text) {
            [System.IO.File]::WriteAllText($File.FullName, $Updated, $Encoding)
        }
    }
}

# Raw arguments intentionally preserve -U versus -u and -R versus -r.
# PowerShell named parameters cannot distinguish names solely by case.
if ($args.Count -eq 1 -and ($args[0] -ceq '-U' -or $args[0] -ceq '-R')) {
    $Mode = [string]$args[0]
    $Locale = ''
}
elseif ($args.Count -eq 2 -and ($args[0] -ceq '-u' -or $args[0] -ceq '-r')) {
    $Mode = [string]$args[0]
    $Locale = [string]$args[1]
    if ($SupportedLocales -cnotcontains $Locale) {
        Write-Host 'Verify your language code. Case sensitive.' -ForegroundColor Yellow
        Write-Host "If correct, ask a maintainer to add support for your language on FreeCAD."
        Write-Host "`nSupported locales:"
        Write-Host (($SupportedLocales | Sort-Object) -join ' ')
        exit 1
    }
}
else {
    Show-Help
    return
}

Push-Location -LiteralPath $PSScriptRoot
try {
    $Tool = if ($Mode -ceq '-U' -or $Mode -ceq '-u') { $LUPDATE } else { $LRELEASE }
    if (-not (Get-Command -Name $Tool -CommandType Application -ErrorAction SilentlyContinue)) {
        throw "Cannot find '$Tool'. Add Qt's bin directory to PATH or set its full path in this script."
    }
    Normalize-TranslationLanguages
    switch -CaseSensitive ($Mode) {
        '-U' { Update-Locale }
        '-u' { Update-Locale; Update-Locale -Locale $Locale }
        '-r' { Invoke-QtTool -Tool $LRELEASE -ToolArguments @("${WB}_${Locale}.ts") }
        '-R' {
            foreach ($File in Get-ChildItem -LiteralPath . -Recurse -File -Filter '*_*.ts') {
                Invoke-QtTool -Tool $LRELEASE -ToolArguments @($File.FullName)
                Write-Host ''
            }
        }
    }
}
catch {
    Write-Error -Message $_.Exception.Message -ErrorAction Continue
    exit 1
}
finally {
    Pop-Location
}
