@echo off
REM Restore-Validierung: guter Stand = BASE-Erzaehltext + Default-Hoerspiel v2_B.
REM KEIN WF_PROMPT_VARIANT (=BASE), KEIN --hoerspiel-prompt (=Default v2_B).
cd /d C:\Users\Andreas\wissensfreund_repo
set WF_PROMPT_VARIANT=
echo START %date% %time% > "C:\Users\Andreas\Desktop\_restore_out.txt"
"C:\Users\Andreas\AppData\Local\Python\pythoncore-3.14-64\python.exe" scripts\generate_grounded.py --catalog Dinosaurier Vulkan Spielzeug --output-dir articles\restore_20260729 --run-id restore_20260729 >> "C:\Users\Andreas\Desktop\_restore_out.txt" 2>&1
echo DONE_EXIT_%errorlevel% %date% %time% >> "C:\Users\Andreas\Desktop\_restore_out.txt"
