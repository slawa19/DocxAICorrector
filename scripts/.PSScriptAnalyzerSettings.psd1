@{
    # Suppress "variable assigned but never used" for _shared.ps1
    # Variables like $serverHost and $healthUrl are exported via dot-sourcing
    # and consumed in start-project.ps1, stop-project.ps1, status-project.ps1
    ExcludeRules = @(
        'PSUseDeclaredVarsMoreThanAssignments'
    )
}
