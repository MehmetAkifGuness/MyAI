Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\gunes\KendiYapayZekam"
WshShell.Run """C:\Users\gunes\AppData\Local\Programs\Python\Python313\pythonw.exe"" ""C:\Users\gunes\KendiYapayZekam\main.py"" --silent", 0, False

