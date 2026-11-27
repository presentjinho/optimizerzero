# Python 3.10 환경에서 이전하기

소스 설치의 최소 버전은 Python 3.11, Pillow 13입니다. Python 3.10 지원 종료에 맞춰 오래된 이미지 처리 경로를 제거했습니다. Windows 배포 파일은 Python을 포함하므로 별도 Python 설치 없이 사용할 수 있습니다. 새 배포 파일은 릴리스가 게시된 후 받을 수 있습니다.

## 기존 데이터와 환경 보존

- 기존 Python과 가상환경을 지우거나 덮어쓰지 마세요. Python 3.11 이상을 별도로 설치하고 새 가상환경 이름을 사용하세요.
- 입력 파일, 최적화 결과, JSON 보고서, 직접 만든 실행 스크립트와 옵션을 기존 위치에 보관하세요. 이 변경은 저장 형식이나 파일 경로를 변경하지 않습니다.
- 기존 가상환경의 `site-packages`를 복사하지 마세요. 새 환경에 필요한 패키지만 다시 설치하세요. PDF/HEIF 기능을 쓰던 경우 아래 선택 설치도 진행하세요.
- 새 환경 확인 전에는 기존 바로가기를 유지하세요. 확인 후 바로가기나 실행 스크립트의 Python 경로만 새 환경으로 바꾸세요. Web Lite 브라우저 저장소에는 이 이전 작업이 영향을 주지 않습니다.

## 새 가상환경 만들기

업데이트한 소스 폴더에서 실행합니다. 아래 `py -3.12`는 설치한 Python 3.11 이상으로 바꿀 수 있습니다. `py` 실행기가 없다면 해당 Python의 전체 경로를 사용하세요. `.venv-py312`가 이미 있으면 다른 새 이름을 선택하세요.

```powershell
py -3.12 -m venv .venv-py312
.\.venv-py312\Scripts\python.exe -m pip install --upgrade pip
.\.venv-py312\Scripts\python.exe -m pip install -e .
# PDF / HEIC 기능이 필요한 경우
.\.venv-py312\Scripts\python.exe -m pip install ".[pdf,heic]"
```

## 확인 후 사용하기

```powershell
.\.venv-py312\Scripts\python.exe -m pip check
.\.venv-py312\Scripts\python.exe -c "import sys, PIL; print(sys.version); print('Pillow', PIL.__version__); assert sys.version_info >= (3, 11); assert int(PIL.__version__.split('.')[0]) >= 13"
.\.venv-py312\Scripts\python.exe -m optimizerzero doctor
.\.venv-py312\Scripts\python.exe -m unittest discover -s tests -v
.\.venv-py312\Scripts\python.exe -m optimizerzero gui
```

평소 사용하는 형식의 복사본으로 확인하세요. 별도 출력 폴더를 사용하고 `--in-place`를 사용하지 않으면 원본을 유지할 수 있습니다. 문제가 있으면 새 환경 사용을 멈추고 기존 환경과 데이터는 보존한 채 오류를 보고하세요. 이전 Pillow 환경에서 외부의 신뢰할 수 없는 파일을 처리하는 것은 피하세요.
