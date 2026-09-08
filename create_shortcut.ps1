$shell = New-Object -ComObject WScript.Shell
$desktop = "$env:USERPROFILE\Desktop"
$path = "$desktop\FindMangaTitle Progress Monitor.lnk"

$shortcut = $shell.CreateShortcut($path)
$shortcut.TargetPath = "C:\source\repos\FindMangaTitle\.venv\Scripts\python.exe"
$shortcut.Arguments = """C:\source\repos\FindMangaTitle\progress_monitor.py""""
$shortcut.WorkingDirectory = "C:\source\repos\FindMangaTitle"
$shortcut.Description = "FindMangaTitle - Progress Monitor"
$shortcut.IconLocation = "shell32.dll,13"
$shortcut.Save()

Write-Output "Shortcut created: $path"
