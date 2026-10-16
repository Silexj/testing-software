# Аппаратный профиль OpenBMC в QEMU для лабораторной 5

Профиль предназначен только для локального Romulus QEMU из лабораторной 1:
`OPENBMC_TARGET_MACHINE=romulus`, `BUILD_ID=20250902012112`. Установщик проверяет
оба значения и выключенное состояние хоста. SSH используется только через
`127.0.0.1:2222`; `--qemu` обязателен. Пароль передаётся через `BMC_PASSWORD`,
ключ SSH после первого подключения сохраняется в `.runtime/known_hosts`.

## Датчики

Штатный `phosphor-hwmon-readd` читает два входа в
`/run/lab5-hardware/hwmon0/temp{1,2}_input`. Файлы содержат миллиградусы, начальные
значения — 42000 и 44000. Служба создаёт обычные D-Bus Sensor.Value и Threshold
интерфейсы с 42/44 °C и порогами 0/5/80/90 °C. Изменение входов проходит через
штатный hwmon и вызывает штатное изменение Health при перегреве.

`associations.c` связывает эти датчики с chassis через Association.Definitions:
в выбранной сборке inventory-manager не предоставляет этот интерфейс.
Служба не предоставляет показаний и порогов. bmcweb обнаруживает датчики через
ObjectMapper и формирует обычный ответ Thermal.

В таблице статических IPMI-датчиков этого образа остался масштаб `-3`, хотя
современный hwmon уже предоставляет `double` в Celsius. Из-за этого 42 °C
превращались в 0 при кодировании IPMI. `ipmi_scale_compat.cpp` исправляет только
`scale` на 0 у ID `0x5b` и `0x73` после проверки имени, типа и коэффициентов
обоих датчиков. Обработчики IPMI, показания и пороги остаются штатными.
Модуль включается отдельной переменной окружения службы и рассчитан строго
на ABI выбранного образа; на других сборках его применять нельзя.

Типы в `romulus_sensor_types.hpp` взяты из
[phosphor-host-ipmid 5659dda709](https://github.com/openbmc/phosphor-host-ipmid/blob/5659dda709/include/ipmid/types.hpp).
Лицензия upstream: [LICENSE.ipmi-host](LICENSE.ipmi-host).

## Питание

`board.sh` реализует состояние виртуального PSU и операции отсутствующих
POWER9/FSI/VRM. Установщик создаёт именованные `lab5-hardware.conf` drop-in
файлы в `/run/systemd/system` только для перечисленных в нём аппаратных служб.
Штатные зависимости systemd и службы состояния продолжают выполнять переходы.
`CurrentHostState` и `CurrentPowerState` напрямую не записываются: их обновляют
штатные state-manager после достижения обычных целей systemd.

Модель позволяет проверить путь запроса Reset через bmcweb и state-manager.
Она не загружает ОС POWER9 и не заменяет проверку физической платы.

## Сборка и управление

Из корня репозитория, с установленным `requirements-stand.txt`:

```bash
python lab5/setup_qemu_lab.py install --qemu --build
python lab5/setup_qemu_lab.py status --qemu
python lab5/setup_qemu_lab.py temperature --qemu --cpu0 95 --cpu1 44
python lab5/setup_qemu_lab.py temperature --qemu --cpu0 42 --cpu1 44
python lab5/setup_qemu_lab.py power-fault --qemu --fault on
python lab5/setup_qemu_lab.py power-fault --qemu --fault off
# При выключенном эмулируемом хосте:
python lab5/setup_qemu_lab.py remove --qemu
```

Docker собирает ARMv6 soft-float код с помощью GCC/G++ из Ubuntu 24.04.
Заголовки systemd предоставляет пакет сборки, ARM-библиотека `libsystemd.so.0`
берётся из самого выбранного образа. Результаты находятся в игнорируемом
`.runtime/lab5-build`, бинарники в Git не добавляются.

Службы, входы и аппаратные drop-in файлы живут в `/run`, поэтому после перезапуска
BMC нужна повторная установка. Единственный добавляемый файл вне `/run` —
`/usr/lib/ipmid-providers/libzz-lab5-scale.so`; команда `remove` удаляет его и
свои службы/drop-in файлы, затем перезапускает штатный ipmid. Исходные бинарники
OpenBMC не перезаписываются. Рабочая flash — отдельная копия исходного образа.
