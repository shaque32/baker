@echo off
rem The mabillon command, staged as mabillon.cmd and, for a release, baker.cmd. Runs Mabillon on
rem the Python bundled next to this file, in UTF-8 mode so text files read the same on every
rem Windows code page. Nothing here uses the network.
setlocal
"%~dp0python\python.exe" -X utf8 -m cli %*
