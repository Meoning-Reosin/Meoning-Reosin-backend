"""사진 인식 설정값. 환경변수로 바꿀 수 있다 (1차 임시값)."""

import os

# 이 값 이상이면 인식 성공으로 본다. 모델 확정 후 조정.
CONFIDENCE_THRESHOLD = float(os.getenv("RECOGNITION_CONFIDENCE_THRESHOLD", "0.6"))

# 업로드 사진 최대 용량 (MB)
MAX_IMAGE_MB = int(os.getenv("RECOGNITION_MAX_IMAGE_MB", "10"))
MAX_IMAGE_BYTES = MAX_IMAGE_MB * 1024 * 1024
