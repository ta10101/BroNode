# Holo Edge Node — Docker runtime cleanup (Windows)
# Removes container "edgenode", image ghcr.io/holo-host/edgenode, volume "holo-data".
# This script does NOT uninstall the BroNode MSI or delete BroNode.exe.
# For GUI removal: Settings -> Apps -> BroNode (MSI) or delete the portable .exe.
# See docs/INSTALL_AND_UNINSTALL.md

$ErrorActionPreference = "Continue"

$ContainerName = "edgenode"
$ImageName = "ghcr.io/holo-host/edgenode"
$VolumeName = "holo-data"

Write-Host "Edge Node Docker cleanup (not the BroNode app uninstaller)" -ForegroundColor Cyan
Write-Host "This will remove Docker resources:" -ForegroundColor Yellow
Write-Host " - Container: $ContainerName"
Write-Host " - Image:     $ImageName"
Write-Host " - Volume:    $VolumeName (DATA LOSS — persisted node data)"
Write-Host ""

$confirm = Read-Host "Type YES to continue"
if ($confirm -ne "YES") {
  Write-Host "Cancelled."
  exit 0
}

Write-Host "`nRemoving container..."
docker rm -f $ContainerName

Write-Host "`nRemoving image..."
docker rmi $ImageName

Write-Host "`nRemoving volume..."
docker volume rm $VolumeName

Write-Host "`nDone."
Write-Host "BroNode GUI is unchanged. To remove the app: Settings -> Apps -> BroNode, or delete BroNode.exe."
Write-Host "Doc: docs\INSTALL_AND_UNINSTALL.md"
