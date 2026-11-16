@echo off
:: SPDX-License-Identifier: MIT
:: /*!
:: ****************************
:: \file       flash.bat
:: \brief      Check a release folder, then flash its images with the ST-LINK (Windows).
::
:: \author     Z. BEN-AKKA
:: \version    1.0
:: \date       15/11/2026
::
:: \details
::   Delivered at the root of the release folder (cd/README.md section 5.3),
::   for Windows with OpenOCD installed on Windows (xPack OpenOCD). Does what
::   flash.sh does on Linux: checks every file against SHA256SUMS (certutil)
::   and every line of images.txt, then flashes the images in the order of
::   images.txt with the same OpenOCD command as "make <app>-flash". A
::   bootloader pair is always flashed whole, QSPI application first. A
::   standalone image replaces any bootloader in internal flash, so it is
::   flashed only once confirmed; an empty answer, or no console, refuses.
::   Nothing is flashed unless every check passed. CRLF line endings, as cmd.exe
::   expects.
::
::     flash.bat              check, confirm a standalone image, flash
::     flash.bat /yes         the same, without the confirmation
::     flash.bat /dry-run     check, then print the OpenOCD commands only
::
::   Exit codes: 0 done, 2 usage error, 3 integrity error, 4 OpenOCD missing
::   or older than 0.11.0, 5 not confirmed, 6 flash failed.
::
:: \section flash_bat_version_history Version history
:: | Version | Date       | Author      | Description      |
:: |:-------:|:----------:|:------------|:-----------------|
:: | 1.0     | 15/11/2026 | Z. BEN-AKKA | Initial version. |
:: ****************************
:: */

setlocal EnableExtensions EnableDelayedExpansion

set "EXIT_USAGE=2"
set "EXIT_INTEGRITY=3"
set "EXIT_OPENOCD=4"
set "EXIT_REFUSED=5"
set "EXIT_FLASH=6"

:: First version with the stmqspi driver that a QSPI image needs: 0.11.0
set "OPENOCD_MIN=0.11.0"
set "OPENOCD_MIN_MINOR=11"

:: The release folder; read before shift, which also shifts %0
set "here=%~dp0"

:: ------------------------------------------------------------------
:: Options
:: ------------------------------------------------------------------

set "yes=0"
set "dry_run=0"

:next_option
if "%~1"=="" goto options_done
if /i "%~1"=="/yes" (
  set "yes=1"
  goto shift_option
)
if /i "%~1"=="--yes" (
  set "yes=1"
  goto shift_option
)
if /i "%~1"=="/dry-run" (
  set "dry_run=1"
  goto shift_option
)
if /i "%~1"=="--dry-run" (
  set "dry_run=1"
  goto shift_option
)
if "%~1"=="/?" (
  call :usage
  exit /b 0
)
if /i "%~1"=="--help" (
  call :usage
  exit /b 0
)
call :error "unknown option: %~1"
call :usage 1>&2
exit /b %EXIT_USAGE%

:shift_option
shift
goto next_option

:options_done

:: The paths of SHA256SUMS and images.txt are relative to the release folder.
:: pushd, not cd: it maps a UNC folder (\\server\share, \\wsl.localhost) to a
:: drive letter. The end of setlocal gives the caller its folder back.
pushd "%here%"

:: ------------------------------------------------------------------
:: Integrity
:: ------------------------------------------------------------------

for %%F in (SHA256SUMS images.txt) do (
  if not exist "%%F" (
    call :error "%%F not found: run flash.bat from the extracted release folder"
    exit /b %EXIT_INTEGRITY%
  )
)

echo flash.bat: checking SHA256SUMS
:: "<sha256>  <path>", "*" before the path in binary mode. A malformed line
:: names no file or no matching hash, so it fails too.
set "listed= "
set "sums=0"
for /f "usebackq tokens=1,*" %%A in ("SHA256SUMS") do (
  set "want=%%A"
  set "sumfile=%%B"
  if "!sumfile:~0,1!"=="*" set "sumfile=!sumfile:~1!"
  set "winfile=!sumfile:/=\!"
  if not exist "!winfile!" (
    call :error "!sumfile!: missing; download the release again, nothing flashed"
    exit /b %EXIT_INTEGRITY%
  )
  set "got="
  for /f "skip=1 delims=" %%H in ('certutil -hashfile "!winfile!" SHA256') do (
    if not defined got set "got=%%H"
  )
  set "got=!got: =!"
  if /i not "!got!"=="!want!" (
    call :error "!sumfile! does not match SHA256SUMS; download the release again, nothing flashed"
    exit /b %EXIT_INTEGRITY%
  )
  set "listed=!listed!!sumfile! "
  set /a sums+=1
)
if %sums%==0 (
  call :error "SHA256SUMS lists no file"
  exit /b %EXIT_INTEGRITY%
)
if "!listed: images.txt =!"=="!listed!" (
  call :error "images.txt is not listed in SHA256SUMS"
  exit /b %EXIT_INTEGRITY%
)

