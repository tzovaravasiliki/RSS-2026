param([string]$Provider = "")
$ErrorActionPreference = "Stop"
if (-not $Provider) {
    Write-Host "1 = OpenAI, 2 = Anthropic / Claude, 3 = Google Gemini"
    $selection = Read-Host "Provider"
    $Provider = switch ($selection) {
        "1" { "openai" }
        "2" { "anthropic" }
        "3" { "gemini" }
        default { throw "Select 1, 2 or 3. Nothing was saved." }
    }
}
if ($Provider -notin @("openai", "anthropic", "gemini")) {
    throw "Invalid provider. Use openai, anthropic or gemini. Nothing was saved."
}
$variable = switch ($Provider) {
    "openai" { "OPENAI_API_KEY" }
    "anthropic" { "ANTHROPIC_API_KEY" }
    "gemini" { "GEMINI_API_KEY" }
}
$secret = Read-Host "Paste API key locally (hidden)" -AsSecureString
$keyValue = [System.Net.NetworkCredential]::new("", $secret).Password.Trim()
if ([string]::IsNullOrWhiteSpace($keyValue)) { throw "Empty key. Nothing was saved." }
[Environment]::SetEnvironmentVariable($variable, $keyValue, "User")
[Environment]::SetEnvironmentVariable($variable, $keyValue, "Process")
Remove-Variable secret, keyValue
Write-Host "$variable saved for your Windows user. No key was printed or written into this project."
Write-Host "The workbench reads the saved User variable directly. Refresh key status in Settings."
