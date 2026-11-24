@echo off
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars32.bat" >nul
cd /d "%~dp0"
set O=..\build\release
set OUT=..\build\winmm.dll
set DEF=
set EXTRA=
if "%1"=="test" (
  set O=..\build\test
  set OUT=..\build\test\winmm.dll
  set DEF=/DXI_TEST
)
if not exist ..\build mkdir ..\build
if not exist %O% mkdir %O%
if not exist ..\build\patch.bin echo.>..\build\patch.bin
rc /nologo /fo %O%\xi_jp.res xc_jp.rc || exit /b 1
cl /nologo /O2 /MT /W3 /utf-8 /LD /D_CRT_SECURE_NO_WARNINGS %DEF% /Fo%O%\ proxy.c xi_jp.c %EXTRA% %O%\xi_jp.res /Fe%OUT% /link /DEF:winmm.def kernel32.lib user32.lib gdi32.lib || exit /b 1
