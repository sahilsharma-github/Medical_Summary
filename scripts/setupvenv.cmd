REM create virtual env
call python3 -m venv venv

REM activate
call venv\Scripts\activate

REM version frozen in requirements.txt file
pip install -r scripts\requirements.txt
