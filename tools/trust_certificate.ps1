<#
 Добавляет сертификат издателя PhotoEnjoyer в «доверенные» на ЭТОМ компьютере,
 чтобы Windows не считала подписанные им программы «от неизвестного издателя».

 Запускайте только если доверяете автору программы и получили файл .cer от него
 лично (отпечаток SHA-256 сверьте с тем, что сообщил автор).

 Использование (PowerShell от имени администратора):
     .\trust_certificate.ps1 -Cer .\photoenjoyer-codesign.cer
 Отменить:
     .\trust_certificate.ps1 -Cer .\photoenjoyer-codesign.cer -Remove
#>
param(
    [Parameter(Mandatory = $true)][string]$Cer,
    [switch]$Remove
)
$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($Cer)
Write-Host "Издатель:  $($cert.Subject)"
Write-Host "Отпечаток: $($cert.GetCertHashString('SHA256'))"
foreach ($storeName in 'Root', 'TrustedPublisher') {
    $store = New-Object System.Security.Cryptography.X509Certificates.X509Store($storeName, 'LocalMachine')
    $store.Open('ReadWrite')
    if ($Remove) { $store.Remove($cert); Write-Host "Удалён из $storeName" }
    else         { $store.Add($cert);    Write-Host "Добавлен в $storeName" }
    $store.Close()
}
