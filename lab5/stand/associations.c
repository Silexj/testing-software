/* SPDX-License-Identifier: Apache-2.0
 * Chassis associations for the two emulated CPU inputs.
 * Values/thresholds are provided by the stock phosphor-hwmon daemon.
 */
#include <systemd/sd-bus.h>
#include <errno.h>
#include <stdio.h>

static int associations(sd_bus *bus, const char *path, const char *interface,
                        const char *property, sd_bus_message *reply,
                        void *userdata, sd_bus_error *error) {
    (void)bus; (void)path; (void)interface; (void)property;
    (void)userdata; (void)error;
    int rc = sd_bus_message_open_container(reply, 'a', "(sss)");
    if (rc < 0) return rc;
    rc = sd_bus_message_append(reply, "(sss)", "chassis", "all_sensors",
        "/xyz/openbmc_project/inventory/system/chassis");
    if (rc < 0) return rc;
    return sd_bus_message_close_container(reply);
}

static const sd_bus_vtable vtable[] = {
    SD_BUS_VTABLE_START(0),
    SD_BUS_PROPERTY("Associations", "a(sss)", associations, 0,
                    SD_BUS_VTABLE_PROPERTY_CONST),
    SD_BUS_VTABLE_END
};

int main(void) {
    sd_bus *bus = NULL;
    int rc = sd_bus_open_system(&bus);
    if (rc < 0) return 1;
    rc = sd_bus_add_object_manager(bus, NULL, "/xyz/openbmc_project/sensors");
    if (rc < 0) return 2;
    const char *paths[] = {
        "/xyz/openbmc_project/sensors/temperature/p0_core0_temp",
        "/xyz/openbmc_project/sensors/temperature/p1_core0_temp"
    };
    for (unsigned i = 0; i < 2; ++i) {
        rc = sd_bus_add_object_vtable(bus, NULL, paths[i],
            "xyz.openbmc_project.Association.Definitions", vtable, NULL);
        if (rc < 0) return 3;
    }
    rc = sd_bus_request_name(bus, "xyz.openbmc_project.Lab5.Associations", 0);
    if (rc < 0) return 4;
    for (unsigned i = 0; i < 2; ++i) sd_bus_emit_object_added(bus, paths[i]);
    for (;;) {
        rc = sd_bus_process(bus, NULL);
        if (rc < 0) break;
        if (rc > 0) continue;
        rc = sd_bus_wait(bus, (uint64_t)-1);
        if (rc < 0) break;
    }
    sd_bus_unref(bus);
    fprintf(stderr, "Association service stopped: %d\n", rc);
    return 5;
}