:: images.txt: "image file memory address openocd-options", in flashing order
set "count=0"
for /f "usebackq eol=# tokens=1-4,*" %%A in ("images.txt") do (
  set /a count+=1
  set "where=images.txt, image %%A"
  if "%%E"=="" (
    call :error "!where!: expected image, file, memory, address, OpenOCD options"
    exit /b %EXIT_INTEGRITY%
  )
  set "file=%%B"
  if not "!file:~0,7!"=="images/" (
    call :error "!where!: %%B is not in images/"
    exit /b %EXIT_INTEGRITY%
  )
  if not "!file:..=!"=="!file!" (
    call :error "!where!: %%B is not in images/"
    exit /b %EXIT_INTEGRITY%
  )
  if "!listed: %%B =!"=="!listed!" (
    call :error "!where!: %%B is not listed in SHA256SUMS"
    exit /b %EXIT_INTEGRITY%
  )
  if not "%%C"=="flash" if not "%%C"=="qspi" (
    call :error "!where!: unknown memory %%C"
    exit /b %EXIT_INTEGRITY%
  )
  set "address=%%D"
  set "digits=!address:~2!"
  set "bad="
  if not "!address:~0,2!"=="0x" set "bad=1"
  if "!digits!"=="" set "bad=1"
  if not "!digits:~8!"=="" set "bad=1"
  rem Only hexadecimal digits: nothing is left once they are the delimiters
  for /f "delims=0123456789abcdefABCDEF" %%X in ("!digits!") do set "bad=1"
  if defined bad (
    call :error "!where!: bad address %%D"
    exit /b %EXIT_INTEGRITY%
  )
  set "name_!count!=%%A"
  set "file_!count!=%%B"
  set "memory_!count!=%%C"
  set "address_!count!=%%D"
  set "options_!count!=%%E"
)
if %count%==0 (
  call :error "images.txt lists no image"
  exit /b %EXIT_INTEGRITY%
)
echo flash.bat: files match SHA256SUMS, images.txt lists %count% image(s)

:: ------------------------------------------------------------------
:: OpenOCD
:: ------------------------------------------------------------------

set "problem="
where openocd >nul 2>nul
if errorlevel 1 (
  set "problem=openocd not found: install OpenOCD %OPENOCD_MIN% or later and add its bin folder to PATH (see README.md)"
  goto openocd_checked
)
set "version_text="
for /f "delims=" %%V in ('openocd --version 2^>^&1') do (
  if not defined version_text set "version_text=%%V"
)
echo flash.bat: !version_text!
:: The first word that starts with a digit: "0.11.0", "0.12.0+dev-..."
set "major="
set "minor="
for %%W in (!version_text!) do (
  set "word=%%W"
  if not defined major if "!word:~0,1!" geq "0" if "!word:~0,1!" leq "9" (
    for /f "tokens=1,2 delims=.+-" %%M in ("%%W") do (
      set /a major=%%M 2>nul
      set /a minor=%%N 2>nul
    )
  )
)
if not defined minor (
  set "problem=cannot read the OpenOCD version"
  goto openocd_checked
)
if !major!==0 if !minor! lss %OPENOCD_MIN_MINOR% (
  set "problem=OpenOCD !major!.!minor! is older than %OPENOCD_MIN%"
)

:openocd_checked
:: A dry run flashes nothing: a missing or old OpenOCD is only reported
if defined problem (
  if %dry_run%==1 (
    1>&2 echo flash.bat: warning: !problem!
  ) else (
    call :error "!problem!"
    exit /b %EXIT_OPENOCD%
  )
)

:: ------------------------------------------------------------------
:: Confirmation
:: ------------------------------------------------------------------

set "standalone=0"
if %count%==1 if "!memory_1!"=="flash" set "standalone=1"
if %standalone%==0 (
  echo flash.bat: bootloader pair: flashed whole, in the order of images.txt
  goto flash
)
echo WARNING: !name_1! is a standalone image: it replaces any bootloader in internal flash.
if %yes%==1 goto flash
if %dry_run%==1 goto flash
set "answer="
set /p "answer=Flash !name_1!? [y/N] "
if /i "!answer!"=="y" goto flash
if /i "!answer!"=="yes" goto flash
call :error "not confirmed; nothing flashed"
exit /b %EXIT_REFUSED%

:: ------------------------------------------------------------------
:: Flash
:: ------------------------------------------------------------------

:flash
for /l %%I in (1,1,%count%) do (
  set "program=program !file_%%I! !address_%%I! verify reset exit"
  if %dry_run%==1 (
    echo openocd !options_%%I! -c "!program!"
  ) else (
    echo flash.bat: flashing !name_%%I! ^(!memory_%%I!, !address_%%I!^)
    openocd !options_%%I! -c "!program!"
    if errorlevel 1 (
      call :error "OpenOCD failed on !name_%%I!: check the ST-LINK connection, then run flash.bat again"
      exit /b %EXIT_FLASH%
    )
  )
)

if %dry_run%==1 (
  echo flash.bat: dry run: nothing flashed
) else (
  echo flash.bat: done: every image flashed and verified, the board restarts
)
exit /b 0

:: ------------------------------------------------------------------
:: Subroutines
:: ------------------------------------------------------------------

:usage
echo Usage: flash.bat [/yes] [/dry-run] [/?]
echo.
echo Checks the release files against SHA256SUMS, then flashes the images of
echo images.txt to the STM32F7508-DK with OpenOCD and the ST-LINK.
echo.
echo   /yes, --yes           do not ask before replacing a bootloader in internal flash
echo   /dry-run, --dry-run   run the checks, print the OpenOCD commands, flash nothing
echo   --help, /?            print this help
echo.
echo Exit codes: 0 done, 2 usage error, 3 integrity error, 4 OpenOCD missing or
echo older than 0.11.0, 5 not confirmed, 6 flash failed.
exit /b 0

:: $1: the message, on stderr
:error
1>&2 echo flash.bat: error: %~1
exit /b 0
