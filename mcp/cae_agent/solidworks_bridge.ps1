param(
    [Parameter(Mandatory = $true)]
    [string]$RequestPath,
    [Parameter(Mandatory = $true)]
    [string]$ResponsePath
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$request = Get-Content -LiteralPath $RequestPath -Raw | ConvertFrom-Json
$response = [ordered]@{
    status = "failed"
    checks = [ordered]@{}
    warnings = @()
    error = $null
    solidworks_revision = $null
}
$swApp = $null
$document = $null
$createdApplication = $false
$openedDocument = $false

function Get-DocumentType([string]$Path) {
    switch ([IO.Path]::GetExtension($Path).ToLowerInvariant()) {
        ".sldprt" { return 1 }
        ".sldasm" { return 2 }
        ".slddrw" { return 3 }
        default { throw "Unsupported SolidWorks document extension: $Path" }
    }
}

function Open-SolidWorksDocument(
    [object]$Application,
    [string]$Path,
    [bool]$ReadOnly
) {
    $errors = 0
    $warnings = 0
    $options = 1
    if ($ReadOnly) {
        $options = $options -bor 2
    }
    $docType = Get-DocumentType $Path
    $doc = $Application.OpenDoc6(
        $Path,
        $docType,
        $options,
        "",
        [ref]$errors,
        [ref]$warnings
    )
    if ($null -eq $doc) {
        throw "OpenDoc6 failed: errors=$errors warnings=$warnings path=$Path"
    }
    return [ordered]@{
        document = $doc
        document_type = $docType
        open_errors = $errors
        open_warnings = $warnings
    }
}

function Convert-BoxToMillimetres([object]$Box) {
    if ($null -eq $Box) {
        return $null
    }
    $values = @($Box)
    if ($values.Count -lt 6) {
        return $null
    }
    return @(
        [double]$values[0] * 1000.0,
        [double]$values[1] * 1000.0,
        [double]$values[2] * 1000.0,
        [double]$values[3] * 1000.0,
        [double]$values[4] * 1000.0,
        [double]$values[5] * 1000.0
    )
}

try {
    try {
        $swApp = [Runtime.InteropServices.Marshal]::GetActiveObject("SldWorks.Application")
    }
    catch {
        $swApp = New-Object -ComObject "SldWorks.Application"
        $createdApplication = $true
    }
    if ($null -eq $swApp) {
        throw "Could not create or attach to SldWorks.Application"
    }
    $swApp.Visible = [bool]$request.visible
    try {
        $response.solidworks_revision = [string]$swApp.RevisionNumber()
    }
    catch {
        $response.warnings += "Could not query SolidWorks revision number."
    }

    $operation = [string]$request.operation
    if ($operation -notin @("inspect", "parameterize", "export")) {
        throw "Unsupported SolidWorks bridge operation: $operation"
    }
    $inputPath = [IO.Path]::GetFullPath([string]$request.input_path)
    $readOnly = $operation -ne "parameterize"
    $opened = Open-SolidWorksDocument $swApp $inputPath $readOnly
    $document = $opened.document
    $openedDocument = $true
    $response.checks.open_errors = $opened.open_errors
    $response.checks.open_warnings = $opened.open_warnings
    $response.checks.document_type = $opened.document_type
    $response.checks.title = [string]$document.GetTitle()
    $response.checks.path = [string]$document.GetPathName()

    if ($operation -eq "inspect") {
        $configurationNames = @($document.GetConfigurationNames())
        $response.checks.configurations = @($configurationNames | ForEach-Object { [string]$_ })

        $features = @()
        $feature = $document.FirstFeature()
        $guard = 0
        while ($null -ne $feature -and $guard -lt 10000) {
            $features += [ordered]@{
                name = [string]$feature.Name
                type = [string]$feature.GetTypeName2()
            }
            $feature = $feature.GetNextFeature()
            $guard += 1
        }
        $response.checks.features = $features
        $response.checks.feature_count = $features.Count

        $dimensions = [ordered]@{}
        foreach ($name in @($request.dimension_names)) {
            $dimension = $document.Parameter([string]$name)
            if ($null -eq $dimension) {
                $dimensions[[string]$name] = $null
            }
            else {
                $dimensions[[string]$name] = [double]$dimension.SystemValue * 1000.0
            }
        }
        $response.checks.dimensions_mm = $dimensions

        $bodies = @()
        if ($opened.document_type -eq 1) {
            foreach ($body in @($document.GetBodies2(0, $false))) {
                if ($null -ne $body) {
                    $bodies += [ordered]@{
                        name = [string]$body.Name
                        bounding_box_mm = Convert-BoxToMillimetres $body.GetBodyBox()
                    }
                }
            }
        }
        $response.checks.bodies = $bodies
        $response.checks.body_count = $bodies.Count
    }
    elseif ($operation -eq "parameterize") {
        $changes = @()
        foreach ($property in $request.dimensions_mm.PSObject.Properties) {
            $dimensionName = [string]$property.Name
            $newMillimetres = [double]$property.Value
            $dimension = $document.Parameter($dimensionName)
            if ($null -eq $dimension) {
                throw "Dimension not found: $dimensionName"
            }
            $oldMillimetres = [double]$dimension.SystemValue * 1000.0
            $dimension.SystemValue = $newMillimetres / 1000.0
            $changes += [ordered]@{
                name = $dimensionName
                old_mm = $oldMillimetres
                new_mm = [double]$dimension.SystemValue * 1000.0
            }
        }
        $rebuilt = [bool]$document.ForceRebuild3($false)
        $saveErrors = 0
        $saveWarnings = 0
        $saved = [bool]$document.Save3(1, [ref]$saveErrors, [ref]$saveWarnings)
        if (-not $saved -or $saveErrors -ne 0) {
            throw "Save3 failed: saved=$saved errors=$saveErrors warnings=$saveWarnings"
        }
        $response.checks.dimension_changes = $changes
        $response.checks.rebuilt = $rebuilt
        $response.checks.save_errors = $saveErrors
        $response.checks.save_warnings = $saveWarnings

        if ($null -ne $request.export_path -and [string]$request.export_path -ne "") {
            $exportPath = [IO.Path]::GetFullPath([string]$request.export_path)
            $saveAsCode = [int]$document.SaveAs3($exportPath, 0, 1)
            if (-not (Test-Path -LiteralPath $exportPath)) {
                throw "SolidWorks did not create export file: code=$saveAsCode path=$exportPath"
            }
            $response.checks.export_path = $exportPath
            $response.checks.export_code = $saveAsCode
        }
    }
    elseif ($operation -eq "export") {
        $exportPath = [IO.Path]::GetFullPath([string]$request.export_path)
        $saveAsCode = [int]$document.SaveAs3($exportPath, 0, 1)
        if (-not (Test-Path -LiteralPath $exportPath)) {
            throw "SolidWorks did not create export file: code=$saveAsCode path=$exportPath"
        }
        $response.checks.export_path = $exportPath
        $response.checks.export_code = $saveAsCode
    }

    $response.status = "succeeded"
}
catch {
    $response.status = "failed"
    $response.error = $_.Exception.Message
}
finally {
    if ($openedDocument -and $null -ne $document -and $null -ne $swApp) {
        try {
            $swApp.CloseDoc([string]$document.GetTitle())
        }
        catch {
            $response.warnings += "Could not close the SolidWorks document cleanly."
        }
    }
    if ($createdApplication -and $null -ne $swApp) {
        try {
            $swApp.ExitApp()
        }
        catch {
            $response.warnings += "Could not close the SolidWorks application cleanly."
        }
    }
    $response | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $ResponsePath -Encoding UTF8
}

if ($response.status -ne "succeeded") {
    exit 1
}
