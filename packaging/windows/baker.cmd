@echo off
rem The baker command. Runs Baker on the Python bundled next to this file, in UTF-8 mode so
rem text files read the same on every Windows code page. Nothing here uses the network.
setlocal
"%~dp0python\python.exe" -X utf8 -m cli %*
