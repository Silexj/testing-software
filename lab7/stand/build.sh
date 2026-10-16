#!/bin/sh
set -eu
arm-linux-gnueabi-gcc -march=armv6 -mfloat-abi=soft -O2 -Wall -Wextra \
    associations.c ./libsystemd.so.0 -Wl,--allow-shlib-undefined -o associations
arm-linux-gnueabi-g++ -march=armv6 -mfloat-abi=soft -std=c++20 -O2 \
    -Wall -Wextra -fPIC -shared ipmi_scale_compat.cpp -ldl -o libzz-lab5-scale.so
