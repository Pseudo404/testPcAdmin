# Démarrage automatique — Mini Crèche

Ce dossier permet au serveur de synchronisation de démarrer automatiquement lorsque la directrice ouvre sa session Windows.

## Avant l'installation

1. Le dossier complet `pc-directrice` doit rester au même emplacement sur le PC.
2. Lancez une fois `backend\start.bat` et vérifiez que `http://127.0.0.1:8000` fonctionne.
3. Fermez le serveur avec `Ctrl+C` une fois le test terminé.

## Installer le démarrage automatique

1. Clic droit sur `installer-demarrage-auto.ps1`.
2. Cliquez **Exécuter avec PowerShell**.
3. À la prochaine ouverture de session Windows, le serveur démarrera automatiquement.
4. Son journal se trouve dans `pc-directrice\logs\backend.log`.

Pour le tester immédiatement, double-cliquez sur `demarrer-backend.bat`, puis ouvrez `http://127.0.0.1:8000`.

## WireGuard du PC

Dans WireGuard Windows, laissez le tunnel de la directrice activé. Activez l'option de démarrage automatique du tunnel si elle est disponible dans votre version de WireGuard.

Le tunnel et le serveur demandent que le PC soit allumé et que la session Windows de la directrice soit ouverte.

## Tablette Android

Dans **Paramètres Android > Réseau et Internet > VPN > WireGuard**, activez **VPN permanent / Always-on VPN** pour le tunnel Mini Crèche. La tablette reconnectera alors WireGuard automatiquement.

Ne cochez pas « Bloquer les connexions sans VPN » pendant les essais : l'application conserve déjà les signatures hors ligne et les synchronise au retour de la connexion.

## Désinstaller

Clic droit sur `desinstaller-demarrage-auto.ps1`, puis **Exécuter avec PowerShell**.
