<#
.SYNOPSIS
  Prints a new Fernet key (URL-safe base64 of 32 random bytes) for ENCRYPTION_KEYS.
  To rotate: put the new key FIRST and keep old keys after it, comma-separated.
#>
$bytes = New-Object byte[] 32
[System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
[Convert]::ToBase64String($bytes).Replace('+', '-').Replace('/', '_')
