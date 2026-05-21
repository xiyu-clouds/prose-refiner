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

# 编写 setup.py，编译 app/core（排除 utils.py）
RUN echo "\
from setuptools import setup\n\
from Cython.Build import cythonize\n\
import os\n\
\n\
py_files = []\n\
core_dir = 'app/core'\n\
exclude_files = ['app/core/meta/utils.py','app/core/steps/basic/text_processor.py']\n\
for root, _, files in os.walk(core_dir):\n\
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

# 清理编译中间文件 + 删除需要混淆的原始 JS（保留第三方库）
RUN find app/core -name "*.c" -delete && \
    find app/core -type f -name "*.py" -not -name "__init__.py" -not -path "app/core/meta/utils.py" -not -path "app/core/steps/basic/text_processor.py" -delete && \
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
    for file in *.js; do \
        case "$file" in \
            alpine.min.js|axios.min.js|iconify.min.js) \
                cp "$file" "/obf/$file"; \
                ;; \
            *) \
                javascript-obfuscator "$file" --output "/obf/$file" \
                    --compact true \
                    --control-flow-flattening true \
                    --control-flow-flattening-threshold 0.5 \
                    --dead-code-injection true \
                    --dead-code-injection-threshold 0.3 \
                    --string-array true \
                    --string-array-threshold 0.75 \
                    --rename-globals false \
                    --self-defending true; \
                ;; \
        esac; \
    done

# ========== 阶段5：最终运行镜像（仅运行时依赖） ==========
FROM base

ENV TZ=Asia/Shanghai

# 将所有安装和清理合并到一个 RUN 层，避免跨层残留
COPY dist/apt-packages/tzdata*.deb /tmp/apt/
COPY --from=offline-pkgs /pkgs /tmp/pkgs
COPY --from=builder /output/app ./app/
COPY --from=js-obfuscator /obf/ ./app/static/js/

RUN dpkg -i --force-depends /tmp/apt/*.deb 2>/dev/null || true && \
    apt-get install -f -y --no-install-recommends && \
    ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone && \
    pip install --no-index --find-links /tmp/pkgs -r /tmp/pkgs/requirements-runtime.txt && \
    rm -rf /tmp/apt /tmp/pkgs /var/lib/apt/lists/* /var/cache/apt/archives/* /root/.cache/pip

# 创建用户
RUN useradd --uid 1000 --create-home --shell /bin/bash appuser && \
    chown -R appuser:appuser /app

# 启动命令
CMD ["sh", "-c", "mkdir -p /data/logs_fallback && chown -R appuser:appuser /data && exec su -c 'python -m uvicorn app.main:app --host 0.0.0.0 --port 8000' appuser"]