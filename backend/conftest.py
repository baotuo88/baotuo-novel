# AIMETA P=测试环境基线配置|R=为 pytest 提供最小环境变量|NR=不含业务逻辑|E=-|X=internal|A=pytest 配置|D=pytest,os|S=env|RD=./README.ai
import os


# 允许在本地/CI 直接运行测试，不依赖外部注入 SECRET_KEY。
os.environ.setdefault("SECRET_KEY", "test-secret-key")
