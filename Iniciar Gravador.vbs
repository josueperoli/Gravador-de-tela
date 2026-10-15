Option Explicit

Dim fileSystem, shell, scriptDirectory, pythonPath, command
Dim errorNumber, errorDescription

Set fileSystem = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
scriptDirectory = fileSystem.GetParentFolderName(WScript.ScriptFullName)
pythonPath = scriptDirectory & "\.venv\Scripts\pythonw.exe"

If fileSystem.FileExists(pythonPath) Then
    command = """" & pythonPath & """"
Else
    command = """pyw.exe"" -3"
End If

command = command & " """ & scriptDirectory & "\main.py"""

On Error Resume Next
shell.Run command, 0, False
errorNumber = Err.Number
errorDescription = Err.Description
On Error GoTo 0

If errorNumber <> 0 Then
    MsgBox "Nao foi possivel iniciar o Gravador de Tela. Verifique se o Python e as dependencias estao instalados." & vbCrLf & errorDescription, vbCritical, "Gravador de Tela"
End If
