@echo off
cd /d C:\Users\Andreas\wissensfreund_repo
set WF_PROMPT_VARIANT=pro
echo START %date% %time% > "C:\Users\Andreas\Desktop\_v8_out.txt"
"C:\Users\Andreas\AppData\Local\Python\pythoncore-3.14-64\python.exe" scripts\generate_grounded.py --catalog Dinosaurier Vulkan Spielzeug --hoerspiel-prompt wissensfreund_hoerspiel_prompt_v8.md --output-dir articles\bakeoff_v8_20260729 --run-id v8_20260729 >> "C:\Users\Andreas\Desktop\_v8_out.txt" 2>&1
echo DONE_EXIT_%errorlevel% %date% %time% >> "C:\Users\Andreas\Desktop\_v8_out.txt"
