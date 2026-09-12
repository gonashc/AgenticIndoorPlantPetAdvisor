function ConvertTo-GcloudDictionaryArgument {
    <#
    .SYNOPSIS
    Serialize key/value entries for a gcloud dictionary flag without treating commas in values
    as entry separators.
    #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Entry
    )

    $delimiter = ";"
    foreach ($item in $Entry) {
        if ([string]::IsNullOrWhiteSpace($item) -or $item.IndexOf("=") -lt 1) {
            throw "Each gcloud dictionary entry must be a non-empty KEY=VALUE string."
        }
        if ($item.Contains($delimiter)) {
            throw "A gcloud dictionary value contains the reserved '$delimiter' delimiter."
        }
    }

    # gcloud requires each caret to be repeated four times when a dictionary argument passes
    # through cmd.exe or Windows PowerShell. Native executables on other platforms use one.
    $prefix = if ($env:OS -eq "Windows_NT") { "^^^^;^^^^" } else { "^;^" }
    return $prefix + ($Entry -join $delimiter)
}
