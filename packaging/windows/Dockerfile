# Cross-compile toolchain for the Windows ARM64 engine: llvm-mingw (UCRT, like the official Windows Python) + build tools.
FROM mstorsjo/llvm-mingw:latest
RUN apt-get update && apt-get install -y --no-install-recommends \
      ninja-build pkg-config flex bison python3 python3-pip make xz-utils ca-certificates curl patch file \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install --no-cache-dir --break-system-packages meson==1.9.1
