"""테스트 환경 때문에 판별력을 잃는 단정에 붙이는 마커."""
import os

import pytest

# chmod(0)로 읽기를 막는 테스트는 root에서 무의미하다 — root는 권한 비트를 무시하므로
# 정상 구현에서도 예외가 나지 않아 **거짓 실패**한다. 조용히 통과하는 것이 아니라 상시
# 빨간 테스트가 되고, 누군가 skip 처리하면 그 시점부터 보호가 사라진다.
# 현재 root로 도는 CI 설정은 없다. 이 마커는 그런 환경이 생겼을 때를 위한 것이다.
requires_permission_bits = pytest.mark.skipif(
    hasattr(os, "getuid") and os.getuid() == 0,
    reason="root는 권한 비트를 무시한다 — chmod(0) 단정이 거짓 실패한다",
)
