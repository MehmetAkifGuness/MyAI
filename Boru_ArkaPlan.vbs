Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Users\gunes\OneDrive\Desktop\KendiYapayZekam"
WshShell.Run """C:\Users\gunes\AppData\Local\Programs\Python\Python313\python.exe"" ""C:\Users\gunes\OneDrive\Desktop\KendiYapayZekam\main.py"" --silent", 0, False
