param([Parameter(Mandatory=$true)][string]$OutputFile)
$ErrorActionPreference='Stop'
[Console]::InputEncoding = New-Object System.Text.UTF8Encoding
Add-Type -AssemblyName System.Speech
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $voice = $speaker.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -like 'en-*' } | Select-Object -First 1
    if (-not $voice) { throw 'No English voice installed in Windows.' }
    $speaker.SelectVoice($voice.VoiceInfo.Name)
    $speaker.SetOutputToWaveFile($OutputFile)
    $text = [Console]::In.ReadToEnd()
    $speaker.Speak($text)
} finally { $speaker.Dispose() }
