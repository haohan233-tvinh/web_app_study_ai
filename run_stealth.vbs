' =========================================================================
' VBScript Launcher: Chay Stealth Network Audit 100% vo hinh
' Khong co cua so console, khong nhay man hinh
' =========================================================================

Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")

strScriptDir = objFSO.GetParentFolderName(WScript.ScriptFullName)
strPsScript = strScriptDir & "\stealth_audit.ps1"

' Tham so 0: SW_HIDE (an hoan toan cua so)
' Tham so True: Doi chay xong moi thoat VBS
strCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File """ & strPsScript & """"

objShell.Run strCommand, 0, True
