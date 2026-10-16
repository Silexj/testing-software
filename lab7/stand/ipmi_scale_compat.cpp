// SPDX-License-Identifier: Apache-2.0
// Correct the two legacy millidegree scale entries in the pinned Romulus image.
// No IPMI handler, reading, response or threshold is replaced. The stock IPMI
// implementation reads the stock hwmon double values in Celsius after this fix.
#include "romulus_sensor_types.hpp"
#include <dlfcn.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>

__attribute__((constructor)) static void correct_cpu_scale() {
    const char* enabled = std::getenv("LAB5_FIX_STATIC_SENSOR_SCALE");
    if (!enabled || std::strcmp(enabled, "1") != 0) return;
    void* handle = dlopen("/usr/lib/ipmid-providers/libipmi20.so.0", RTLD_NOW);
    if (!handle) { std::fprintf(stderr, "lab5: IPMI provider not found\n"); return; }
    auto* table = static_cast<const ipmi::sensor::IdInfoMap*>(
        dlsym(handle, "_ZN4ipmi6sensor7sensorsE"));
    if (!table || table->size() > 255 || table->size() < 2) {
        std::fprintf(stderr, "lab5: unsupported IPMI sensor table\n"); return;
    }
    const unsigned ids[] = {0x5b, 0x73};
    const char* paths[] = {
        "/xyz/openbmc_project/sensors/temperature/p0_core0_temp",
        "/xyz/openbmc_project/sensors/temperature/p1_core0_temp"
    };
    // Validate every entry before changing any metadata. This helper is pinned
    // to OpenBMC BUILD_ID=20250902012112, ipmi-host commit 5659dda709.
    for (unsigned i=0; i<2; ++i) {
        auto entry = table->find(ids[i]);
        if (entry == table->end() || entry->second.sensorPath != paths[i] ||
            entry->second.sensorType != 1 || entry->second.coefficientM != 1 ||
            entry->second.exponentR != 0 || entry->second.scale != -3) {
            std::fprintf(stderr, "lab5: sensor table validation failed at %u\n", ids[i]);
            return;
        }
    }
    for (unsigned i=0; i<2; ++i) {
        // std::map nodes contain a non-const mapped_type, including in a const
        // container. Only the legacy scale metadata is updated in those nodes.
        auto& info = const_cast<ipmi::sensor::Info&>(table->find(ids[i])->second);
        info.scale = 0;
        std::fprintf(stderr, "lab5: %s: scale -3 -> 0 for Celsius hwmon values\n", paths[i]);
    }
}
