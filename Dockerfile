# ========== 基础镜像 ==========
FROM python:3.10-slim AS base

# ========== 阶段1：离线安装系统编译依赖（仅 builder 使用） ==========
FROM base AS sysdeps

COPY dist/apt-packages /pkgs
RUN dpkg -i --force-depends /pkgs/*.deb 2>/dev/null || true && \
    apt-get install -f -y --no-install-recommends && \
    rm -rf /var/lib/apt/lists/* /pkgs

# ========== 阶段2：准备离线 Python 包（供 builder 和 final 使用） ==========
FROM base AS offline-pkgs

WORKDIR /pkgs
COPY dist/packages/ /pkgs/
COPY requirements-build.txt /pkgs/
COPY requirements-runtime.txt /pkgs/

# ========== 阶段3：编译核心模块（只编译 app/core） ==========
FROM sysdeps AS builder

WORKDIR /build
COPY app/ ./app/
COPY --from=offline-pkgs /pkgs /pkgs

# 安装编译依赖（仅 cython）
RUN pip install --no-index --find-links /pkgs -r /pkgs/requirements-build.txt

# 编写 setup.py，编译 app/core
RUN echo "\
from setuptools import setup\n\
from Cython.Build import cythonize\n\
import os\n\
\n\
py_files = []\n\
core_dir = 'app/core'\n\
exclude_files = []\n\
skip_dirs = ['app/core/steps']\n\
for root, _, files in os.walk(core_dir):\n\
    if any(os.path.normpath(root).startswith(os.path.normpath(d)) for d in skip_dirs):\n\
        continue\n\
    for file in files:\n\
        if file.endswith('.py') and file != '__init__.py':\n\
            full_path = os.path.join(root, file)\n\
            if full_path in exclude_files:\n\
                continue\n\
            py_files.append(full_path)\n\
\n\
setup(\n\
    name='psytext_core',\n\
    ext_modules=cythonize(py_files, build_dir='build', compiler_directives={'language_level': 3}, nthreads=4),\n\
)\n\
" > setup.py

RUN python setup.py build_ext --inplace

# 清理编译中间文件 + 删除需要混淆的原始 JS
RUN find app/core -name "*.c" -delete && \
    find app/core -type f -name "*.py" -not -name "__init__.py" -not -path "*/steps/*" -delete && \
    rm -rf build/ /root/.cache/pip && \
    find app/static/js -type f -name "*.js" ! -name "alpine.min.js" ! -name "axios.min.js" ! -name "iconify.min.js" -delete

# 打包编译后的 app 目录
RUN mkdir /output && cp -r app /output/

# ========== 阶段4：混淆 JavaScript ==========
FROM node:20-alpine AS js-obfuscator

WORKDIR /src
COPY app/static/js/ ./js/
COPY dist/npm-packages/javascript-obfuscator-4.1.1.tgz /tmp/javascript-obfuscator.tgz

RUN npm install -g /tmp/javascript-obfuscator.tgz && \
    mkdir -p /obf && \
    cd js && \
    find . -name "*.js" -type f | while read -r file; do \
        case "$file" in \
            */alpine.min.js|*/axios.min.js|*/iconify.min.js|*/d3.min.js) \
                mkdir -p "/obf/$(dirname "$file")" && cp "$file" "/obf/$file"; \
                ;; \
            *) \
                mkdir -p "/obf/$(dirname "$file")" && \
                javascript-obfuscator "$file" --output "/obf/$file" \
                    --compact true \
                    --control-flow-flattening true \
                    --control-flow-flattening-threshold 0.5 \
                    --dead-code-injection true \
                    --dead-code-injection-threshold 0.3 \
                    --rename-globals false \
                    --self-defending true; \
                ;; \
        esac; \
    done

# ========== 阶段5：最终运行镜像（仅运行时依赖） ==========
FROM base

ENV TZ=Asia/Shanghai

# 注意：apt-packages 中除 tzdata 外还包含 cv2 运行所需的 X11/XCB/GObject 系统库
# dist/bin 包含 ffmpeg/ffprobe 静态二进制，用于音视频处理
COPY dist/apt-packages/*.deb /tmp/apt/
COPY dist/bin/ /usr/local/bin/
COPY --from=offline-pkgs /pkgs /tmp/pkgs
COPY --from=builder /output/app ./app/
COPY --from=js-obfuscator /obf/ ./app/static/js/

# === 安装系统依赖 + Python 包 ===
RUN chmod +x /usr/local/bin/ffmpeg /usr/local/bin/ffprobe 2>/dev/null || true && \
    dpkg -i --force-depends /tmp/apt/*.deb 2>/dev/null || true && \
    apt-get install -f -y --no-install-recommends && \
    ldconfig && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone && \
    pip install --no-index --find-links /tmp/pkgs torch --no-deps && \
    pip install --no-index --find-links /tmp/pkgs -r /tmp/pkgs/requirements-runtime.txt && \
    find /app -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true && \
    find /app -name "*.pyc" -delete 2>/dev/null || true && \
    rm -rf /tmp/apt /tmp/pkgs /var/lib/apt/lists/* /var/cache/apt/archives/* /root/.cache/pip

# 创建用户 + 设置权限
RUN useradd --uid 1000 --create-home --shell /bin/bash appuser && \
    chmod +x /usr/local/bin/ffmpeg /usr/local/bin/ffprobe && \
    chown appuser:appuser /usr/local/bin/ffmpeg /usr/local/bin/ffprobe && \
    chown -R appuser:appuser /app && \
    mkdir -p /data/logs_fallback && \
    chown -R appuser:appuser /data

WORKDIR /

ENV PYTHONPATH=/
ENV PATH=/usr/local/bin:/usr/bin:/bin:$PATH

USER appuser

CMD [ \
    "python", "-m", "uvicorn", "app.main:app", \
    "--host", "0.0.0.0", \
    "--port", "8000", \
    "--workers", "1", \
    "--timeout-keep-alive", "30", \
    "--timeout-graceful-shutdown", "60", \
    "--log-level", "info" \
]
